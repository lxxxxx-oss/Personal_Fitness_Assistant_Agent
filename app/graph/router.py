"""Top-level router graph: intent classification + conditional dispatch."""
import json
import logging
import re
import threading
import time
from collections import Counter
from typing import Any, Dict, List, Literal, NotRequired, Optional, Sequence, Tuple, TypedDict

from langgraph.graph import END, StateGraph

from app.graph.prompt_builder import PromptBuilder
from app.graph.safety_policy import (
    SAFETY_POLICY_VERSION,
    compose_safe_prompt,
    validate_public_output,
)
from app.graph.state import RouterState, record_execution
from app.graph.structured_state import add_decision, ensure_structured_state, set_task
from app.graph.subgraphs.chat import build_chat_subgraph
from app.graph.subgraphs.diet import build_diet_subgraph
from app.graph.subgraphs.mcp import build_mcp_subgraph
from app.graph.subgraphs.motion import build_motion_subgraph
from app.graph.subgraphs.search import build_search_subgraph

logger = logging.getLogger(__name__)

Intent = Literal["search", "motion", "diet", "chat", "mcp"]


class RouteDecision(TypedDict):
    """Structured router decision for debugging and evaluation."""

    intent: Intent
    confidence: float
    reason: str
    source: str
    scores: Dict[str, float]
    matches: List[str]
    ambiguity_signals: NotRequired[List[str]]
    primary_intent: NotRequired[Intent]
    secondary_intents: NotRequired[List[Intent]]
    route_plan: NotRequired[List[Intent]]
    multi_intent_reason: NotRequired[str]
    needs_clarification: NotRequired[bool]
    clarification_candidates: NotRequired[List[Intent]]
    clarification_question: NotRequired[str]


_LLM_ROUTER_METRICS_LOCK = threading.Lock()
_LLM_ROUTER_OUTCOMES: Counter[str] = Counter()
_LLM_ROUTER_SELECTIONS: Counter[str] = Counter()
_LLM_ROUTER_TOTAL_LATENCY_MS = 0.0
_LLM_ROUTER_MAX_LATENCY_MS = 0.0
_EMBEDDING_ROUTER_LOCK = threading.Lock()
_EMBEDDING_ROUTER_MODEL: Any = None
_EMBEDDING_ROUTER_MODEL_NAME = ""
_EMBEDDING_EXAMPLE_VECTORS: Dict[str, List[Tuple[Intent, str, Sequence[float]]]] = {}


WEIGHTED_RULES: Dict[Intent, List[Tuple[str, float]]] = {
    "search": [
        ("搜索", 6.0),
        ("查一下", 6.0),
        ("查一查", 6.0),
        ("联网", 5.0),
        ("最新", 4.5),
        ("新闻", 4.5),
        ("热点", 4.0),
        ("资讯", 3.5),
        ("研究", 3.0),
        ("最近", 1.5),
        ("搜一下", 6.0),
        ("找一下", 6.0),
        ("找一找", 6.0),
        ("权威说法", 5.0),
        ("权威机构", 5.0),
        ("search", 6.0),
        ("latest", 4.5),
        ("recent", 3.5),
        ("news", 4.5),
    ],
    "motion": [
        (".npz", 8.0),
        ("动作分析", 7.0),
        ("姿势", 5.0),
        ("姿态", 5.0),
        ("动作", 3.5),
        ("深蹲", 4.0),
        ("硬拉", 4.0),
        ("卧推", 4.0),
        ("划船", 4.0),
        ("膝盖内扣", 4.0),
        ("哪里不对", 4.0),
        ("analyze", 5.0),
        ("pose", 4.0),
        ("posture", 4.0),
    ],
    "diet": [
        ("减脂", 5.0),
        ("减重", 4.0),
        ("增肌", 5.0),
        ("吃什么", 5.0),
        ("怎么吃", 5.0),
        ("饮食", 5.0),
        ("食谱", 4.0),
        ("营养", 4.0),
        ("热量", 4.0),
        ("碳水", 3.5),
        ("蛋白质摄入", 4.0),
        ("高蛋白", 3.5),
        ("吃多少蛋白质", 5.0),
        ("多少蛋白质", 4.5),
        ("瘦一点", 5.0),
        ("变瘦", 4.0),
        ("有点胖", 4.0),
        ("改善体型", 5.0),
        ("体型", 3.0),
        ("控制体重", 5.0),
        ("体重管理", 5.0),
        ("吃得健康", 4.0),
        ("吃得清淡", 4.0),
        ("调整得更轻盈", 5.0),
        ("三餐", 3.0),
        ("healthy diet", 5.0),
        ("lose weight", 5.0),
        ("bulk", 4.0),
    ],
    "mcp": [
        ("菜谱", 6.0),
        ("烹饪", 5.0),
        ("做法", 5.0),
        ("步骤", 3.5),
        ("怎么做", 3.0),
        ("番茄炒蛋", 6.0),
        ("红烧肉", 6.0),
        ("炒蛋", 4.0),
        ("晚餐推荐", 5.0),
        ("晚饭", 3.0),
        ("做什么菜", 4.0),
        ("高蛋白菜", 5.0),
        ("菜", 2.0),
        ("晚餐", 3.0),
        ("低脂晚餐", 5.0),
        ("高蛋白晚餐", 5.0),
        ("鸡胸肉", 4.0),
        ("沙拉", 3.0),
        ("recipe", 6.0),
        ("cook", 5.0),
    ],
    "chat": [
        ("是什么", 5.0),
        ("什么是", 5.0),
        ("为什么", 7.0),
        ("有什么作用", 6.0),
        ("有哪些好处", 5.0),
        ("好处", 3.5),
        ("原理", 4.0),
        ("概念", 4.0),
        ("训练计划", 5.0),
        ("训练建议", 4.0),
        ("怎么练", 4.0),
        ("练点什么", 4.0),
        ("不需要器械", 4.0),
        ("不知道该问", 5.0),
        ("先给我个建议", 4.0),
        ("练什么动作", 5.0),
        ("应该练什么动作", 6.0),
        ("体重没变", 5.0),
        ("训练没效果", 4.0),
        ("讲原理", 6.0),
        ("what is", 5.0),
    ],
}

COMBO_RULES: List[Tuple[Intent, Tuple[str, ...], float, str]] = [
    ("search", ("最近", "新闻"), 5.0, "recent news"),
    ("search", ("最近", "研究"), 5.0, "recent research"),
    ("search", ("最新", "研究"), 5.0, "latest research"),
    ("search", ("搜索", "研究"), 3.0, "explicit search research"),
    ("search", ("查一下", "动作"), 5.0, "explicit search for movement info"),
    ("search", ("查一下", "深蹲"), 4.0, "explicit search for squat info"),
    ("search", ("最近", "权威"), 7.0, "recent authoritative information"),
    ("search", ("有没有", "研究"), 5.0, "research lookup"),
    ("search", ("有没有", "权威"), 7.0, "authoritative lookup"),
    ("search", ("找一找", "训练计划"), 6.0, "explicit plan lookup"),
    ("diet", ("最近", "瘦"), 5.0, "recent weight-loss intent"),
    ("diet", ("想", "瘦"), 4.0, "weight-loss goal"),
    ("diet", ("改善", "体型"), 5.0, "body composition goal"),
    ("diet", ("控制", "体重"), 5.0, "weight management"),
    ("diet", ("减脂", "吃"), 4.0, "diet goal with food"),
    ("diet", ("增肌", "吃"), 4.0, "muscle-gain diet"),
    ("diet", ("怎么", "吃"), 4.0, "food planning"),
    ("diet", ("蛋白质", "多少"), 5.0, "protein intake amount"),
    ("motion", ("深蹲", "姿势"), 5.0, "squat posture"),
    ("motion", ("深蹲", "哪里不对"), 5.0, "squat issue"),
    ("motion", ("硬拉", "姿势"), 5.0, "deadlift posture"),
    ("motion", ("帮我看看", "深蹲"), 4.0, "squat review"),
    ("motion", ("动作", "分析"), 5.0, "motion analysis"),
    ("mcp", ("怎么做", "番茄"), 5.0, "cooking recipe"),
    ("mcp", ("晚餐", "菜"), 5.0, "dinner dish"),
    ("mcp", ("推荐", "菜"), 4.0, "dish recommendation"),
    ("mcp", ("步骤", "菜"), 4.0, "recipe steps"),
    ("mcp", ("做法", "菜"), 4.0, "recipe method"),
]

