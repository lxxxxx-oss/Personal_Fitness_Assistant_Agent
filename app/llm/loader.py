"""Qwen3-0.6B 模型加载与生成封装.

PERMISSION: This LLM generates text based on statistical patterns in training data.
Its output may be inaccurate, outdated, or biased. It does NOT provide:
- Medical diagnosis or treatment recommendations
- Professional training plans for individuals with injuries/conditions
- Nutritional advice for specific medical conditions
Users should consult qualified professionals for health-related decisions.
"""

import gc
import logging
import os
import threading
from typing import Any, Dict, Generator, Optional, Tuple

from app.tools.types import ErrorCode, ToolResult

logger = logging.getLogger(__name__)

# A model is a process-level resource. Subgraph nodes may create lightweight
# LLMLoader wrappers with different generation settings, but they must reuse
# the same tokenizer/model objects instead of loading one copy per node.
_MODEL_CACHE: Dict[Tuple[str, str, str], Tuple[Any, Any]] = {}
_MODEL_LOAD_LOCK = threading.Lock()
_MODEL_GENERATION_LOCK = threading.Lock()


class LLMGenerationError(RuntimeError):
    """Stable generation failure that callers can map to a transport error."""

    def __init__(self, error_code: str, public_message: str):
        super().__init__(public_message)
        self.error_code = error_code
        self.public_message = public_message


