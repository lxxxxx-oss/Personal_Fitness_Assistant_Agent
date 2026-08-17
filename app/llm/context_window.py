"""Resolve a local model's declared context window and derive safe budgets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple


_CONTEXT_FIELDS = (
    "max_position_embeddings",
    "n_positions",
    "max_sequence_length",
    "seq_length",
    "model_max_length",
)
_MAX_REASONABLE_CONTEXT = 10_000_000


@dataclass(frozen=True)
class ContextWindowInfo:
    """Resolved hard context limit and the evidence used for it."""

    tokens: int
    source: str
    declared_tokens: Optional[int] = None


@dataclass(frozen=True)
class ContextBudget:
    """Application prompt budget derived from a model's hard limit."""

    context_window_tokens: int
    output_reserve_tokens: int
    safety_tokens: int
    max_prompt_tokens: int
    compact_trigger_tokens: int


def derive_conversation_summary_trigger(
    compact_trigger_tokens: int,
    *,
    ratio: float = 0.35,
    minimum_tokens: int = 900,
    maximum_tokens: int = 4000,
    override_tokens: int = 0,
) -> int:
    """Derive a stable old-dialogue summary watermark from prompt budget.

    The conversation summary is a lossy, persisted view, so it should not run
    every time the request-level prompt approaches its compact watermark.  A
    bounded fraction keeps the default conservative for small models while
    avoiding needlessly early summaries for larger context windows.  An
    explicit override remains available for deployments that have calibrated
    their own threshold.
    """
    if compact_trigger_tokens <= 0:
        raise ValueError("prompt compact trigger must be positive")
    if not 0.0 < ratio <= 1.0:
        raise ValueError("CONVERSATION_SUMMARY_TRIGGER_RATIO must be in (0, 1]")
    if minimum_tokens <= 0 or maximum_tokens <= 0:
        raise ValueError("conversation summary trigger bounds must be positive")
    if minimum_tokens > maximum_tokens:
        raise ValueError(
            "CONVERSATION_SUMMARY_TRIGGER_MIN_TOKENS must not exceed "
            "CONVERSATION_SUMMARY_TRIGGER_MAX_TOKENS"
        )
    if override_tokens < 0:
        raise ValueError("CONVERSATION_SUMMARY_TRIGGER_TOKENS must not be negative")
    if override_tokens:
        return override_tokens

    automatic = int(compact_trigger_tokens * ratio)
    return min(max(automatic, minimum_tokens), maximum_tokens)


def _valid_context_value(value: Any) -> Optional[int]:
    """Return a usable context length while ignoring tokenizer sentinels."""
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if 128 <= parsed <= _MAX_REASONABLE_CONTEXT:
        return parsed
    return None


def detect_context_window(data: Mapping[str, Any]) -> Optional[Tuple[int, str]]:
    """Detect a context limit from a Hugging Face-style config mapping."""
    candidates = [("", data)]
    text_config = data.get("text_config")
    if isinstance(text_config, Mapping):
        candidates.insert(0, ("text_config.", text_config))

    for prefix, mapping in candidates:
        for field in _CONTEXT_FIELDS:
            value = _valid_context_value(mapping.get(field))
            if value is not None:
                return value, f"{prefix}{field}"
    return None


def detect_runtime_context_window(model: Any) -> Optional[Tuple[int, str]]:
    """Read the same limit from an already-loaded Transformers model."""
    model_config = getattr(model, "config", None)
    if model_config is None:
        return None
    if hasattr(model_config, "to_dict"):
        try:
            data = model_config.to_dict()
        except Exception:
            data = None
        if isinstance(data, Mapping):
            detected = detect_context_window(data)
            if detected:
                return detected[0], f"runtime_model.config.{detected[1]}"

    for field in _CONTEXT_FIELDS:
        value = _valid_context_value(getattr(model_config, field, None))
        if value is not None:
            return value, f"runtime_model.config.{field}"
    return None