MIN_ROUTE_SCORE = 3.0
# Confidence threshold: when ≥2 intents reach the score threshold but
# no sequencing / parallel conjunction is present, confidence determines
# whether the secondary intent is noise or a genuine co-intent.
MIN_ROUTE_CONFIDENCE = 0.60
# Light conjunctions that indicate the user is listing two tasks without the
# strict "先...然后..." pattern.  When present AND both intents are confident,
# they trigger multi-intent execution.
PARALLEL_CONJUNCTIONS = ("顺便", "同时", "并且", "另外")
# When ≥2 intents reach threshold, the margin between top-2 decides:
# Confidence cap applied to all score-based decisions.
CONFIDENCE_CAP = 0.95
LLM_ROUTER_MIN_CONFIDENCE = 0.70
ALLOWED_INTENTS = {"search", "motion", "diet", "chat", "mcp"}
# Multi-intent plans are open to every legal subgraph combination.  The step
# budget keeps one request bounded without coupling the router to a brittle
# pair whitelist.
MAX_ROUTE_STEPS = 3

INTENT_CLARIFICATION_COPY: Dict[Intent, Tuple[str, str]] = {
    "search": ("资料检索", "查找最新或权威资料"),
    "motion": ("动作分析", "分析具体动作、姿势或动作数据"),
    "diet": ("饮食建议", "制定饮食、营养或摄入方案"),
    "chat": ("训练问答", "解释训练原理或给出训练建议"),
    "mcp": ("菜谱工具", "提供具体菜品做法和烹饪步骤"),
}
INTENT_CLARIFICATION_ALIASES: Dict[Intent, Tuple[str, ...]] = {
    "search": ("资料检索", "检索", "搜索", "查资料", "查最新", "权威资料"),
    "motion": ("动作分析", "动作", "姿势", "姿态", "纠正动作"),
    "diet": ("饮食建议", "饮食", "营养", "吃什么", "三餐", "摄入"),
    "chat": ("训练问答", "训练建议", "原理", "解释"),
    "mcp": ("菜谱工具", "菜谱", "做法", "烹饪", "做菜"),
}
COOKING_ACTION_PATTERNS = ("怎么做", "如何做", "咋做", "做法", "步骤", "教程")
COOKING_CONTEXT_TERMS = (
    "炒",
    "煮",
    "炖",
    "蒸",
    "煎",
    "烤",
    "饭",
    "面",
    "汤",
    "菜",
    "肉",
    "鱼",
    "蛋",
    "鸡",
    "食材",
    "早餐",
    "午餐",
    "晚餐",
)
EXERCISE_TERMS = (
    "深蹲",
    "硬拉",
    "卧推",
    "俯卧撑",
    "引体向上",
    "划船",
    "肩推",
    "平板支撑",
    "动作",
    "姿势",
    "训练",
    "练",
)
DIET_PLANNING_TERMS = ("减脂", "增肌", "热量", "营养", "饮食", "摄入", "蛋白质")

SEMANTIC_EXAMPLES: Dict[Intent, List[str]] = {
    "search": [
        "最近有什么健身新闻",
        "有没有新的运动科学研究",
        "查一下最新减脂研究",
        "帮我找一下最近训练资讯",
        "latest fitness research",
        "recent strength training news",
    ],
    "motion": [
        "帮我看看深蹲哪里不对",
        "我的硬拉姿势有问题吗",
        "这个动作标准吗",
        "帮我分析卧推动作",
        "我的训练姿态有没有问题",
        "analyze my squat posture",
    ],
    "diet": [
        "我最近想瘦一点",
        "我想把身材调整得更轻盈一点",
        "我想控制体重",
        "我想吃得健康一点",
        "我应该怎么安排饮食",
        "减重期间怎么安排三餐",
        "I want to lose weight",
    ],
    "mcp": [
        "番茄炒蛋怎么做",
        "晚饭做什么菜",
        "给我一个家常菜做法",
        "这道菜的烹饪步骤",
        "how to cook tomato eggs",
    ],
    "chat": [
        "什么是渐进超负荷",
        "蛋白质有什么作用",
        "深蹲有哪些好处",
        "什么是有氧运动",
        "健身新手应该注意什么",
        "what is progressive overload",
    ],
}


def _normalize_text(text: str) -> str:
    return text.strip().lower()


def _empty_scores() -> Dict[str, float]:
    return {intent: 0.0 for intent in ["search", "motion", "diet", "mcp", "chat"]}


def _record_llm_router_outcome(outcome: str, latency_ms: float) -> None:
    global _LLM_ROUTER_TOTAL_LATENCY_MS, _LLM_ROUTER_MAX_LATENCY_MS
    with _LLM_ROUTER_METRICS_LOCK:
        _LLM_ROUTER_OUTCOMES[outcome] += 1
        _LLM_ROUTER_TOTAL_LATENCY_MS += latency_ms
        _LLM_ROUTER_MAX_LATENCY_MS = max(_LLM_ROUTER_MAX_LATENCY_MS, latency_ms)


def _record_llm_router_selection(outcome: str) -> None:
    with _LLM_ROUTER_METRICS_LOCK:
        _LLM_ROUTER_SELECTIONS[outcome] += 1


def get_llm_router_metrics(reset: bool = False) -> Dict[str, Any]:
    """Return process-local LLM router call metrics for evaluation and logging."""
    global _LLM_ROUTER_TOTAL_LATENCY_MS, _LLM_ROUTER_MAX_LATENCY_MS
    with _LLM_ROUTER_METRICS_LOCK:
        calls = sum(_LLM_ROUTER_OUTCOMES.values())
        metrics = {
            "calls": calls,
            "outcomes": dict(_LLM_ROUTER_OUTCOMES),
            "selection_outcomes": dict(_LLM_ROUTER_SELECTIONS),
            "average_latency_ms": (
                round(_LLM_ROUTER_TOTAL_LATENCY_MS / calls, 2) if calls else 0.0
            ),
            "max_latency_ms": round(_LLM_ROUTER_MAX_LATENCY_MS, 2),
        }
        if reset:
            _LLM_ROUTER_OUTCOMES.clear()
            _LLM_ROUTER_SELECTIONS.clear()
            _LLM_ROUTER_TOTAL_LATENCY_MS = 0.0
            _LLM_ROUTER_MAX_LATENCY_MS = 0.0
        return metrics


def _with_llm_router_metric(
    decision: RouteDecision,
    outcome: str,
    started_at: float,
) -> RouteDecision:
    latency_ms = (time.perf_counter() - started_at) * 1000
    _record_llm_router_outcome(outcome, latency_ms)
    decision["matches"].append(f"llm_outcome:{outcome}")
    logger.info(
        "LLM router outcome=%s intent=%s confidence=%.2f latency_ms=%.2f",
        outcome,
        decision["intent"],
        decision["confidence"],
        latency_ms,
    )
    return decision


