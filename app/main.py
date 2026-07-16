"""FastAPI application entry point — Fitness Assistant API."""
import logging
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional

import asyncio
from contextlib import suppress
from dataclasses import dataclass
import json
import os
import tempfile
import threading

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.api.schemas import (
    CandidateMemoryListResponse,
    CandidateMemoryResponse,
    ChatRequest,
    ChatResponse,
    ClearResponse,
    EmbeddingJobListResponse,
    EmbeddingJobProcessResponse,
    ExecutionTraceItem,
    HistoryResponse,
    MemoryCreateRequest,
    MemoryItemResponse,
    MemoryListResponse,
    MemoryUpdateRequest,
    MotionAnalyzeImageResponse,
    MotionAnalyzeResponse,
    MotionAnalyzeVideoResponse,
    MotionReferenceItem,
    MotionReferencesResponse,
)
from app.config import config
from app.graph.router import build_router_graph
from app.graph.state import RouterState, record_execution

if TYPE_CHECKING:
    from app.memory.sliding_window import SlidingWindowMemory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fitness Assistant API", version="0.1.0")

# CORS — allow browser access from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_router_graph = None
_sessions: Dict[str, "SlidingWindowMemory"] = {}
_conversation_store = None
_memory_store = None
_DEPENDENCY_LOCK = threading.Lock()
_SESSION_LOCK = threading.RLock()


async def _read_upload_with_limit(
    file: UploadFile,
    *,
    max_bytes: int,
    media_label: str,
) -> bytes:
    """Read one upload without buffering more than the documented limit."""
    chunks: List[bytes] = []
    total_bytes = 0
    while True:
        chunk = await file.read(min(1024 * 1024, max_bytes + 1 - total_bytes))
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"{media_label} file is too large, max {max_bytes} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _stream_llm_to_websocket(
    websocket: WebSocket,
    llm: Any,
    prompt: str,
) -> str:
    """Forward non-blocking LLM tokens to one WebSocket connection."""
    reply_parts: List[str] = []
    async for token in _iterate_llm_tokens(llm, prompt):
        reply_parts.append(token)
        await websocket.send_json({"type": "token", "text": token})
    return "".join(reply_parts)


async def _invoke_graph(graph: Any, state: RouterState) -> RouterState:
    """Run synchronous LangGraph work without blocking the asyncio loop."""
    return await asyncio.to_thread(graph.invoke, state)


async def _iterate_llm_tokens(llm: Any, prompt: str) -> AsyncIterator[str]:
    """Bridge a synchronous token generator to an async iterator."""
    queue: asyncio.Queue = asyncio.Queue()
    stop_requested = threading.Event()
    loop = asyncio.get_running_loop()

    def publish(kind: str, payload: Any = None) -> None:
        if loop.is_closed():
            return
        with suppress(RuntimeError):
            asyncio.run_coroutine_threadsafe(queue.put((kind, payload)), loop)

    def produce() -> None:
        try:
            for token in llm.generate_stream(prompt):
                if stop_requested.is_set():
                    break
                publish("token", token)
        except Exception as exc:
            publish("error", exc)
        finally:
            publish("done")

    producer_task = asyncio.create_task(asyncio.to_thread(produce))
    try:
        while True:
            kind, payload = await queue.get()
            if kind == "done":
                break
            if kind == "error":
                if isinstance(payload, BaseException):
                    raise payload
                raise RuntimeError(str(payload))
            token = str(payload)
            yield token
    finally:
        stop_requested.set()
        if producer_task.done():
            await producer_task
        else:
            producer_task.cancel()
            with suppress(asyncio.CancelledError):
                await producer_task


def _result_metadata(
    result_state: RouterState,
) -> tuple[List[str], List[str], List[Dict]]:
    """Return stable, deduplicated client metadata from graph state."""
    sources = list(dict.fromkeys(
        str(item) for item in result_state.get("_sources", []) if item
    ))
    warnings = list(dict.fromkeys(
        str(item)
        for item in result_state.get("_route_execution_warnings", [])
        if item
    ))
    execution = []
    for raw_item in result_state.get("_execution", []):
        item = {
            "component": str(raw_item.get("component", "unknown")),
            "mode": str(raw_item.get("mode", "unknown")),
            "degraded": bool(raw_item.get("degraded", False)),
            "detail": str(raw_item.get("detail", "")),
        }
        if item not in execution:
            execution.append(item)
    llm_item = {
        "component": "llm",
        "mode": "mock" if config.llm_mock else "local_qwen",
        "degraded": bool(config.llm_mock),
        "detail": "LLM demo mode configured" if config.llm_mock else "",
    }
    if llm_item not in execution:
        execution.append(llm_item)
    return sources, warnings, execution


