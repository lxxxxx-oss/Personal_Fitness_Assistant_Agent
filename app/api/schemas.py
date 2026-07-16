"""Pydantic request and response models shared by API transports."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ExecutionTraceItem(BaseModel):
    component: str
    mode: str
    degraded: bool = False
    detail: str = ""


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=4096)
    conversation_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


class ChatResponse(BaseModel):
    user_id: str
    conversation_id: str
    intent: str
    reply: str
    sources: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    execution: List[ExecutionTraceItem] = Field(default_factory=list)


class HistoryResponse(BaseModel):
    user_id: str
    conversation_id: Optional[str] = None
    history: List[Dict[str, str]]


class ClearResponse(BaseModel):
    user_id: str
    conversation_id: Optional[str] = None
    status: str


class MemoryCreateRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    kind: str = Field(default="note", min_length=1, max_length=32)
    content: str = Field(..., min_length=1, max_length=2000)
    scope: str = Field(default="global", min_length=1, max_length=128)
    source_type: str = Field(default="manual_import", min_length=1, max_length=64)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: Dict = Field(default_factory=dict)


class MemoryUpdateRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    kind: Optional[str] = Field(default=None, min_length=1, max_length=32)
    content: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    scope: Optional[str] = Field(default=None, min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: Optional[str] = Field(default=None, min_length=1, max_length=32)
    metadata: Optional[Dict] = None


class MemoryItemResponse(BaseModel):
    id: str
    user_id: str
    kind: str
    content: str
    scope: str
    source_type: str
    importance: float
    status: str
    access_count: int
    last_accessed_at: Optional[str] = None
    memory_key: str
    metadata: Dict = Field(default_factory=dict)
    created_at: str
    updated_at: str
    deduplicated: bool = False
    score: Optional[float] = None


class MemoryListResponse(BaseModel):
    user_id: str
    memories: List[MemoryItemResponse] = Field(default_factory=list)


class CandidateMemoryResponse(BaseModel):
    id: str
    user_id: str
    kind: str
    content: str
    scope: str
    source_type: str
    importance: float
    privacy_level: str
    status: str
    metadata: Dict = Field(default_factory=dict)
    created_at: str
    updated_at: str
    candidate: bool = False


class CandidateMemoryListResponse(BaseModel):
    user_id: str
    candidates: List[CandidateMemoryResponse] = Field(default_factory=list)


class EmbeddingJobResponse(BaseModel):
    id: str
    memory_id: str
    user_id: str
    status: str
    attempts: int
    last_error: Optional[str] = None
    next_run_at: str
    created_at: str
    updated_at: str


class EmbeddingJobListResponse(BaseModel):
    jobs: List[EmbeddingJobResponse] = Field(default_factory=list)


class EmbeddingJobProcessResponse(BaseModel):
    processed: int
    completed: int
    failed: int
    enabled: bool


class MotionAnalyzeResponse(BaseModel):
    filename: str
    frames: int
    joints: int
    reference: str | None = None
    metrics: dict | None = None
    message: str


class MotionAnalyzeImageResponse(BaseModel):
    filename: str
    source_type: str
    frames: int
    joints: int
    pose_model: str
    joint_schema: str
    confidence_summary: dict | None = None
    warnings: List[str] = Field(default_factory=list)
    execution: List[ExecutionTraceItem] = Field(default_factory=list)
    message: str


class MotionAnalyzeVideoResponse(BaseModel):
    filename: str
    source_type: str
    frames: int
    joints: int
    fps: float
    pose_model: str
    joint_schema: str
    sampled_frames: int
    valid_frame_ratio: float
    confidence_summary: dict | None = None
    reference: str | None = None
    metrics: dict | None = None
    warnings: List[str] = Field(default_factory=list)
    execution: List[ExecutionTraceItem] = Field(default_factory=list)
    message: str


class MotionReferenceItem(BaseModel):
    name: str
    frames: int | None = None
    joints: int | None = None
    pose_model: str = "unknown"
    joint_schema: str = "unknown"
    coordinate_space: str = "unknown"
    compatible_with_video: bool = False
    reason: str = ""


class MotionReferencesResponse(BaseModel):
    references: List[MotionReferenceItem] = Field(default_factory=list)