def _confidence(best_score: float, margin: float) -> float:
    """Compute a confidence score from the top score and the margin to second.

    The formula encodes two orthogonal signals into a single 0-1 score:

        base = 0.35                                          # 最低线
        score_contrib = min(best_score / 15, 0.35)           # 绝对值分量
        margin_contrib = min(margin / 12, 0.25)              # 相对差距分量

    Range: ~0.42 (e.g. score=3, margin=0) to 0.95 (capped).

    This confidence is used in the multi-signal branch to decide whether
    the second-highest intent is noise (high confidence → single-intent)
    or a genuine co-intent / ambiguous (low confidence → multi / chat).
    """
    if best_score < MIN_ROUTE_SCORE:
        return 0.0
    raw = 0.35 + min(best_score / 15.0, 0.35) + min(margin / 12.0, 0.25)
    return round(min(raw, CONFIDENCE_CAP), 2)


def _has_explicit_sequencing(text: str) -> bool:
    """Detect explicit multi-step signal like '先...再...'."""
    return "先" in text and any(sep in text for sep in ("再", "然后"))


def _has_parallel_conjunction(text: str) -> bool:
    """Detect light parallel-task markers like '顺便', '同时', '并且'."""
    return any(conj in text for conj in PARALLEL_CONJUNCTIONS)


def _low_confidence_fallback(
    user_input: str,
    model_id: Optional[str],
    scores: Dict[str, float],
    matches: List[str],
) -> RouteDecision:
    """No intent reached threshold. Try embedding then LLM, fallback to chat."""
    embedding_decision = _embedding_semantic_route(user_input)
    if embedding_decision["source"] == "embedding_examples":
        return embedding_decision
    llm_decision = _llm_classifier_route(user_input, model_id)
    if llm_decision["source"] == "llm_classifier":
        _record_llm_router_selection("selected")
        return llm_decision
    return RouteDecision(
        intent="chat",
        confidence=0.0,
        reason=(
            "No route rule reached the minimum score; "
            f"{embedding_decision['reason']} "
            f"{llm_decision['reason']} Falling back to chat."
        ),
        source="fallback",
        scores=scores,
        matches=matches + embedding_decision["matches"] + llm_decision["matches"],
    )


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for left_value, right_value in zip(left, right):
        left_float = float(left_value)
        right_float = float(right_value)
        numerator += left_float * right_float
        left_norm += left_float * left_float
        right_norm += right_float * right_float
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return numerator / ((left_norm ** 0.5) * (right_norm ** 0.5))


def _get_embedding_router_model(model_name: str) -> Any:
    global _EMBEDDING_ROUTER_MODEL, _EMBEDDING_ROUTER_MODEL_NAME
    with _EMBEDDING_ROUTER_LOCK:
        if (
            _EMBEDDING_ROUTER_MODEL is None
            or _EMBEDDING_ROUTER_MODEL_NAME != model_name
        ):
            from sentence_transformers import SentenceTransformer

            _EMBEDDING_ROUTER_MODEL = SentenceTransformer(model_name)
            _EMBEDDING_ROUTER_MODEL_NAME = model_name
        return _EMBEDDING_ROUTER_MODEL


def _as_vector_list(vectors: Any) -> List[List[float]]:
    if hasattr(vectors, "tolist"):
        vectors = vectors.tolist()
    if not isinstance(vectors, list):
        return []
    if vectors and not isinstance(vectors[0], list):
        return [[float(value) for value in vectors]]
    return [[float(value) for value in vector] for vector in vectors]


def _get_embedding_example_vectors(
    model: Any,
    model_name: str,
) -> List[Tuple[Intent, str, Sequence[float]]]:
    with _EMBEDDING_ROUTER_LOCK:
        cached = _EMBEDDING_EXAMPLE_VECTORS.get(model_name)
        if cached is not None:
            return cached

        pairs: List[Tuple[Intent, str]] = [
            (intent, example)
            for intent, examples in SEMANTIC_EXAMPLES.items()
            for example in examples
        ]
        encoded = _as_vector_list(
            model.encode([example for _, example in pairs], normalize_embeddings=True)
        )
        vectors = [
            (intent, example, vector)
            for (intent, example), vector in zip(pairs, encoded)
        ]
        _EMBEDDING_EXAMPLE_VECTORS[model_name] = vectors
        return vectors


def _embedding_semantic_route(user_input: str) -> RouteDecision:
    from app.config import config

    scores = _empty_scores()
    matches: List[str] = []
    if not config.router_embedding_enabled:
        return RouteDecision(
            intent="chat",
            confidence=0.0,
            reason="Embedding semantic router is disabled.",
            source="embedding_disabled",
            scores=scores,
            matches=matches,
        )

    try:
        model = _get_embedding_router_model(config.router_embedding_model)
        query_vector = _as_vector_list(
            model.encode([user_input], normalize_embeddings=True)
        )[0]
        example_vectors = _get_embedding_example_vectors(
            model,
            config.router_embedding_model,
        )
    except Exception as exc:
        logger.warning("Embedding semantic router unavailable: %s", exc)
        return RouteDecision(
            intent="chat",
            confidence=0.0,
            reason=f"Embedding semantic router is unavailable: {exc}",
            source="embedding_unavailable",
            scores=scores,
            matches=[f"embedding_error:{type(exc).__name__}"],
        )

    best_examples: Dict[Intent, Tuple[str, float]] = {
        intent: ("", 0.0) for intent in ALLOWED_INTENTS
    }
    for intent, example, vector in example_vectors:
        score = _cosine_similarity(query_vector, vector)
        if score > best_examples[intent][1]:
            best_examples[intent] = (example, score)

    for intent, (example, score) in best_examples.items():
        scores[intent] = round(score, 4)
        if example and score > 0:
            matches.append(f"{intent}:embedding_example({example})={score:.2f}")

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_intent, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = best_score - second_score
    confidence = round(min(0.50 + best_score * 0.35 + margin * 0.35, 0.92), 2)

    if (
        confidence < config.router_embedding_min_confidence
        or margin < config.router_embedding_min_margin
    ):
        return RouteDecision(
            intent="chat",
            confidence=confidence,
            reason=(
                "Embedding semantic router did not pass confidence/margin gates: "
                f"score={best_score:.2f}, margin={margin:.2f}, "
                f"confidence={confidence:g}."
            ),
            source="embedding_rejected",
            scores=scores,
            matches=matches,
        )

    return RouteDecision(
        intent=best_intent,  # type: ignore[typeddict-item]
        confidence=confidence,
        reason=(
            f"Selected {best_intent} by embedding examples: "
            f"score={best_score:.2f}, margin={margin:.2f}, confidence={confidence:g}."
        ),
        source="embedding_examples",
        scores=scores,
        matches=matches,
    )


def _build_llm_router_prompt(user_input: str) -> str:
    """Build the strict JSON prompt for a future LLM classifier fallback."""
    prompt = f"""待分类用户输入：<<<{user_input}>>>

你是健身助手的意图路由分类器。只判断上面的输入，不回答问题。

必须从以下五类中选择一个：
- chat：健身知识解释、训练计划、问候、信息不足或跨领域综合问题
- search：查找最新资料、研究、新闻、权威来源
- diet：个人饮食规划、减脂增肌饮食、热量和摄入量
- motion：动作姿势纠错、姿态分析、上传 .npz 动作数据
- mcp：具体菜谱、食材做法、烹饪步骤、一道菜推荐

只输出一个 JSON 对象，不要 Markdown，不要解释过程。字段必须完整：
{{
  "intent": "chat|search|diet|motion|mcp",
  "confidence": 0.85,
  "reason": "简短中文原因",
  "needs_clarification": false
}}

现在只输出 JSON。/no_think
"""
    return compose_safe_prompt(prompt, kind="router.classifier")


