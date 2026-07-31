"""Shared domain constants for the layered memory system."""

from __future__ import annotations

from enum import Enum


class MemoryRisk(str, Enum):
    LOW = "low"
    SENSITIVE = "sensitive"
    SECRET = "secret"


class ObservationStatus(str, Enum):
    OBSERVED = "observed"
    REVIEW_REQUIRED = "review_required"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class EvidencePolarity(str, Enum):
    SUPPORT = "support"
    CONTRADICT = "contradict"


class MemoryEventType(str, Enum):
    CAPTURE = "capture"
    REINFORCE = "reinforce"
    PROMOTE = "promote"
    CONFIRM = "confirm"
    REJECT = "reject"
    EDIT = "edit"
    DELETE = "delete"
    SUPERSEDE = "supersede"
    EXPIRE = "expire"
    UNDO = "undo"

