"""Model catalog and provider factory used by every Agent execution path."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from app.config import config
from app.llm.loader import LLMGenerationError, LLMLoader
from app.tools.types import ErrorCode

QWEN_LOCAL = "qwen-local"
DEEPSEEK_API = "deepseek-api"
SUPPORTED_MODEL_IDS = {QWEN_LOCAL, DEEPSEEK_API}


def resolve_model_id(model_id: Optional[str]) -> str:
    """Resolve an omitted ID to the configured default and reject unknown IDs."""
    resolved = (model_id or config.llm_default_model).strip().lower()
    if resolved not in SUPPORTED_MODEL_IDS:
        raise LLMGenerationError(
            ErrorCode.INVALID_PARAM,
            f"Unknown model '{resolved}'. Choose qwen-local or deepseek-api.",
        )
    return resolved


def list_models() -> List[Dict[str, Any]]:
    """Return a public model catalog without exposing paths or credentials."""
    default_id = resolve_model_id(None)
    qwen_available = bool(config.llm_mock or os.path.isdir(config.model_path))
    deepseek_available = bool(config.deepseek_api_key)
    return [
        {
            "id": QWEN_LOCAL,
            "label": "Qwen（本地）",
            "provider": "local",
            "backend_model": "Qwen3-0.6B",
            "available": qwen_available,
            "default": default_id == QWEN_LOCAL,
            "detail": (
                "演示模式可用"
                if config.llm_mock
                else ("本地模型可用" if qwen_available else "当前设备未找到本地模型")
            ),
        },
        {
            "id": DEEPSEEK_API,
            "label": "DeepSeek（API）",
            "provider": "deepseek",
            "backend_model": config.deepseek_model,
            "available": deepseek_available,
            "default": default_id == DEEPSEEK_API,
            "detail": "API 已配置" if deepseek_available else "需要配置 DEEPSEEK_API_KEY",
        },
    ]


def create_llm(
    model_id: Optional[str] = None,
    *,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
):
    """Create a lightweight adapter; callers select explicitly per request."""
    resolved = resolve_model_id(model_id)
    tokens = config.model_max_tokens if max_tokens is None else max_tokens
    temp = config.model_temperature if temperature is None else temperature
    nucleus = config.model_top_p if top_p is None else top_p
    if resolved == QWEN_LOCAL:
        return LLMLoader(
            model_path=config.model_path,
            device=config.model_device,
            max_tokens=tokens,
            temperature=temp,
            top_p=nucleus,
        )

    from app.llm.deepseek import DeepSeekLLM

    return DeepSeekLLM(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
        timeout_seconds=config.deepseek_timeout_seconds,
        max_tokens=tokens,
        temperature=temp,
        top_p=nucleus,
    )