def _call_llm_router(prompt: str, model_id: Optional[str] = None) -> Optional[str]:
    """Call the request-selected classifier; return None when disabled/unavailable."""
    from app.config import config

    if not config.llm_router_enabled:
        return None

    from app.llm.loader import LLMGenerationError
    from app.llm.providers import create_llm

    llm = create_llm(
        model_id,
        max_tokens=config.llm_router_max_tokens,
        temperature=0.0,
        top_p=1.0,
    )
    try:
        return llm.generate(
            prompt,
            max_new_tokens=config.llm_router_max_tokens,
            temperature=0.0,
            top_p=1.0,
        )
    except LLMGenerationError as exc:
        logger.error("LLM router failed [%s]", exc.error_code)
        return None


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start: end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _llm_classifier_route(
    user_input: str,
    model_id: Optional[str] = None,
) -> RouteDecision:
    """Try the LLM classifier fallback contract.

    A decision is accepted only when the JSON is valid, the intent is allowed,
    no clarification is requested, and confidence is high enough.
    """
    started_at = time.perf_counter()
    prompt = _build_llm_router_prompt(user_input)
    # Keep the original one-argument hook compatible for tests and extensions;
    # only pass an explicit model when the request actually selected one.
    raw = (
        _call_llm_router(prompt, model_id)
        if model_id is not None
        else _call_llm_router(prompt)
    )
    if not raw:
        return _with_llm_router_metric(
            RouteDecision(
                intent="chat",
                confidence=0.0,
                reason="LLM router provider is disabled or unavailable.",
                source="llm_unavailable",
                scores=_empty_scores(),
                matches=[],
            ),
            "unavailable",
            started_at,
        )

    payload = _extract_json_object(raw)
    if payload is None:
        return _with_llm_router_metric(
            RouteDecision(
                intent="chat",
                confidence=0.0,
                reason="LLM router returned invalid JSON.",
                source="llm_parse_error",
                scores=_empty_scores(),
                matches=[f"llm_raw:{raw[:120]}"],
            ),
            "parse_error",
            started_at,
        )

    intent = payload.get("intent")
    confidence_raw = payload.get("confidence", 0.0)
    needs_clarification = bool(payload.get("needs_clarification", False))
    reason = str(payload.get("reason", "")).strip() or "No LLM reason provided."

    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0

    if intent not in ALLOWED_INTENTS:
        return _with_llm_router_metric(
            RouteDecision(
                intent="chat",
                confidence=0.0,
                reason=f"LLM router returned invalid intent: {intent!r}.",
                source="llm_invalid",
                scores=_empty_scores(),
                matches=[f"llm_payload:{payload}"],
            ),
            "invalid_intent",
            started_at,
        )

    if needs_clarification:
        return _with_llm_router_metric(
            RouteDecision(
                intent="chat",
                confidence=confidence,
                reason=f"LLM router requested clarification: {reason}",
                source="llm_clarification",
                scores=_empty_scores(),
                matches=[f"llm_intent:{intent}", "needs_clarification:true"],
            ),
            "clarification",
            started_at,
        )

    if confidence < LLM_ROUTER_MIN_CONFIDENCE:
        return _with_llm_router_metric(
            RouteDecision(
                intent="chat",
                confidence=confidence,
                reason=(
                    f"LLM router confidence {confidence:.2f} is below "
                    f"{LLM_ROUTER_MIN_CONFIDENCE:.2f}: {reason}"
                ),
                source="llm_low_confidence",
                scores=_empty_scores(),
                matches=[f"llm_intent:{intent}"],
            ),
            "low_confidence",
            started_at,
        )

    return _with_llm_router_metric(
        RouteDecision(
            intent=intent,  # type: ignore[typeddict-item]
            confidence=round(min(confidence, 0.99), 2),
            reason=f"Selected {intent} by LLM classifier fallback: {reason}",
            source="llm_classifier",
            scores=_empty_scores(),
            matches=[f"llm_intent:{intent}"],
        ),
        "contract_accepted",
        started_at,
    )


def _classify_primary_intent_with_scores(
    user_input: str,
    model_id: Optional[str] = None,
) -> RouteDecision:
    """Classify intent with weighted rule scores and route metadata."""
    text = _normalize_text(user_input)
    scores = _empty_scores()
    matches: List[str] = []

    for intent, rules in WEIGHTED_RULES.items():
        for phrase, weight in rules:
            if phrase.lower() in text:
                scores[intent] += weight
                matches.append(f"{intent}:{phrase}+{weight:g}")

    for intent, required, weight, label in COMBO_RULES:
        if all(part.lower() in text for part in required):
            scores[intent] += weight
            matches.append(f"{intent}:combo({label})+{weight:g}")

    _apply_pattern_boosts(text, scores, matches)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_intent, best_score = ranked[0]
    second_intent, second_score = ranked[1] if len(ranked) > 1 else ("", 0.0)
    margin = best_score - second_score

    # --- 单意图：只有一个意图达到最低分 ---
    active_count = sum(1 for _, s in ranked if s >= MIN_ROUTE_SCORE)
    if active_count <= 1:
        if best_score < MIN_ROUTE_SCORE:
            return _low_confidence_fallback(user_input, model_id, scores, matches)
        confidence = _confidence(best_score, margin)
        return RouteDecision(
            intent=best_intent,
            confidence=confidence,
            reason=f"Single intent {best_intent}: score={best_score:g}, margin={margin:g}.",
            source="weighted_rules",
            scores=scores,
            matches=matches,
        )

    # --- 多信号：≥2 个意图达到最低分 ---
    has_sequencing = _has_explicit_sequencing(text)
    has_parallel = _has_parallel_conjunction(text)
    primary_confidence = _confidence(best_score, margin)

    # ── 显式顺序 / 并列：不看置信度，直接多意图 ──
    if has_sequencing:
        return RouteDecision(
            intent=best_intent,
            confidence=primary_confidence,
            reason=(
                f"Multi-intent: selected {best_intent} as primary "
                f"(score={best_score:g}), "
                f"{second_intent} detected as secondary "
                f"(score={second_score:g}). "
                "Explicit sequencing present."
            ),
            source="weighted_rules",
            scores=scores,
            matches=matches,
        )

    if has_parallel:
        return RouteDecision(
            intent=best_intent,
            confidence=primary_confidence,
            reason=(
                f"Multi-intent (parallel): {best_intent} "
                f"(score={best_score:g}) and "
                f"{second_intent} (score={second_score:g}) "
                "both detected. Parallel conjunction present."
            ),
            source="weighted_rules",
            scores=scores,
            matches=matches,
        )

    # ── 无连接词：置信度是唯一的决策依据 ──
    # 置信度同时编码了两件事：
    #   - score 大小（信号本身有多强）
    #   - margin 大小（比第二名领先多少）
    # 这两个维度不需要单独判断 — 合在一起就是"系统对此决定有多确定"。
    #
    # confidence ≥ 0.80 → 主意图信号强 + margin 够大 → 单意图
    #   例: search=15 margin=7.5 → conf=0.95（强信号大差距）
    #   例: motion=8 margin=5    → conf=0.82（中等信号够差距）
    #
    # confidence < 0.80 → margin 太小或信号不够 → 歧义
    #   例: motion=7 chat=6.5 margin=0.5 → conf≈0.57（两意图接近）
    #   例: motion=4 mcp=3.5 margin=0.5  → conf≈0.50（刚过线且接近）

    _CONFIDENCE_FOR_SINGLE = 0.80

    if primary_confidence < _CONFIDENCE_FOR_SINGLE:
        return RouteDecision(
            intent="chat",
            confidence=primary_confidence,
            reason=(
                f"Ambiguity: {best_intent}={best_score:g} vs {second_intent}={second_score:g}, "
                f"margin={margin:g}, confidence={primary_confidence:g} < {_CONFIDENCE_FOR_SINGLE}. "
                "Requesting clarification before execution."
            ),
            source="ambiguity_fallback",
            scores=scores,
            matches=matches,
        )

    # 主强 + margin 大 → 单意图
    return RouteDecision(
        intent=best_intent,
        confidence=primary_confidence,
        reason=(
            f"Dominant intent {best_intent}: score={best_score:g}, "
            f"margin={margin:g}, confidence={primary_confidence:g} ≥ "
            f"{_CONFIDENCE_FOR_SINGLE} (secondary {second_intent}={second_score:g} is noise)."
        ),
        source="weighted_rules",
        scores=scores,
        matches=matches,
    )


