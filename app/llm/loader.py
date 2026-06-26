"""Qwen3-0.6B 模型加载与生成封装.

PERMISSION: This LLM generates text based on statistical patterns in training data.
Its output may be inaccurate, outdated, or biased. It does NOT provide:
- Medical diagnosis or treatment recommendations
- Professional training plans for individuals with injuries/conditions
- Nutritional advice for specific medical conditions
Users should consult qualified professionals for health-related decisions.
"""

import logging
from typing import Generator, Optional

from app.tools.types import ToolResult, ErrorCode, check_str_nonempty, check_str_len

logger = logging.getLogger(__name__)

# --- Constants ---
MAX_PROMPT_CHARS = 8192  # ~4096 tokens in Chinese


class LLMLoader:
    """加载本地 Qwen3-0.6B 模型,提供统一的 generate() 和流式 generate_stream() 接口.

    Input:
        prompt: str, 1-8192 chars
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
        import os
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if not os.path.isdir(self.model_path):
            return ToolResult.fail(
                ErrorCode.DATA_NOT_FOUND,
                f"Model path not found: '{self.model_path}'. "
                f"Download the model or update config.model_path.",
                meta={"model_path": self.model_path},
            )

        logger.info(f"Loading model from {self.model_path} on {self.device}...")
        try:
            dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_path, trust_remote_code=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                torch_dtype=dtype,
                trust_remote_code=True,
            ).to(self.device)
            self._model.eval()
            logger.info("Model loaded.")
            return ToolResult.ok()
        except Exception as e:
            return ToolResult.fail(
                ErrorCode.INTERNAL_ERROR,
                f"Failed to load model from '{self.model_path}': {e}",
                meta={"model_path": self.model_path},
            )

    def _prepare_inputs(self, prompt: str):
        """Validate prompt and convert to model input tensors.

        Returns:
            (inputs_dict, text) or (None, None) on failure.
        """
        # Validate prompt
        if not isinstance(prompt, str) or not prompt.strip():
            logger.error("prompt must be a non-empty string")
            return None, None
        if len(prompt) > MAX_PROMPT_CHARS:
            logger.error(
                f"prompt too long: {len(prompt)} chars (max {MAX_PROMPT_CHARS})"
            )
            return None, None

        result = self._ensure_loaded()
        if not result.ok:
            logger.error(f"Model load failed: {result.error_message}")
            return None, None

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

        Returns:
            生成的完整文本，出错时返回以"[Error]"开头的错误字符串。
        """
        from app.config import config

        if config.llm_mock:
            return _mock_response(prompt)

        import torch

        tokens = max_new_tokens or self.max_tokens
        temp = temperature or self.temperature
        p = top_p or self.top_p

        inputs, _ = self._prepare_inputs(prompt)
        if inputs is None:
            return "[Error: Model not loaded or prompt invalid]"

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=tokens,
                temperature=temp,
                top_p=p,
                do_sample=True,
                pad_token_id=self._tokenizer.pad_token_id
                or self._tokenizer.eos_token_id,
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

        Yields:
            每个 token 片段，出错时 yield 一个 "[Error]" 前缀标记。
        """
        from app.config import config

        if config.llm_mock:
            for token in _mock_response(prompt):
                yield token
            return

        import torch

        tokens = max_new_tokens or self.max_tokens
        temp = temperature or self.temperature
        p = top_p or self.top_p

        inputs, _ = self._prepare_inputs(prompt)
        if inputs is None:
            yield "[Error: Model not loaded or prompt invalid]"
            return
        input_len = inputs["input_ids"].shape[1]
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
    if "番茄炒蛋" in prompt or "菜谱" in prompt or "配料" in prompt:
        return (
            "【Demo 模式】番茄炒蛋可以这样做：1. 番茄切块，鸡蛋打散；"
            "2. 先炒鸡蛋盛出；3. 再炒番茄出汁；4. 倒回鸡蛋，加盐调味。"
        )
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