class LLMLoader:
    """加载本地 Qwen3-0.6B 模型,提供统一的 generate() 和流式 generate_stream() 接口.

    Input:
        prompt: non-empty str, bounded by MAX_PROMPT_CHARS
        max_new_tokens: int (optional)
        temperature: float (optional)
        top_p: float (optional)

    Output:
        generate() -> str
        generate_stream() -> Generator[str]
    """

    def __init__(
        self,
        model_path: str,
        device: str = "cpu",
        max_tokens: int = 1024,
        temperature: float = 0.6,
        top_p: float = 0.95,
    ):
        self.model_path = model_path
        self.device = device
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self._model = None
        self._tokenizer = None

    def _ensure_loaded(self) -> ToolResult:
        """延迟加载模型(首次调用generate时才加载).

        Returns:
            ToolResult: ok if loaded, fail with DATA_NOT_FOUND if model path invalid.
        """
        from app.config import config

        if config.llm_mock:
            return ToolResult.ok(mock=True)
        if self._model is not None:
            return ToolResult.ok()
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if not os.path.isdir(self.model_path):
            return ToolResult.fail(
                ErrorCode.DATA_NOT_FOUND,
                f"Model path not found: '{self.model_path}'. "
                f"Download the model or update config.model_path.",
                meta={"model_path": self.model_path},
            )

        dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
        cache_key = (
            os.path.normcase(os.path.abspath(self.model_path)),
            self.device,
            str(dtype),
        )

        cached = _MODEL_CACHE.get(cache_key)
        if cached is not None:
            self._tokenizer, self._model = cached
            return ToolResult.ok(shared=True)

        # Double-checked locking prevents concurrent first requests from
        # allocating multiple multi-gigabyte copies of the same model.
        with _MODEL_LOAD_LOCK:
            cached = _MODEL_CACHE.get(cache_key)
            if cached is not None:
                self._tokenizer, self._model = cached
                return ToolResult.ok(shared=True)

            logger.info("Loading shared model from %s on %s...", self.model_path, self.device)
            try:
                tokenizer = AutoTokenizer.from_pretrained(
                    self.model_path, trust_remote_code=True
                )
                model = AutoModelForCausalLM.from_pretrained(
                    self.model_path,
                    dtype=dtype,
                    trust_remote_code=True,
                ).to(self.device)
                model.eval()
                _MODEL_CACHE[cache_key] = (tokenizer, model)
                self._tokenizer = tokenizer
                self._model = model
                logger.info("Shared model loaded and cached.")
                return ToolResult.ok(shared=False)
            except Exception as e:
                # Do not retain partially initialized objects after a failed or
                # out-of-memory load. This keeps the next retry deterministic.
                self._tokenizer = None
                self._model = None
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                return ToolResult.fail(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to load model from '{self.model_path}': {e}",
                    model_path=self.model_path,
                    device=self.device,
                    shared_cache_entries=len(_MODEL_CACHE),
                )

    @staticmethod
    def _validate_prompt(prompt: str) -> None:
        """Validate the transport-independent prompt contract."""
        from app.config import config

        if not isinstance(prompt, str) or not prompt.strip():
            logger.error("prompt must be a non-empty string")
            raise LLMGenerationError(
                ErrorCode.INVALID_PARAM,
                "The model prompt is empty or invalid.",
            )
        max_prompt_chars = config.context_max_prompt_chars
        if len(prompt) > max_prompt_chars:
            logger.error(
                "prompt too long: %s chars (max %s)",
                len(prompt),
                max_prompt_chars,
            )
            raise LLMGenerationError(
                ErrorCode.INVALID_PARAM,
                "The model prompt exceeds the configured size limit.",
            )

    def _prepare_inputs(self, prompt: str):
        """Validate prompt and convert to model input tensors.

        Raises:
            LLMGenerationError: If the prompt is invalid or the model is unavailable.
        """
        self._validate_prompt(prompt)

        result = self._ensure_loaded()
        if not result.ok:
            logger.error("Model load failed: %s", result.error_message)
            raise LLMGenerationError(
                result.error_code or ErrorCode.INTERNAL_ERROR,
                "The local language model is unavailable.",
            )

        messages = [{"role": "user", "content": prompt}]
        text = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        return self._tokenizer(text, return_tensors="pt").to(self.device), text

    def generate(
        self,
        prompt: str,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> str:
        """给定提示词,生成文本回复.

        Raises:
            LLMGenerationError: Prompt validation or model loading failed.
        """
        from app.config import config

        self._validate_prompt(prompt)
        if config.llm_mock:
            return _mock_response(prompt)

        import torch

        tokens = self.max_tokens if max_new_tokens is None else max_new_tokens
        temp = self.temperature if temperature is None else temperature
        p = self.top_p if top_p is None else top_p

        inputs, _ = self._prepare_inputs(prompt)

        # The shared model is intentionally serialized. Concurrent generation
        # would create multiple KV caches and can exhaust CPU/GPU memory.
        generation_kwargs = {
            "max_new_tokens": tokens,
            "do_sample": temp > 0,
            "pad_token_id": (
                self._tokenizer.pad_token_id or self._tokenizer.eos_token_id
            ),
        }
        if temp > 0:
            generation_kwargs["temperature"] = temp
            generation_kwargs["top_p"] = p

        with _MODEL_GENERATION_LOCK, torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                **generation_kwargs,
            )

        generated = outputs[0][inputs["input_ids"].shape[1] :]
        result = self._tokenizer.decode(generated, skip_special_tokens=True)
        return result.strip()

    def generate_stream(
        self,
        prompt: str,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> Generator[str, None, None]:
        """流式生成 — 逐 token yield 文本增量.

        Raises:
            LLMGenerationError: Prompt validation or model loading failed.
        """
        from app.config import config

        self._validate_prompt(prompt)
        if config.llm_mock:
            for token in _mock_response(prompt):
                yield token
            return

        import torch

        tokens = self.max_tokens if max_new_tokens is None else max_new_tokens
        temp = self.temperature if temperature is None else temperature
        p = self.top_p if top_p is None else top_p

        inputs, _ = self._prepare_inputs(prompt)
        with _MODEL_GENERATION_LOCK:
            past_key_values = None
            current_ids = inputs["input_ids"]

            for _ in range(tokens):
                with torch.no_grad():
                    outputs = self._model(
                        input_ids=current_ids,
                        past_key_values=past_key_values,
                        use_cache=True,
                    )
                past_key_values = outputs.past_key_values
                logits = outputs.logits[:, -1, :]

                # 温度采样
                if temp > 0:
                    logits = logits / temp
                    if p < 1.0:
                        sorted_logits, sorted_indices = torch.sort(logits, descending=True)
                        cum_probs = torch.cumsum(
                            torch.softmax(sorted_logits, dim=-1), dim=-1
                        )
                        sorted_indices_to_remove = cum_probs > p
                        sorted_indices_to_remove[:, 1:] = sorted_indices_to_remove[
                            :, :-1
                        ].clone()
                        sorted_indices_to_remove[:, 0] = False
                        indices_to_remove = sorted_indices_to_remove.scatter(
                            1, sorted_indices, sorted_indices_to_remove
                        )
                        logits[indices_to_remove] = float("-inf")
                    probs = torch.softmax(logits, dim=-1)
                    next_token_id = torch.multinomial(probs, num_samples=1)
                else:
                    next_token_id = logits.argmax(dim=-1, keepdim=True)

                token_id = next_token_id.item()

                # 遇到 EOS 就停止
                if token_id == self._tokenizer.eos_token_id:
                    break

                token_text = self._tokenizer.decode(
                    [token_id], skip_special_tokens=True
                )
                if token_text:
                    yield token_text

                current_ids = next_token_id


def _mock_response(prompt: str) -> str:
    """Return a deterministic demo response when LLM_MOCK is enabled."""
    if "工具返回数据" in prompt and (
        "配料" in prompt or "ingredients" in prompt or "steps" in prompt
    ):
        recipe_reply = _mock_recipe_response(prompt)
        if recipe_reply:
            return recipe_reply
    if "减脂" in prompt or "饮食" in prompt or "营养" in prompt:
        return (
            "【Demo 模式】减脂期间建议保证蛋白质摄入，控制总热量，"
            "主食选择粗粮，搭配蔬菜和瘦肉。真实建议应结合身高、体重和训练量。"
        )
    if "深蹲" in prompt or "姿势" in prompt or "动作" in prompt:
        return (
            "【Demo 模式】深蹲时保持核心收紧、背部中立、膝盖与脚尖方向一致，"
            "下蹲深度以动作稳定为前提。若要做 3D 分析，请上传 .npz 姿态数据。"
        )
    if "搜索结果" in prompt or "联网搜索" in prompt:
        return "【Demo 模式】这里会基于 Tavily 或 mock 搜索结果合成摘要，并标注来源。"
    return "【Demo 模式】你好，我是健身智能助手。你可以问我健身知识、饮食建议、动作分析或菜谱做法。"


def _mock_recipe_response(prompt: str) -> str:
    """Format MCP recipe payloads in demo mode without hard-coding one dish."""
    import json
    import re

    match = re.search(
        r"# 工具返回数据\s*(.*?)(?=\n\n# |\Z)",
        prompt,
        flags=re.S,
    )
    if not match:
        return ""

    raw_payload = match.group(1).strip()
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return raw_payload if raw_payload else ""

    if isinstance(payload, dict) and isinstance(payload.get("content"), list):
        for item in payload["content"]:
            if not isinstance(item, dict) or item.get("type") != "text":
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                return text
            break

    if isinstance(payload, dict) and payload.get("error"):
        return f"【Demo 模式】{payload.get('error')}。{payload.get('suggestion', '')}".strip()

    if isinstance(payload, list):
        names = [str(item.get("name", item)) for item in payload[:5]]
        return "【Demo 模式】可以考虑这些菜：" + "、".join(names)

    if not isinstance(payload, dict):
        return ""

    if "recommendations" in payload:
        dishes = "、".join(map(str, payload.get("recommendations", [])))
        return f"【Demo 模式】为 {payload.get('peopleCount', '你')} 人推荐：{dishes}。"

    if "weeklyPlan" in payload:
        days = "、".join(payload.get("weeklyPlan", {}).keys())
        shopping = "、".join(map(str, payload.get("shoppingList", [])[:8]))
        return f"【Demo 模式】已生成 {payload.get('peopleCount', '多')} 人膳食计划，覆盖 {days}。购物清单可先准备：{shopping}。"

    name = payload.get("name")
    if not name:
        return ""

    ingredients = payload.get("ingredients", [])
    ingredient_text = []
    for item in ingredients:
        if isinstance(item, dict):
            ingredient_text.append(str(item.get("text_quantity") or item.get("name") or item))
        else:
            ingredient_text.append(str(item))

    steps = payload.get("steps", [])
    step_text = "；".join(map(str, steps[:6]))
    extra = payload.get("calories") or payload.get("description") or ""

    parts = [f"【Demo 模式】{name}可以这样做"]
    if ingredient_text:
        parts.append("配料：" + "、".join(ingredient_text))
    if step_text:
        parts.append("步骤：" + step_text)
    if extra:
        parts.append("补充：" + str(extra))
    return "。".join(parts) + "。"