def _rule_intent_for_segment(text: str) -> Optional[Intent]:
    """Classify one clause without invoking the optional LLM provider."""
    normalized = _normalize_text(text)
    if not normalized:
        return None

    scores = _empty_scores()
    matches: List[str] = []
    for intent, rules in WEIGHTED_RULES.items():
        for phrase, weight in rules:
            if phrase.lower() in normalized:
                scores[intent] += weight
    for intent, required, weight, _label in COMBO_RULES:
        if all(part.lower() in normalized for part in required):
            scores[intent] += weight
    _apply_pattern_boosts(normalized, scores, matches)

    best_intent, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score >= MIN_ROUTE_SCORE:
        return best_intent  # type: ignore[return-value]

    return None


def _multi_intent_metadata(
    user_input: str,
    decision: RouteDecision,
) -> Tuple[List[Intent], List[Intent], str, bool]:
    """Detect reliable co-intents and preserve their expression order."""
    scored_primary = decision["intent"]
    text = _normalize_text(user_input)
    clause_source = text
    if _has_explicit_sequencing(text):
        # Text before "先" usually describes the overall goal; the actual task
        # order starts after it (for example, "想学硬拉，先讲原理再看动作").
        clause_source = text[text.find("先") + 1 :]
    clause_pattern = (
        r"(?:，|,|；|;|。|然后|顺便|同时|并且|另外|最好给(?:个)?|"
        r"再(?=查|搜|给|分析|看|安排|推荐|解释))"
    )
    clauses = [
        part.strip()
        for part in re.split(clause_pattern, clause_source)
        if part.strip()
    ]

    ordered_clause_intents: List[Intent] = []
    for clause in clauses:
        intent = _rule_intent_for_segment(clause)
        if intent and intent not in ordered_clause_intents:
            ordered_clause_intents.append(intent)

    scored_intents: List[Intent] = []
    for intent, score in sorted(
        decision["scores"].items(), key=lambda item: item[1], reverse=True
    ):
        if score >= MIN_ROUTE_SCORE:
            scored_intents.append(intent)  # type: ignore[arg-type]

    reliable_multi_signal = (
        _has_explicit_sequencing(text)
        or _has_parallel_conjunction(text)
        or "然后" in text
        or "最好给" in text
        or "再给" in text
    )
    route_plan: List[Intent] = [scored_primary]
    if reliable_multi_signal:
        ordered_candidates = list(ordered_clause_intents)
        if len(ordered_candidates) < 2:
            ordered_candidates = [scored_primary]
            ordered_candidates.extend(
                intent for intent in scored_intents if intent not in ordered_candidates
            )
        if len(ordered_candidates) >= 2:
            route_plan = ordered_candidates

    primary = route_plan[0]
    observed: List[Intent] = [intent for intent in route_plan[1:] if intent != primary]
    if len(route_plan) == 1:
        for intent in ordered_clause_intents + scored_intents:
            if intent != primary and intent not in observed:
                observed.append(intent)

    # Secondary intents describe the downstream capability that complements the
    # primary route, rather than blindly copying every keyword score.  Search
    # normally needs a chat synthesis step; only a concrete form-analysis signal
    # should keep motion as its secondary capability.
    if primary == "search" and len(route_plan) == 1:
        motion_analysis_terms = ("内扣", "姿势", "姿态", "动作分析", "动作数据", ".npz")
        observed = (
            ["motion"]
            if any(term in text for term in motion_analysis_terms)
            else ["chat"]
        )

    # Negated or quantity-only recipe language is a nutrition request, not a
    # latent tool call.  Concrete ingredients/fridge constraints remain eligible
    # for the recipe capability.
    recipe_negations = (
        "不需要具体做法",
        "不需要做法",
        "不用给具体做法",
        "不用具体做法",
        "不要具体做法",
        "不要菜谱",
        "不想做饭",
        "不用做饭",
    )
    has_cooking_action = any(pattern in text for pattern in COOKING_ACTION_PATTERNS)
    has_cooking_context = any(term in text for term in COOKING_CONTEXT_TERMS)
    if primary == "diet" and (
        any(pattern in text for pattern in recipe_negations)
        or (not has_cooking_action and not has_cooking_context)
    ):
        observed = [intent for intent in observed if intent != "mcp"]

    # Some broad planning questions deliberately stay on chat, while retaining
    # the domain capability as metadata for evaluation and future composition.
    if primary == "chat":
        if any(term in text for term in ("吃和练", "体重没变")) and "diet" not in observed:
            observed.append("diet")
        if any(term in text for term in ("圆肩", "骨盆前倾", "恢复训练")) and "motion" not in observed:
            observed.append("motion")

    if primary == "motion" and any(
        term in text for term in ("疼", "不舒服", "主要练哪里")
    ) and "chat" not in observed:
        observed.append("chat")

    needs_clarification = False
    if observed:
        reason = (
            f"Primary intent is {primary}; observed secondary intents: "
            + ", ".join(observed)
            + "."
        )
    else:
        reason = f"Only the primary intent {primary} was observed."
    if reliable_multi_signal and len(route_plan) > 1:
        reason += " Reliable multi-intent language produced an ordered route plan."

    return observed, route_plan, reason, needs_clarification


def classify_intent_with_scores(
    user_input: str,
    model_id: Optional[str] = None,
) -> RouteDecision:
    """Classify primary intent and attach Phase 4 multi-intent observations."""
    decision = _classify_primary_intent_with_scores(user_input, model_id)
    if decision["source"] == "ambiguity_fallback":
        ranked_candidates = [
            intent
            for intent, score in sorted(
                decision["scores"].items(),
                key=lambda item: item[1],
                reverse=True,
            )
            if score >= MIN_ROUTE_SCORE
        ][:2]
        candidates: List[Intent] = [
            intent  # type: ignore[misc]
            for intent in ranked_candidates
            if intent in ALLOWED_INTENTS
        ]
        if len(candidates) >= 2:
            question = _build_clarification_question(candidates)
            decision["primary_intent"] = "chat"
            decision["secondary_intents"] = candidates
            decision["route_plan"] = ["chat"]
            decision["multi_intent_reason"] = (
                "Two candidate intents passed the score gate, but neither had "
                "enough evidence to execute safely without clarification."
            )
            decision["needs_clarification"] = True
            decision["clarification_candidates"] = candidates
            decision["clarification_question"] = question
            decision["ambiguity_signals"] = [
                "low_confidence",
                "multiple_capabilities",
                "clarification_required",
            ]
            return decision

    secondary, route_plan, reason, needs_clarification = _multi_intent_metadata(
        user_input, decision
    )
    detected_primary = route_plan[0]
    if detected_primary != decision["intent"]:
        decision["reason"] += (
            f" User expression order promoted {detected_primary} to the first route step."
        )
        decision["intent"] = detected_primary
    decision["primary_intent"] = detected_primary
    decision["secondary_intents"] = secondary
    decision["route_plan"] = route_plan
    decision["multi_intent_reason"] = reason
    decision["needs_clarification"] = needs_clarification
    ambiguity_signals: List[str] = []
    if decision["source"] == "ambiguity_fallback":
        ambiguity_signals.append("low_confidence")
    if secondary:
        ambiguity_signals.append("multiple_capabilities")
    if len(route_plan) > 1:
        ambiguity_signals.append("multi_intent_plan")
    decision["ambiguity_signals"] = ambiguity_signals
    return decision