def _get_router_graph():
    global _router_graph
    if _router_graph is None:
        with _DEPENDENCY_LOCK:
            if _router_graph is None:
                _router_graph = build_router_graph()
    return _router_graph


def _get_conversation_store():
    global _conversation_store
    if _conversation_store is None:
        with _DEPENDENCY_LOCK:
            if _conversation_store is None:
                from app.memory.conversation_store import ConversationStore

                _conversation_store = ConversationStore(config.memory_db_path)
    return _conversation_store


def _get_memory_store():
    global _memory_store
    if _memory_store is None:
        with _DEPENDENCY_LOCK:
            if _memory_store is None:
                from app.memory.memory_store import MemoryStore

                _memory_store = MemoryStore(
                    config.memory_db_path,
                    semantic_enabled=config.memory_milvus_enabled,
                )
    return _memory_store


def _remember_explicit_user_memory(user_id: str, message: str) -> None:
    try:
        _get_memory_store().remember_explicit(user_id, message)
    except ValueError:
        logger.warning("Explicit memory write skipped due to invalid content")
    except Exception:
        logger.exception("Explicit memory write failed")


def _retrieve_long_term_memories(user_id: str, message: str) -> List[Dict]:
    try:
        return _get_memory_store().search_memories(user_id, message, limit=5)
    except Exception:
        logger.exception("Long-term memory retrieval failed")
        return []


def _session_key(user_id: str, conversation_id: str) -> str:
    return f"{user_id}:{conversation_id}"


def _get_or_restore_memory(user_id: str, conversation_id: str):
    from app.memory.sliding_window import SlidingWindowMemory

    key = _session_key(user_id, conversation_id)
    with _SESSION_LOCK:
        if key not in _sessions:
            memory = SlidingWindowMemory(max_turns=config.memory_max_turns)
            for message in _get_conversation_store().get_messages(
                conversation_id,
                user_id,
            ):
                memory.add(message)
            _sessions[key] = memory
        return _sessions[key]


def _attach_conversation_summary(
    state: RouterState,
    user_id: str,
    conversation_id: str,
) -> None:
    """Load one active summary; failures preserve the existing chat path."""
    state["_conversation_summary"] = ""
    if not config.conversation_summary_enabled:
        return
    try:
        store = _get_conversation_store()
        summary = store.get_active_summary(
            conversation_id,
            user_id,
        )
        if summary:
            content = str(summary.get("content", ""))
            uncompacted = store.get_uncompacted_messages(conversation_id, user_id)
            recent_limit = max(1, int(config.memory_max_turns)) * 2
            state["_conversation_summary"] = content
            state["memory"] = [
                {"role": item["role"], "content": item["content"]}
                for item in uncompacted[-recent_limit:]
            ]
            record_execution(
                state,
                "conversation_summary",
                "loaded",
                detail=(
                    f"loaded persisted summary ({len(content)} chars) with "
                    f"{len(state['memory'])} uncompacted recent messages"
                ),
            )
    except Exception:
        state["_conversation_summary"] = ""
        logger.exception("Conversation summary load failed; using recent messages")
        record_execution(
            state,
            "conversation_summary",
            "recent_messages_fallback",
            degraded=True,
            detail="persisted summary unavailable",
        )


def _persist_conversation_turn(
    memory: Any,
    conversation_id: str,
    user_id: str,
    user_message: str,
    assistant_message: str,
) -> Dict[str, Any]:
    """Persist one turn and best-effort update its deterministic summary."""
    _get_conversation_store().add_turn(
        conversation_id,
        user_id,
        user_message,
        assistant_message,
    )
    memory.add_turn(user_message, assistant_message)
    _remember_explicit_user_memory(user_id, user_message)
    if not config.conversation_summary_enabled:
        return {"updated": False, "reason": "disabled"}
    try:
        from app.memory.conversation_summary import maybe_compact_conversation

        return maybe_compact_conversation(
            _get_conversation_store(),
            conversation_id,
            user_id,
            trigger_chars=config.conversation_summary_trigger_chars,
            keep_recent_messages=config.conversation_summary_keep_recent_messages,
            max_summary_chars=config.conversation_summary_max_chars,
        )
    except Exception as exc:
        logger.exception("Conversation summary update failed; turn remains persisted")
        return {
            "updated": False,
            "reason": "summary_error",
            "error": str(exc)[:200],
        }


