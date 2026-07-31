"""Risk and lifecycle policy for inferred user memory."""

from __future__ import annotations

from dataclasses import dataclass

from app.memory.memory_store import infer_privacy_level
from app.memory.models import MemoryRisk


@dataclass(frozen=True)
class MemoryPolicy:
    """Configurable thresholds; values are defaults, not claimed benchmarks."""

    auto_promotion_evidence: int = 2
    auto_promotion_conversations: int = 2
    auto_promotion_confidence: float = 0.82
    soft_memory_min_confidence: float = 0.62
    observation_ttl_days: int = 30

    def risk_for(self, content: str) -> MemoryRisk:
        privacy = infer_privacy_level(content)
        if privacy == "security":
            return MemoryRisk.SECRET
        if privacy == "health":
            return MemoryRisk.SENSITIVE
        return MemoryRisk.LOW

    def requires_confirmation(self, risk: MemoryRisk, *, has_conflict: bool) -> bool:
        return risk is MemoryRisk.SENSITIVE or has_conflict

    def can_auto_promote(
        self,
        *,
        risk: MemoryRisk,
        confidence: float,
        evidence_count: int,
        conversation_count: int,
        has_conflict: bool,
    ) -> bool:
        return (
            risk is MemoryRisk.LOW
            and not has_conflict
            and confidence >= self.auto_promotion_confidence
            and evidence_count >= self.auto_promotion_evidence
            and conversation_count >= self.auto_promotion_conversations
        )