def _build_clarification_question(candidates: Sequence[Intent]) -> str:
    """Build a deterministic question that names the competing capabilities."""
    choices = []
    for index, intent in enumerate(candidates[:2], start=1):
        label, description = INTENT_CLARIFICATION_COPY[intent]
        choices.append(f"{index}）{label}：{description}")
    return (
        "我理解到两种可能："
        + "；".join(choices)
        + "。你更希望我先处理哪一种？可以回复“1/前者”或“2/后者”；"
        "如果两项都需要，请回复“两个都要”。"
    )


def _valid_pending_candidates(pending: Dict[str, Any]) -> List[Intent]:
    candidates: List[Intent] = []
    raw_candidates = pending.get("candidates", [])
    if not isinstance(raw_candidates, list):
        return candidates
    for raw_intent in raw_candidates[:2]:
        if raw_intent in ALLOWED_INTENTS and raw_intent not in candidates:
            candidates.append(raw_intent)  # type: ignore[arg-type]
    return candidates


def _clarification_selection(
    user_input: str,
    candidates: Sequence[Intent],
) -> Optional[List[Intent]]:
    """Resolve ordinal, capability-name, or 'both' clarification answers."""
    normalized = re.sub(r"[\s，,。.!！?？、]", "", user_input).lower()
    if not normalized:
        return None
    if any(term in normalized for term in ("两个都要", "两项都要", "都需要", "都要", "一起做", "一起")):
        return list(candidates)
    ordinal_aliases = (
        (("1",), ("第一个", "第一项", "前者")),
        (("2",), ("第二个", "第二项", "后者")),
    )
    ordinal_matches = []
    for index, (exact_aliases, phrase_aliases) in enumerate(ordinal_aliases):
        if index >= len(candidates):
            continue
        if normalized in exact_aliases or any(
            alias in normalized for alias in phrase_aliases
        ):
            ordinal_matches.append(candidates[index])
    if len(ordinal_matches) == 1:
        return ordinal_matches
    matched = [
        intent
        for intent in candidates
        if any(alias in normalized for alias in INTENT_CLARIFICATION_ALIASES[intent])
    ]
    return matched if len(matched) == 1 else None


def _clarification_decision(
    pending: Dict[str, Any],
    selected: Sequence[Intent],
) -> RouteDecision:
    scores = _empty_scores()
    stored_scores = pending.get("scores")
    if isinstance(stored_scores, dict):
        for intent in ALLOWED_INTENTS:
            try:
                scores[intent] = float(stored_scores.get(intent, 0.0))
            except (TypeError, ValueError):
                scores[intent] = 0.0
    plan = list(selected[:MAX_ROUTE_STEPS])
    primary = plan[0]
    return RouteDecision(
        intent=primary,
        confidence=0.98,
        reason="User explicitly resolved the pending route clarification.",
        source="clarification_resolution",
        scores=scores,
        matches=[f"clarification_selected:{intent}" for intent in plan],
        ambiguity_signals=["clarification_resolved"],
        primary_intent=primary,
        secondary_intents=list(plan[1:]),
        route_plan=plan,
        multi_intent_reason=(
            "User selected both candidate capabilities."
            if len(plan) > 1
            else f"User selected {primary}."
        ),
        needs_clarification=False,
        clarification_candidates=list(plan),
    )


def _retry_clarification_decision(
    candidates: Sequence[Intent],
) -> RouteDecision:
    question = _build_clarification_question(candidates)
    return RouteDecision(
        intent="chat",
        confidence=0.0,
        reason="The clarification answer did not identify either candidate.",
        source="clarification_retry",
        scores=_empty_scores(),
        matches=["clarification_answer:unresolved"],
        ambiguity_signals=["clarification_required"],
        primary_intent="chat",
        secondary_intents=list(candidates),
        route_plan=["chat"],
        multi_intent_reason="Waiting for the user to select a stored candidate.",
        needs_clarification=True,
        clarification_candidates=list(candidates),
        clarification_question="我还不能确定你的选择。" + question,
    )


def _validate_route_plan(
    requested_plan: Sequence[str],
    fallback_intent: Intent,
) -> Tuple[List[Intent], List[str]]:
    """Validate a detected plan without restricting legal intent combinations."""
    execution_plan: List[Intent] = []
    warnings: List[str] = []
    for raw_intent in requested_plan:
        if raw_intent not in ALLOWED_INTENTS:
            warnings.append(f"route_plan_invalid_intent:{raw_intent}")
            continue
        intent: Intent = raw_intent  # type: ignore[assignment]
        if intent in execution_plan:
            warnings.append(f"route_plan_duplicate_intent:{intent}")
            continue
        execution_plan.append(intent)

    if not execution_plan:
        execution_plan = [fallback_intent]
        warnings.append("route_plan_empty:fallback_to_primary")

    if len(execution_plan) > MAX_ROUTE_STEPS:
        execution_plan = execution_plan[:MAX_ROUTE_STEPS]
        warnings.append(f"route_plan_truncated:max_steps={MAX_ROUTE_STEPS}")

    return execution_plan, warnings


def _apply_pattern_boosts(
    text: str,
    scores: Dict[str, float],
    matches: List[str],
) -> None:
    """Apply general routing patterns that are broader than fixed keywords."""
    _apply_order_constraint(text, scores, matches)

    has_cooking_action = any(pattern in text for pattern in COOKING_ACTION_PATTERNS)
    has_exercise_term = any(term in text for term in EXERCISE_TERMS)
    has_diet_planning_term = any(term in text for term in DIET_PLANNING_TERMS)
    has_cooking_context = any(term in text for term in COOKING_CONTEXT_TERMS)

    negative_recipe_patterns = (
        "不需要具体做法",
        "不需要做法",
        "不用给具体做法",
        "不用具体做法",
        "不要具体做法",
        "不要菜谱",
        "不想做饭",
        "不用做饭",
    )
    if any(pattern in text for pattern in negative_recipe_patterns):
        scores["mcp"] = max(0.0, scores["mcp"] - 20.0)
        scores["diet"] += 6.0
        matches.append("diet:constraint(recipe_negation)+6")
        matches.append("mcp:constraint(recipe_negation)-20")

    if "吃和练" in text and any(term in text for term in ("安排", "状态", "建议")):
        scores["chat"] += 10.0
        matches.append("chat:pattern(cross_domain_plan)+10")

    if "体重没变" in text and any(term in text for term in ("训练", "效果", "原因")):
        scores["chat"] += 8.0
        matches.append("chat:pattern(progress_diagnosis)+8")

    plan_motion_patterns = (
        "练什么动作",
        "练哪些动作",
        "应该练什么动作",
        "应该练哪些动作",
        "什么动作适合",
    )
    motion_analysis_signals = (
        "姿势",
        "姿态",
        "动作分析",
        "哪里不对",
        "标准吗",
        ".npz",
        "上传",
    )
    if (
        any(pattern in text for pattern in plan_motion_patterns)
        and not any(signal in text for signal in motion_analysis_signals)
    ):
        scores["chat"] += 8.0
        matches.append("chat:pattern(plan_not_motion_analysis)+8")

    ingredient_meal_patterns = ("用冰箱里的", "用现有食材", "用这些食材")
    if (
        any(pattern in text for pattern in ingredient_meal_patterns)
        and any(term in text for term in ("一顿", "一道", "做", "安排"))
    ):
        scores["mcp"] += 10.0
        matches.append("mcp:pattern(ingredient_meal)+10")
    elif (
        "用" in text
        and "一顿" in text
        and has_cooking_context
    ):
        scores["mcp"] += 10.0
        matches.append("mcp:pattern(concrete_meal_from_ingredients)+10")

    if has_cooking_action and has_exercise_term:
        scores["motion"] += 4.0
        matches.append("motion:pattern(exercise_how_to)+4")
        return

    if has_cooking_action and (has_cooking_context or not has_diet_planning_term):
        weight = 5.0 if has_cooking_context else 3.5
        scores["mcp"] += weight
        matches.append(f"mcp:pattern(cooking_how_to)+{weight:g}")