def resolve_model_context_window(
    model_path: str,
    *,
    override_tokens: int = 0,
    fallback_tokens: int = 4096,
) -> ContextWindowInfo:
    """Resolve the hard limit from local model files, then cap or fall back.

    ``MODEL_CONTEXT_WINDOW`` is treated as an operational cap when a model
    declaration exists, so a mistaken override cannot expand the architecture's
    declared limit. It becomes the source only when local metadata is absent.
    """
    if fallback_tokens <= 0:
        raise ValueError("MODEL_CONTEXT_FALLBACK_TOKENS must be positive")
    if override_tokens < 0:
        raise ValueError("MODEL_CONTEXT_WINDOW must not be negative")

    detected: Optional[Tuple[int, str]] = None
    model_dir = Path(model_path).expanduser()
    for filename in ("config.json", "tokenizer_config.json"):
        path = model_dir / filename
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, Mapping):
            match = detect_context_window(data)
            if match:
                detected = (match[0], f"{filename}:{match[1]}")
                break

    if detected:
        declared, source = detected
        if override_tokens > 0 and override_tokens < declared:
            return ContextWindowInfo(
                tokens=override_tokens,
                source=f"MODEL_CONTEXT_WINDOW cap over {source}",
                declared_tokens=declared,
            )
        return ContextWindowInfo(
            tokens=declared,
            source=source,
            declared_tokens=declared,
        )

    if override_tokens > 0:
        return ContextWindowInfo(
            tokens=override_tokens,
            source="MODEL_CONTEXT_WINDOW override (model metadata unavailable)",
        )
    return ContextWindowInfo(
        tokens=fallback_tokens,
        source="MODEL_CONTEXT_FALLBACK_TOKENS (model metadata unavailable)",
    )


def derive_context_budget(
    context_window_tokens: int,
    *,
    output_reserve_tokens: int,
    safety_tokens: int,
    compact_trigger_ratio: float,
    max_prompt_cap_tokens: int = 0,
    compact_trigger_cap_tokens: int = 0,
) -> ContextBudget:
    """Derive prompt limits without pretending a policy threshold is a fact."""
    if context_window_tokens <= 0:
        raise ValueError("model context window must be positive")
    if output_reserve_tokens <= 0:
        raise ValueError("MODEL_MAX_TOKENS must be positive")
    if safety_tokens <= 0:
        raise ValueError("CONTEXT_SAFETY_TOKENS must be positive")
    if not 0.0 < compact_trigger_ratio <= 1.0:
        raise ValueError("CONTEXT_COMPACT_TRIGGER_RATIO must be in (0, 1]")
    if max_prompt_cap_tokens < 0 or compact_trigger_cap_tokens < 0:
        raise ValueError("manual prompt limits must not be negative")

    available = context_window_tokens - output_reserve_tokens - safety_tokens
    if available < 1200:
        raise ValueError(
            "model context window leaves fewer than 1200 prompt tokens after "
            "generation and safety reserves"
        )

    max_prompt = min(available, max_prompt_cap_tokens) if max_prompt_cap_tokens else available
    if max_prompt < 1200:
        raise ValueError("MAX_PROMPT_TOKENS must be at least 1200")

    automatic_trigger = max(1, int(max_prompt * compact_trigger_ratio))
    if compact_trigger_cap_tokens > max_prompt:
        raise ValueError("COMPACT_TRIGGER_TOKENS must not exceed MAX_PROMPT_TOKENS")
    trigger = (
        min(automatic_trigger, compact_trigger_cap_tokens)
        if compact_trigger_cap_tokens
        else automatic_trigger
    )

    return ContextBudget(
        context_window_tokens=context_window_tokens,
        output_reserve_tokens=output_reserve_tokens,
        safety_tokens=safety_tokens,
        max_prompt_tokens=max_prompt,
        compact_trigger_tokens=trigger,
    )