def _resolve_conversation_id(user_id: str, conversation_id: Optional[str]) -> str:
    try:
        return _get_conversation_store().get_or_create_conversation(
            user_id,
            conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@dataclass
class PreparedChat:
    """Transport-neutral inputs required to execute one chat request."""

    user_id: str
    message: str
    conversation_id: str
    memory: Any
    state: RouterState


def _prepare_chat_sync(
    user_id: str,
    message: str,
    conversation_id: Optional[str],
    *,
    streaming: bool,
) -> PreparedChat:
    """Resolve persistence and build one shared RouterState."""
    resolved_id = _resolve_conversation_id(user_id, conversation_id)
    memory = _get_or_restore_memory(user_id, resolved_id)
    state: RouterState = {
        "user_input": message,
        "user_id": user_id,
        "conversation_id": resolved_id,
        "intent": "",
        "memory": memory.get_all(),
        "_long_term_memories": _retrieve_long_term_memories(user_id, message),
        "result": "",
        "error": None,
    }
    if streaming:
        state["_streaming"] = True
    _attach_conversation_summary(state, user_id, resolved_id)
    return PreparedChat(user_id, message, resolved_id, memory, state)


async def _prepare_chat(
    user_id: str,
    message: str,
    conversation_id: Optional[str],
    *,
    streaming: bool,
) -> PreparedChat:
    """Prepare chat state without blocking the event loop on SQLite/retrieval."""
    return await asyncio.to_thread(
        _prepare_chat_sync,
        user_id,
        message,
        conversation_id,
        streaming=streaming,
    )


async def _persist_prepared_chat(prepared: PreparedChat, reply: str) -> Dict[str, Any]:
    """Persist one successful complete turn outside the event loop."""
    return await asyncio.to_thread(
        _persist_conversation_turn,
        prepared.memory,
        prepared.conversation_id,
        prepared.user_id,
        prepared.message,
        reply,
    )


def _create_llm():
    from app.llm.loader import LLMLoader

    return LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=config.model_max_tokens,
        temperature=config.model_temperature,
        top_p=config.model_top_p,
    )