def _apply_order_constraint(
    text: str,
    scores: Dict[str, float],
    matches: List[str],
) -> None:
    """Boost the task explicitly requested first in a multi-step sentence."""
    separators = [separator for separator in ("再", "然后") if separator in text]
    if "先" not in text or not separators:
        return

    separator = min(separators, key=text.index)
    first_clause = text[:text.index(separator)]
    intent: Optional[Intent] = None

    if any(term in first_clause for term in ("原理", "概念", "讲解", "解释")):
        intent = "chat"
    elif any(term in first_clause for term in ("搜一下", "搜索", "查一下", "找一下", "找一找")):
        intent = "search"
    elif any(term in first_clause for term in ("分析", ".npz", "姿势", "姿态", "动作")):
        intent = "motion"
    elif any(term in first_clause for term in ("菜谱", "做法", "烹饪", "做一道")):
        intent = "mcp"
    elif any(term in first_clause for term in DIET_PLANNING_TERMS):
        intent = "diet"

    if intent is not None:
        scores[intent] += 24.0
        matches.append(f"{intent}:constraint(first_task)+24")


def classify_intent(user_input: str, model_id: Optional[str] = None) -> str:
    """Return only the selected intent for backward-compatible callers."""
    return classify_intent_with_scores(user_input, model_id)["intent"]


def intent_classify_node(state: RouterState) -> RouterState:
    """Set intent and route metadata based on weighted rules."""
    current_input = state["user_input"]
    pending = state.get("_pending_route_clarification")
    state["_clarification_resolved"] = False
    state["_clarification_cancelled"] = False
    decision: RouteDecision
    if state.get("_motion_artifacts"):
        artifact_count = len(state["_motion_artifacts"])
        decision = {
            "intent": "motion",
            "confidence": 1.0,
            "reason": "The request explicitly references a validated Motion artifact.",
            "source": "motion_artifact",
            "scores": {"motion": 100.0},
            "matches": [f"motion:artifact_reference({artifact_count})"],
            "ambiguity_signals": [],
            "primary_intent": "motion",
            "secondary_intents": [],
            "route_plan": ["motion"],
            "multi_intent_reason": "",
            "needs_clarification": False,
            "clarification_candidates": [],
            "clarification_question": "",
        }
    elif isinstance(pending, dict) and len(_valid_pending_candidates(pending)) >= 2:
        candidates = _valid_pending_candidates(pending)
        selected = _clarification_selection(current_input, candidates)
        if selected:
            decision = _clarification_decision(pending, selected)
            original_input = str(pending.get("original_input", "")).strip()
            if original_input:
                state["user_input"] = (
                    f"原始问题：{original_input}\n用户澄清：{current_input}"
                )
            state["_clarification_resolved"] = True
        elif any(term in current_input.strip() for term in ("算了", "不用了", "取消")):
            decision = classify_intent_with_scores(current_input, state.get("_model_id"))
            state["_clarification_cancelled"] = True
        else:
            fresh_decision = classify_intent_with_scores(
                current_input,
                state.get("_model_id"),
            )
            if (
                fresh_decision["source"] not in {"fallback", "ambiguity_fallback"}
                and not fresh_decision.get("needs_clarification", False)
            ):
                decision = fresh_decision
                state["_clarification_cancelled"] = True
            else:
                decision = _retry_clarification_decision(candidates)
    else:
        decision = classify_intent_with_scores(
            current_input,
            state.get("_model_id"),
        )
    state["intent"] = decision["intent"]
    state["_route_scores"] = decision["scores"]
    state["_route_confidence"] = decision["confidence"]
    state["_route_reason"] = decision["reason"]
    state["_route_source"] = decision["source"]
    state["_route_matches"] = decision["matches"]
    state["_route_ambiguity_signals"] = decision.get("ambiguity_signals", [])
    state["_primary_intent"] = decision["primary_intent"]
    state["_secondary_intents"] = decision["secondary_intents"]
    state["_route_plan"] = decision["route_plan"]
    state["_multi_intent_reason"] = decision["multi_intent_reason"]
    state["_needs_clarification"] = decision["needs_clarification"]
    state["_clarification_candidates"] = decision.get(
        "clarification_candidates", []
    )
    state["_clarification_question"] = decision.get("clarification_question", "")
    requested_plan = decision["route_plan"]
    warnings: List[str] = []
    if decision["needs_clarification"]:
        execution_plan = [decision["primary_intent"]]
    else:
        execution_plan, validation_warnings = _validate_route_plan(
            requested_plan,
            decision["primary_intent"],
        )
        warnings.extend(validation_warnings)
    state["_route_execution_plan"] = execution_plan
    state["_route_execution_cursor"] = 0
    state["_active_intent"] = execution_plan[0]
    state["_route_results"] = []
    state["_route_execution_warnings"] = warnings
    state["_execution"] = []
    ensure_structured_state(state)
    set_task(
        state,
        {
            "user_input": state["user_input"],
            "primary_intent": decision["primary_intent"],
            "secondary_intents": decision["secondary_intents"],
            "execution_plan": execution_plan,
            "needs_clarification": decision["needs_clarification"],
        },
    )
    add_decision(
        state,
        {
            "stage": "router",
            "source": decision["source"],
            "confidence": decision["confidence"],
            "reason": decision["reason"],
            "matches": decision["matches"][:8],
        },
    )
    logger.info(
        "Intent: %s confidence=%.2f source=%s input=%s",
        decision["intent"],
        decision["confidence"],
        decision["source"],
        state["user_input"][:50],
    )
    return state


def clarification_response_node(state: RouterState) -> RouterState:
    """Return the targeted clarification without spending an LLM call."""
    question = state.get("_clarification_question", "").strip()
    if not question:
        candidates = [
            intent
            for intent in state.get("_clarification_candidates", [])
            if intent in ALLOWED_INTENTS
        ]
        question = _build_clarification_question(candidates) if candidates else (
            "我还不能确定你希望处理哪一类问题，请补充具体目标。"
        )
    state["result"] = question
    state["error"] = None
    state.pop("_prompt", None)
    labels = [
        INTENT_CLARIFICATION_COPY[intent][0]
        for intent in state.get("_clarification_candidates", [])
        if intent in INTENT_CLARIFICATION_COPY
    ]
    record_execution(
        state,
        "intent_router",
        "clarification_requested",
        detail="candidates=" + ",".join(labels),
    )
    return state


def route_to_subgraph(
    state: RouterState,
) -> Literal["search", "motion", "diet", "chat", "mcp", "clarify"]:
    """Conditional edge: route based on intent."""
    if state.get("_needs_clarification"):
        return "clarify"
    return state.get("_active_intent", state["intent"])  # type: ignore


def collect_route_result_node(state: RouterState) -> RouterState:
    """Capture one subgraph output and prepare the next approved route step."""
    active_intent = state.get("_active_intent", state["intent"])
    record = {
        "intent": active_intent,
        "result": state.get("result", ""),
        "error": state.get("error"),
        "prompt": state.get("_prompt", ""),
        "prompt_meta": dict(state.get("_prompt_meta", {})),
        "sources": list(state.get("_sources", [])),  # type: ignore[arg-type]
        "structured_state": dict(state.get("_structured_state", {})),
    }
    state.setdefault("_route_results", []).append(record)

    cursor = state.get("_route_execution_cursor", 0) + 1
    state["_route_execution_cursor"] = cursor
    execution_plan = state.get("_route_execution_plan", [state["intent"]])
    if cursor < len(execution_plan):
        state["_active_intent"] = execution_plan[cursor]
        state["result"] = ""
        state["error"] = None
        for key in (
            "_prompt",
            "_prompt_meta",
            "_sources",
            "_retrieved",
            "_retrieval_meta",
            "_search_query",
            "_search_results",
            "_search_meta",
            "_user_profile",
        ):
            state.pop(key, None)  # type: ignore[misc]
    else:
        state["_active_intent"] = state.get("_primary_intent", state["intent"])
    return state


