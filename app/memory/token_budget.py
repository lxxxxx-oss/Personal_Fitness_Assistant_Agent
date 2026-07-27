"""Small, dependency-free token budgeting helpers.

The estimate is deliberately conservative for Chinese prompts.  It is not a
tokenizer replacement; its job is to provide a stable guardrail before a
provider-specific tokenizer is available.
"""

from __future__ import annotations

import math
import re


_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_NON_CJK_UNIT_RE = re.compile(r"[A-Za-z0-9_]+|[^\w\s]", re.UNICODE)


def estimate_tokens(text: str) -> int:
    """Estimate mixed Chinese/English token usage without external packages."""
    if not text:
        return 0
    cjk_count = len(_CJK_RE.findall(text))
    non_cjk = _CJK_RE.sub(" ", text)
    other_count = 0
    for unit in _NON_CJK_UNIT_RE.findall(non_cjk):
        if unit.isalnum() or "_" in unit:
            other_count += max(1, math.ceil(len(unit) / 4))
        else:
            other_count += 1
    return cjk_count + other_count


def within_budget(text: str, *, max_chars: int, max_tokens: int) -> bool:
    """Return whether text satisfies both deterministic safety budgets."""
    return len(text) <= max_chars and estimate_tokens(text) <= max_tokens