def _sse_event(event: str, payload: Dict[str, Any]) -> str:
    """Encode one SSE event as a single JSON data record."""
    return (
        f"event: {event}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


# --- API Endpoints ---

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/memory", response_model=MemoryListResponse)
def list_memories(
    user_id: str,
    kind: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = 50,
):
    """List long-term memories for one user."""
    try:
        memories = _get_memory_store().list_memories(
            user_id,
            kind=kind,
            include_deleted=include_deleted,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MemoryListResponse(user_id=user_id, memories=memories)


@app.post("/memory", response_model=MemoryItemResponse)
def create_memory(request: MemoryCreateRequest):
    """Create one explicit long-term memory."""
    try:
        return _get_memory_store().create_memory(
            user_id=request.user_id,
            kind=request.kind,
            content=request.content,
            scope=request.scope,
            source_type=request.source_type,
            importance=request.importance,
            metadata=request.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/memory/search", response_model=MemoryListResponse)
def search_memories(user_id: str, query: str, limit: int = 5):
    """Search active long-term memories using SQLite FTS5 with LIKE fallback."""
    memories = _get_memory_store().search_memories(user_id, query, limit=limit)
    return MemoryListResponse(user_id=user_id, memories=memories)


@app.get("/memory/candidates", response_model=CandidateMemoryListResponse)
def list_candidate_memories(
    user_id: str,
    status: str = "pending",
    limit: int = 50,
):
    """List candidate memories waiting for confirmation."""
    try:
        candidates = _get_memory_store().list_candidate_memories(
            user_id,
            status=status,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CandidateMemoryListResponse(user_id=user_id, candidates=candidates)


@app.post("/memory/candidates/{candidate_id}/confirm", response_model=MemoryItemResponse)
def confirm_candidate_memory(candidate_id: str, user_id: str):
    """Confirm one candidate memory and promote it into memory_items."""
    item = _get_memory_store().confirm_candidate_memory(user_id, candidate_id)
    if item is None:
        raise HTTPException(status_code=404, detail="candidate memory was not found")
    return item


@app.post("/memory/candidates/{candidate_id}/reject")
def reject_candidate_memory(candidate_id: str, user_id: str):
    """Reject one candidate memory."""
    rejected = _get_memory_store().reject_candidate_memory(user_id, candidate_id)
    if not rejected:
        raise HTTPException(status_code=404, detail="candidate memory was not found")
    return {"id": candidate_id, "status": "rejected"}


@app.get("/memory/embedding-jobs", response_model=EmbeddingJobListResponse)
def list_memory_embedding_jobs(status: str = "pending", limit: int = 50):
    """List memory embedding jobs for the optional Milvus sync worker."""
    try:
        jobs = _get_memory_store().list_embedding_jobs(status=status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EmbeddingJobListResponse(jobs=jobs)


@app.post("/memory/embedding-jobs/process", response_model=EmbeddingJobProcessResponse)
def process_memory_embedding_jobs(limit: int = 20):
    """Process pending memory embedding jobs synchronously for local demos/tests."""
    result = _get_memory_store().process_embedding_jobs(limit=limit)
    return EmbeddingJobProcessResponse(**result)


@app.get("/memory/{memory_id}", response_model=MemoryItemResponse)
def get_memory(memory_id: str, user_id: str):
    """Read one long-term memory by id."""
    item = _get_memory_store().get_memory(user_id, memory_id)
    if item is None:
        raise HTTPException(status_code=404, detail="memory was not found")
    return item


@app.patch("/memory/{memory_id}", response_model=MemoryItemResponse)
def update_memory(memory_id: str, request: MemoryUpdateRequest):
    """Update one long-term memory."""
    updates = request.model_dump(exclude_none=True)
    updates.pop("user_id", None)
    try:
        item = _get_memory_store().update_memory(
            user_id=request.user_id,
            memory_id=memory_id,
            updates=updates,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="memory was not found")
    return item


@app.delete("/memory/{memory_id}")
def delete_memory(memory_id: str, user_id: str):
    """Logically delete one long-term memory."""
    deleted = _get_memory_store().delete_memory(user_id, memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="memory was not found")
    return {"id": memory_id, "status": "deleted"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process user message, route to subgraph, return reply."""
    try:
        prepared = await _prepare_chat(
            request.user_id,
            request.message,
            request.conversation_id,
            streaming=False,
        )
        graph = _get_router_graph()
        result_state = await _invoke_graph(graph, prepared.state)

        reply = result_state.get("result", "")
        if not isinstance(reply, str) or not reply.strip():
            raise RuntimeError("chat graph completed without reply text")
        intent = result_state.get("intent", "chat")
        summary_result = await _persist_prepared_chat(prepared, reply)
        if summary_result.get("updated"):
            record_execution(
                result_state,
                "conversation_summary",
                "deterministic_extractive",
                detail=(
                    f"compacted {summary_result['compacted_message_count']} messages; "
                    f"kept {summary_result['remaining_message_count']} recent messages"
                ),
            )
        sources, warnings, execution = _result_metadata(result_state)

        return ChatResponse(
            user_id=request.user_id,
            conversation_id=prepared.conversation_id,
            intent=intent,
            reply=reply,
            sources=sources,
            warnings=warnings,
            execution=execution,
        )
    except HTTPException:
        raise
    except Exception as exc:
        from app.llm.loader import LLMGenerationError

        logger.exception("Error processing chat")
        if isinstance(exc, LLMGenerationError):
            raise HTTPException(
                status_code=503,
                detail={"code": exc.error_code, "message": exc.public_message},
            ) from exc
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "Chat request failed."},
        ) from exc


@app.get("/chat/{user_id}/history", response_model=HistoryResponse)
async def get_history(user_id: str):
    """Get user conversation history."""
    conversation_id = await asyncio.to_thread(
        _get_conversation_store().get_latest_active_conversation,
        user_id,
    )
    if conversation_id is None:
        return HistoryResponse(user_id=user_id, conversation_id=None, history=[])
    memory = await asyncio.to_thread(_get_or_restore_memory, user_id, conversation_id)
    return HistoryResponse(
        user_id=user_id,
        conversation_id=conversation_id,
        history=memory.get_all(),
    )


@app.delete("/chat/{user_id}/history", response_model=ClearResponse)
async def clear_history(user_id: str):
    """Clear user conversation history."""
    store = _get_conversation_store()
    conversation_id = await asyncio.to_thread(
        store.get_latest_active_conversation,
        user_id,
    )
    await asyncio.to_thread(store.archive_user_conversations, user_id)
    with _SESSION_LOCK:
        for key in list(_sessions.keys()):
            if key.startswith(f"{user_id}:") or key == user_id:
                _sessions[key].clear()
                _sessions.pop(key, None)
    return ClearResponse(
        user_id=user_id,
        conversation_id=conversation_id,
        status="cleared",
    )


@app.post("/motion/analyze", response_model=MotionAnalyzeResponse)
async def analyze_motion(
    file: UploadFile = File(...),
    reference_name: str | None = Form(default=None),
):
    """Analyze an uploaded .npz pose file.

    This endpoint uses deterministic motion tools only. It does not call the
    LLM, so uploaded motion analysis can run without loading the local model.
    """
    from app.tools.motion_tool import compute_similarity, list_motion_library, load_npz_pose

    if not file.filename or not file.filename.lower().endswith(".npz"):
        raise HTTPException(status_code=422, detail="Only .npz pose files are supported")

    suffix = os.path.splitext(file.filename)[1] or ".npz"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)

        pose_result = await asyncio.to_thread(load_npz_pose, tmp_path)
        if not pose_result.ok:
            raise HTTPException(
                status_code=422,
                detail=pose_result.error_message or "Invalid pose file",
            )

        pose = pose_result.data
        response = MotionAnalyzeResponse(
            filename=file.filename,
            frames=int(pose.shape[0]),
            joints=int(pose.shape[1]),
            message=(
                "姿态数据已加载。未提供 reference_name，当前仅返回基础信息；"
                "如需标准动作对比，请在 data/motions/ 中准备同名 .npz 并传入 reference_name。"
            ),
        )

        if reference_name:
            library_result = await asyncio.to_thread(
                list_motion_library,
                config.motion_library_dir,
            )
            library = library_result.data if library_result.ok else {}
            ref_path = library.get(reference_name)
            if ref_path is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Reference motion not found: {reference_name}",
                )

            ref_result = await asyncio.to_thread(load_npz_pose, ref_path)
            if not ref_result.ok:
                raise HTTPException(
                    status_code=422,
                    detail=ref_result.error_message or "Invalid reference pose file",
                )

            metrics_result = await asyncio.to_thread(
                compute_similarity,
                pose,
                ref_result.data,
            )
            if not metrics_result.ok:
                raise HTTPException(
                    status_code=422,
                    detail=metrics_result.error_message or "Motion comparison failed",
                )

            response.reference = reference_name
            response.metrics = metrics_result.data
            response.message = "姿态数据已加载，并完成与标准动作的相似度对比。"

        return response
    finally:
        await file.close()
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/motion/analyze-image", response_model=MotionAnalyzeImageResponse)
async def analyze_motion_image(file: UploadFile = File(...)):
    """Analyze an uploaded image as a single-frame static posture.

    This endpoint extracts pose landmarks and returns a posture summary. A
    single image cannot assess full motion timing, trajectory, or repetition
    stability.
    """
    from app.tools.pose_estimator import (
        MAX_IMAGE_BYTES,
        decode_image_bytes_to_rgb,
        estimate_pose_from_image,
    )
    from app.tools.types import ErrorCode

    if not file.filename:
        raise HTTPException(status_code=422, detail="Image filename is required")

    try:
        content = await _read_upload_with_limit(
            file,
            max_bytes=MAX_IMAGE_BYTES,
            media_label="Image",
        )
        image_result = await asyncio.to_thread(
            decode_image_bytes_to_rgb,
            content,
            filename=file.filename,
        )
        if not image_result.ok:
            status_code = 503 if image_result.error_code == ErrorCode.CONFIG_MISSING else 422
            raise HTTPException(
                status_code=status_code,
                detail=image_result.error_message or "Invalid image file",
            )

        pose_result = await asyncio.to_thread(
            estimate_pose_from_image,
            image_result.data,
            source_name=file.filename,
        )
        if not pose_result.ok:
            status_code = 503 if pose_result.error_code == ErrorCode.CONFIG_MISSING else 422
            raise HTTPException(
                status_code=status_code,
                detail=pose_result.error_message or "Pose estimation failed",
            )

        sequence = pose_result.data
        confidence_summary = None
        warnings = [
            "单张图片只能分析静态姿态，不能判断动作节奏、轨迹或发力顺序。"
        ]
        if sequence.confidence is not None:
            confidence = sequence.confidence.astype(float)
            confidence_summary = {
                "mean": round(float(confidence.mean()), 4),
                "min": round(float(confidence.min()), 4),
                "max": round(float(confidence.max()), 4),
            }
            if confidence_summary["mean"] < 0.5:
                warnings.append("关键点整体置信度较低，建议更换清晰、无遮挡的图片。")

        return MotionAnalyzeImageResponse(
            filename=file.filename,
            source_type=sequence.source_type,
            frames=sequence.frames,
            joints=sequence.joints,
            pose_model=sequence.pose_model,
            joint_schema=sequence.joint_schema,
            confidence_summary=confidence_summary,
            warnings=warnings,
            execution=[
                ExecutionTraceItem(
                    component="motion",
                    mode="mediapipe_image",
                    degraded=False,
                    detail="",
                )
            ],
            message=(
                "图片姿态已提取为 PoseSequence。当前返回静态姿态摘要；"
                "完整动作标准性判断需要视频序列或标准动作库对比。"
            ),
        )
    finally:
        await file.close()


@app.get("/motion/references", response_model=MotionReferencesResponse)
def list_motion_references():
    """List standard references and whether they match the video pose schema."""
    from app.tools.motion_tool import list_motion_library, load_npz_pose_sequence

    library_result = list_motion_library(config.motion_library_dir)
    library = library_result.data if library_result.ok else {}
    references = []
    for name, path in library.items():
        loaded = load_npz_pose_sequence(path)
        if not loaded.ok:
            references.append(
                MotionReferenceItem(name=name, reason="Invalid PoseSequence file")
            )
            continue
        sequence = loaded.data
        compatible = (
            sequence.pose_model == "mediapipe_pose"
            and sequence.joint_schema == "mediapipe_33"
            and sequence.joints == 33
        )
        references.append(
            MotionReferenceItem(
                name=name,
                frames=sequence.frames,
                joints=sequence.joints,
                pose_model=sequence.pose_model,
                joint_schema=sequence.joint_schema,
                coordinate_space=str(
                    sequence.metadata.get("coordinate_space") or "unknown"
                ),
                compatible_with_video=compatible,
                reason=(
                    ""
                    if compatible
                    else "Reference must use mediapipe_pose / mediapipe_33"
                ),
            )
        )
    return MotionReferencesResponse(references=references)


@app.post("/motion/analyze-video", response_model=MotionAnalyzeVideoResponse)
async def analyze_motion_video(
    file: UploadFile = File(...),
    reference_name: str | None = Form(None),
):
    """Extract a bounded multi-frame pose sequence from an uploaded video."""
    from app.tools.pose_estimator import (
        MAX_VIDEO_BYTES,
        SUPPORTED_VIDEO_SUFFIXES,
        estimate_pose_from_video_path,
    )
    from app.tools.motion_tool import (
        compute_pose_sequence_similarity,
        list_motion_library,
        load_npz_pose_sequence,
    )
    from app.tools.types import ErrorCode

    if not file.filename:
        raise HTTPException(status_code=422, detail="Video filename is required")
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in SUPPORTED_VIDEO_SUFFIXES:
        raise HTTPException(
            status_code=422,
            detail="Only .mp4, .mov, and .avi videos are supported",
        )

    tmp_path = None
    total_bytes = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_VIDEO_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Video file is too large, max {MAX_VIDEO_BYTES} bytes",
                    )
                tmp.write(chunk)

        pose_result = await asyncio.to_thread(
            estimate_pose_from_video_path,
            tmp_path,
            source_name=file.filename,
        )
        if not pose_result.ok:
            status_code = 503 if pose_result.error_code == ErrorCode.CONFIG_MISSING else 422
            raise HTTPException(
                status_code=status_code,
                detail=pose_result.error_message or "Video pose estimation failed",
            )

        sequence = pose_result.data
        metadata = sequence.metadata
        confidence_summary = None
        if sequence.confidence is not None:
            confidence = sequence.confidence.astype(float)
            confidence_summary = {
                "mean": round(float(confidence.mean()), 4),
                "min": round(float(confidence.min()), 4),
                "max": round(float(confidence.max()), 4),
            }
        valid_frame_ratio = float(metadata.get("valid_frame_ratio", 0.0))
        warnings = []
        if valid_frame_ratio < 0.8:
            warnings.append("有效姿态帧比例较低，建议使用单人、无遮挡、固定机位视频。")

        reference = None
        metrics = None
        execution_mode = "mediapipe_video"
        if reference_name and reference_name.strip():
            normalized_reference = reference_name.strip()
            if len(normalized_reference) > 64:
                raise HTTPException(status_code=422, detail="reference_name is too long")
            library_result = await asyncio.to_thread(
                list_motion_library,
                config.motion_library_dir,
            )
            library = library_result.data if library_result.ok else {}
            reference_path = library.get(normalized_reference)
            if reference_path is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Reference motion not found: {normalized_reference}",
                )
            reference_result = await asyncio.to_thread(
                load_npz_pose_sequence,
                reference_path,
            )
            if not reference_result.ok:
                raise HTTPException(
                    status_code=422,
                    detail=reference_result.error_message or "Invalid reference motion",
                )
            similarity_result = await asyncio.to_thread(
                compute_pose_sequence_similarity,
                sequence,
                reference_result.data,
            )
            if not similarity_result.ok:
                raise HTTPException(
                    status_code=422,
                    detail=similarity_result.error_message
                    or "Motion similarity comparison failed",
                )
            reference = normalized_reference
            metrics = similarity_result.data
            execution_mode = "mediapipe_video_similarity"
            warnings.append(
                "相似度仅表示与所选标准样本的统计接近程度，不等同于专业教练的动作质量诊断。"
            )
            quality = metrics.get("quality") if isinstance(metrics, dict) else None
            if isinstance(quality, dict) and quality.get("accepted") is False:
                warnings.append(
                    "关键点有效对齐比例低于质量门控阈值，本次相似度仅作低置信参考，建议重新拍摄后再判断。"
                )
        else:
            warnings.append(
                "未选择标准动作，本次仅提取多帧 PoseSequence，不执行相似度评分。"
            )

        return MotionAnalyzeVideoResponse(
            filename=file.filename,
            source_type=sequence.source_type,
            frames=sequence.frames,
            joints=sequence.joints,
            fps=round(float(sequence.fps or 0.0), 4),
            pose_model=sequence.pose_model,
            joint_schema=sequence.joint_schema,
            sampled_frames=int(metadata.get("sampled_frames", sequence.frames)),
            valid_frame_ratio=round(valid_frame_ratio, 4),
            confidence_summary=confidence_summary,
            reference=reference,
            metrics=metrics,
            warnings=warnings,
            execution=[
                ExecutionTraceItem(
                    component="motion",
                    mode=execution_mode,
                    degraded=False,
                    detail="",
                )
            ],
            message=(
                "视频已转换为 PoseSequence，并完成与标准动作的相似度分析。"
                if metrics is not None
                else "视频已转换为多帧 PoseSequence。"
            ),
        )
    finally:
        await file.close()
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat: SSE token-by-token output."""
    prepared = await _prepare_chat(
        request.user_id,
        request.message,
        request.conversation_id,
        streaming=True,
    )

    async def event_stream():
        try:
            graph = _get_router_graph()
            result_state = await _invoke_graph(graph, prepared.state)
            prompt = result_state.get("_prompt", "")
            intent = result_state.get("intent", "chat")
            sources, warnings, execution = _result_metadata(result_state)
            yield _sse_event("meta", {
                "conversation_id": prepared.conversation_id,
                "intent": intent,
                "sources": sources,
                "warnings": warnings,
                "execution": execution,
            })

            if not prompt:
                fallback = result_state.get(
                    "result",
                    "Sorry, I couldn't process that.",
                )
                yield _sse_event("token", {"text": fallback})
                await _persist_prepared_chat(prepared, fallback)
                yield _sse_event("done", {})
                return

            full_reply = ""
            llm = _create_llm()
            async for token in _iterate_llm_tokens(llm, prompt):
                full_reply += token
                yield _sse_event("token", {"text": token})
            if not full_reply.strip():
                raise RuntimeError("LLM stream completed without reply text")
            await _persist_prepared_chat(prepared, full_reply)
            yield _sse_event("done", {})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            from app.llm.loader import LLMGenerationError

            logger.exception("SSE chat stream failed")
            code = (
                exc.error_code
                if isinstance(exc, LLMGenerationError)
                else "STREAM_ERROR"
            )
            message = (
                exc.public_message
                if isinstance(exc, LLMGenerationError)
                else "Streaming chat failed."
            )
            yield _sse_event("error", {"code": code, "message": message})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.websocket("/chat/ws")
async def chat_websocket(websocket: WebSocket):
    """WebSocket streaming chat — token-by-token via WS protocol.

    Protocol:
      Client → Server:  {"user_id": "...", "message": "..."}
      Server → Client:  {"type": "meta", "intent": "chat"}
      Server → Client:  {"type": "token", "text": "你"}
      Server → Client:  {"type": "token", "text": "好"}
      Server → Client:  {"type": "done"}
      Server → Client:  {"type": "error", "code": "...", "message": "..."}
    """
    await websocket.accept()
    logger.info("WebSocket connected")

    try:
        # Wait for client message
        raw = await websocket.receive_text()
        data = json.loads(raw)
        try:
            request = ChatRequest.model_validate(data)
        except ValidationError:
            await websocket.send_json({
                "type": "error",
                "code": "INVALID_REQUEST",
                "message": (
                    "user_id must be a 1-64 character string and message must "
                    "be a 1-4096 character string"
                ),
            })
            await websocket.close()
            return
        try:
            prepared = await _prepare_chat(
                request.user_id,
                request.message,
                request.conversation_id,
                streaming=True,
            )
        except HTTPException as exc:
            await websocket.send_json({
                "type": "error",
                "code": "CONVERSATION_NOT_FOUND",
                "message": str(exc.detail),
            })
            await websocket.close()
            return

        # Step 1: Run graph to build context + get prompt
        graph = _get_router_graph()
        result_state = await _invoke_graph(graph, prepared.state)
        prompt = result_state.get("_prompt", "")
        intent = result_state.get("intent", "chat")
        sources, warnings, execution = _result_metadata(result_state)

        # Send metadata
        await websocket.send_json({
            "type": "meta",
            "conversation_id": prepared.conversation_id,
            "intent": intent,
            "sources": sources,
            "warnings": warnings,
            "execution": execution,
        })

        if not prompt:
            # No prompt — graph couldn't prepare context, send result directly
            fallback = result_state.get("result", "Sorry, I couldn't process that.")
            await websocket.send_json({"type": "token", "text": fallback})
            await websocket.send_json({"type": "done"})
            await _persist_prepared_chat(prepared, fallback)
            await websocket.close()
            return

        # Step 2: Stream LLM tokens via WebSocket
        # Bridge sync generation through an async queue so each token is sent
        # as soon as it is produced without blocking the event loop.
        llm = _create_llm()
        full_reply = await _stream_llm_to_websocket(websocket, llm, prompt)
        if not full_reply.strip():
            raise RuntimeError("LLM stream completed without reply text")

        # Persist before declaring success so "done" has a stable meaning.
        await _persist_prepared_chat(prepared, full_reply)
        await websocket.send_json({"type": "done"})
        logger.info(f"WebSocket stream complete: {len(full_reply)} chars, intent={intent}")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected by client")
    except json.JSONDecodeError:
        await websocket.send_json({
            "type": "error",
            "code": "INVALID_JSON",
            "message": "Invalid JSON",
        })
    except Exception as exc:
        from app.llm.loader import LLMGenerationError

        logger.exception("WebSocket error")
        code = (
            exc.error_code
            if isinstance(exc, LLMGenerationError)
            else "STREAM_ERROR"
        )
        message = (
            exc.public_message
            if isinstance(exc, LLMGenerationError)
            else "WebSocket chat failed."
        )
        try:
            await websocket.send_json({"type": "error", "code": code, "message": message})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# Static files — serve the web UI
import os
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/ui", StaticFiles(directory=static_dir, html=True), name="static")