def route_after_collection(
    state: RouterState,
) -> Literal["search", "motion", "diet", "chat", "mcp", "synthesize"]:
    """Continue an approved plan or move to final result synthesis."""
    cursor = state.get("_route_execution_cursor", 0)
    execution_plan = state.get("_route_execution_plan", [state["intent"]])
    if cursor < len(execution_plan):
        return state["_active_intent"]  # type: ignore[return-value]
    return "synthesize"


def synthesize_route_results_node(state: RouterState) -> RouterState:
    """Produce one stable answer from single or multiple subgraph outcomes."""
    records = state.get("_route_results", [])
    state["intent"] = state.get("_primary_intent", state["intent"])
    if not records:
        state["error"] = "No route result was produced."
        state["result"] = "Error: No route result was produced."
        return state

    if len(records) == 1:
        record = records[0]
        state["result"] = record.get("result", "")
        state["error"] = record.get("error")
        if record.get("prompt"):
            state["_prompt"] = record["prompt"]
        if record.get("prompt_meta"):
            state["_prompt_meta"] = record["prompt_meta"]
        state["_sources"] = record.get("sources", [])  # type: ignore[typeddict-unknown-key]
        return state

    successful = [record for record in records if not record.get("error")]
    if not successful:
        errors = "; ".join(
            str(record.get("error") or "unknown error") for record in records
        )
        state["error"] = f"All route steps failed: {errors}"
        state["result"] = f"Error: {state['error']}"
        return state

    sections = []
    sources: List[Any] = []
    for record in successful:
        content = record.get("result") or record.get("prompt") or "No usable output."
        sections.append(
            f"## {record['intent']} 子任务结果\n{str(content)[:3200]}"
        )
        for source in record.get("sources", []):
            if source not in sources:
                sources.append(source)

    failed = [record for record in records if record.get("error")]
    warning_text = ""
    if failed:
        failed_names = ", ".join(str(record["intent"]) for record in failed)
        warning_text = f"\n部分子任务失败：{failed_names}。请基于成功结果回答并说明边界。"
        state.setdefault("_route_execution_warnings", []).append(
            "partial_route_failure:" + failed_names
        )

    prompt = f"""# 任务
将多个健身助手子任务结果合成为一个连贯、准确的最终回答。

# 合成规则
- 先直接回答用户，再按子任务组织要点。
- 不重复内容，不虚构子任务没有提供的信息。
- 如果存在失败或资料不足，明确说明边界。
- 涉及疼痛、伤病或疾病时保留专业医疗提示。

# 用户问题
{state['user_input']}

# 子任务结果
{chr(10).join(sections)}
{warning_text}
"""
    prompt = PromptBuilder.attach(
        state,
        prompt,
        kind="router.synthesis",
        sections=["user_question", "subtask_results", "failure_boundaries"],
    )
    state["_sources"] = sources  # type: ignore[typeddict-unknown-key]
    state["error"] = None
    if state.get("_streaming"):
        state["result"] = ""
        return state

    from app.config import config
    from app.llm.loader import LLMGenerationError
    from app.llm.providers import create_llm

    llm = create_llm(
        state.get("_model_id"),
        max_tokens=config.model_max_tokens,
        temperature=config.model_temperature,
        top_p=config.model_top_p,
    )
    try:
        synthesized = llm.generate(prompt)
    except LLMGenerationError:
        state["_route_execution_warnings"].append("synthesis_failed:llm_error")
        state["result"] = "\n\n".join(
            f"[{record['intent']}] {record.get('result', '')}"
            for record in successful
            if record.get("result")
        ) or "组合回答生成失败，请稍后重试。"
        return state
    state["result"] = synthesized
    return state


def _safe_subgraph_node(intent: Intent, subgraph):
    """Isolate subgraph exceptions so approved route plans can degrade safely."""
    def run(state: RouterState) -> RouterState:
        try:
            return subgraph.invoke(state)
        except Exception as exc:
            from app.llm.loader import LLMGenerationError

            if isinstance(exc, LLMGenerationError):
                raise
            logger.exception("%s subgraph failed", intent)
            state["result"] = ""
            state["error"] = f"{intent} subgraph failed"
            state.setdefault("_route_execution_warnings", []).append(
                f"subgraph_failed:{intent}"
            )
            return state

    return run


def finalize_node(state: RouterState) -> RouterState:
    """Finalize non-stream output through the shared public safety boundary."""
    if state.get("error"):
        state["result"] = "This request could not be completed. Please try again."
        return state

    result = state.get("result", "")
    if not result or state.get("_streaming"):
        return state

    prompt_meta = state.get("_prompt_meta", {})
    kind = str(prompt_meta.get("kind") or {
        "chat": "chat.answer",
        "search": "search.synthesis",
        "diet": "diet.recommendation",
        "motion": "motion.answer",
        "mcp": "mcp.format_result",
    }.get(state.get("intent", "chat"), "chat.answer"))
    checked = validate_public_output(result, kind=kind)
    state["result"] = checked.text
    if checked.violations:
        warnings = state.setdefault("_route_execution_warnings", [])
        warnings.extend(
            f"output_safety:{violation}"
            for violation in checked.violations
            if f"output_safety:{violation}" not in warnings
        )
    record_execution(
        state,
        "output_safety",
        SAFETY_POLICY_VERSION,
        degraded=not checked.safe,
        detail=("violations=" + ",".join(checked.violations)) if checked.violations else "passed",
    )
    return state


def build_router_graph():
    """Build the top-level router graph.

    Nodes: intent_classify -> [clarify/search/motion/diet/chat/mcp] -> finalize -> END
    """
    builder = StateGraph(RouterState)

    builder.add_node("intent_classify", intent_classify_node)
    builder.add_node("search", _safe_subgraph_node("search", build_search_subgraph()))
    builder.add_node("motion", _safe_subgraph_node("motion", build_motion_subgraph()))
    builder.add_node("diet", _safe_subgraph_node("diet", build_diet_subgraph()))
    builder.add_node("chat", _safe_subgraph_node("chat", build_chat_subgraph()))
    builder.add_node("mcp", _safe_subgraph_node("mcp", build_mcp_subgraph()))
    builder.add_node("clarify", clarification_response_node)
    builder.add_node("collect_route_result", collect_route_result_node)
    builder.add_node("synthesize_route_results", synthesize_route_results_node)
    builder.add_node("finalize", finalize_node)

    builder.set_entry_point("intent_classify")

    # Load shared knowledge base for all RAG subgraphs.
    from app.tools.retriever import load_shared_knowledge_base

    load_shared_knowledge_base("data/knowledge")

    builder.add_conditional_edges(
        "intent_classify",
        route_to_subgraph,
        {
            "search": "search",
            "motion": "motion",
            "diet": "diet",
            "chat": "chat",
            "mcp": "mcp",
            "clarify": "clarify",
        },
    )

    builder.add_edge("clarify", "finalize")

    for intent in ["search", "motion", "diet", "chat", "mcp"]:
        builder.add_edge(intent, "collect_route_result")
    builder.add_conditional_edges(
        "collect_route_result",
        route_after_collection,
        {
            "search": "search",
            "motion": "motion",
            "diet": "diet",
            "chat": "chat",
            "mcp": "mcp",
            "synthesize": "synthesize_route_results",
        },
    )
    builder.add_edge("synthesize_route_results", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()
