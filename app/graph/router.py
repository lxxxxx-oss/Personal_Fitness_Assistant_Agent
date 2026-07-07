"""Top-level router graph: intent classification + conditional dispatch."""
import json
import logging
import re
import threading
import time
from collections import Counter
from typing import Any, Dict, List, Literal, NotRequired, Optional, Tuple, TypedDict

from langgraph.graph import END, StateGraph

from app.graph.state import RouterState
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


_LLM_ROUTER_METRICS_LOCK = threading.Lock()
_LLM_ROUTER_OUTCOMES: Counter[str] = Counter()
_LLM_ROUTER_SELECTIONS: Counter[str] = Counter()
_LLM_ROUTER_TOTAL_LATENCY_MS = 0.0
_LLM_ROUTER_MAX_LATENCY_MS = 0.0


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
MARGIN_FOR_HIGH_CONFIDENCE = 2.0
SEMANTIC_TRIGGER_CONFIDENCE = 0.72
SEMANTIC_MIN_CONFIDENCE = 0.62
LLM_ROUTER_MIN_CONFIDENCE = 0.70
ALLOWED_INTENTS = {"search", "motion", "diet", "chat", "mcp"}
LLM_REVIEW_AMBIGUITY_SIGNALS = {
    "close_rule_scores",
    "cross_domain_plan",
    "progress_diagnosis",
}
SUPPORTED_ROUTE_COMBINATIONS = {
    ("search", "diet"),
    ("search", "chat"),
    ("motion", "chat"),
    ("motion", "diet"),
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
    if best_score < MIN_ROUTE_SCORE:
        return 0.0
    raw = 0.55 + min(best_score / 12.0, 0.3) + min(margin / 8.0, 0.15)
    return round(min(raw, 0.95), 2)


def _semantic_features(text: str) -> set[str]:
    normalized = _normalize_text(text)
    compact = "".join(ch for ch in normalized if not ch.isspace())
    features: set[str] = set()
    for token in normalized.replace("?", " ").replace("？", " ").split():
        if token:
            features.add(token)
    for size in (2, 3):
        if len(compact) >= size:
            for idx in range(len(compact) - size + 1):
                features.add(compact[idx: idx + size])
    return features


SEMANTIC_EXAMPLE_FEATURES: Dict[Intent, List[Tuple[str, set[str]]]] = {
    intent: [(example, _semantic_features(example)) for example in examples]
    for intent, examples in SEMANTIC_EXAMPLES.items()
}


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    union = len(left | right)
    return intersection / union if union else 0.0


def _semantic_route(user_input: str) -> RouteDecision:
    query_features = _semantic_features(user_input)
    scores = _empty_scores()
    matches: List[str] = []

    for intent, examples in SEMANTIC_EXAMPLE_FEATURES.items():
        best_score = 0.0
        best_example = ""
        for example, example_features in examples:
            score = _jaccard_similarity(query_features, example_features)
            if score > best_score:
                best_score = score
                best_example = example
        scores[intent] = round(best_score, 4)
        if best_example and best_score > 0:
            matches.append(f"{intent}:example({best_example})={best_score:.2f}")

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_intent, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = best_score - second_score
    confidence = round(min(0.55 + best_score * 0.7 + margin * 0.4, 0.88), 2)

    if confidence < SEMANTIC_MIN_CONFIDENCE or best_score <= 0:
        return RouteDecision(
            intent="chat",
            confidence=0.0,
            reason="Semantic examples did not reach the minimum confidence.",
            source="semantic_fallback",
            scores=scores,
            matches=matches,
        )

    return RouteDecision(
        intent=best_intent,  # type: ignore[typeddict-item]
        confidence=confidence,
        reason=(
            f"Selected {best_intent} by semantic examples: "
            f"score={best_score:.2f}, margin={margin:.2f}, confidence={confidence:g}."
        ),
        source="semantic_examples",
        scores=scores,
        matches=matches,
    )


def _build_llm_router_prompt(user_input: str) -> str:
    """Build the strict JSON prompt for a future LLM classifier fallback."""
    return f"""待分类用户输入：<<<{user_input}>>>

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


def _call_llm_router(prompt: str) -> Optional[str]:
    """Call the configured local classifier; return None when disabled/unavailable."""
    from app.config import config

    if not config.llm_router_enabled:
        return None

    from app.llm.loader import LLMLoader

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=config.llm_router_max_tokens,
        temperature=0.0,
        top_p=1.0,
    )
    result = llm.generate(
        prompt,
        max_new_tokens=config.llm_router_max_tokens,
        temperature=0.0,
        top_p=1.0,
    )
    if result.startswith("[Error:"):
        logger.error("Local LLM router failed: %s", result)
        return None
    return result


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


def _llm_classifier_route(user_input: str) -> RouteDecision:
    """Try the LLM classifier fallback contract.

    A decision is accepted only when the JSON is valid, the intent is allowed,
    no clarification is requested, and confidence is high enough.
    """
    started_at = time.perf_counter()
    prompt = _build_llm_router_prompt(user_input)
    raw = _call_llm_router(prompt)
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


def _detect_ambiguity(text: str, scores: Dict[str, float]) -> List[str]:
    """Return structured reasons why deterministic routing may need review."""
    signals: List[str] = []

    if "先" in text and any(separator in text for separator in ("再", "然后")):
        signals.append("ordered_multi_task")

    if any(
        pattern in text
        for pattern in (
            "不需要具体做法",
            "不需要做法",
            "不要具体做法",
            "不要菜谱",
            "不想做饭",
            "不用做饭",
            "不下厨",
        )
    ):
        signals.append("recipe_negation")

    if "吃和练" in text:
        signals.append("cross_domain_plan")

    if "体重没变" in text or "训练是不是没效果" in text:
        signals.append("progress_diagnosis")

    plan_motion_patterns = (
        "练什么动作",
        "练哪些动作",
        "应该练什么动作",
        "应该练哪些动作",
        "训练计划",
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
        signals.append("plan_vs_motion")

    if scores["diet"] >= MIN_ROUTE_SCORE and scores["mcp"] >= MIN_ROUTE_SCORE:
        signals.append("diet_vs_recipe")

    if "权威" in text and any(term in text for term in ("资料", "说法", "研究")):
        signals.append("authority_lookup")

    ranked = sorted(scores.values(), reverse=True)
    if len(ranked) >= 2 and ranked[1] >= MIN_ROUTE_SCORE and ranked[0] - ranked[1] < 2:
        signals.append("close_rule_scores")

    return list(dict.fromkeys(signals))


def _classify_primary_intent_with_scores(user_input: str) -> RouteDecision:
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
    ambiguity_signals = _detect_ambiguity(text, scores)
    matches.extend(f"ambiguity:{signal}" for signal in ambiguity_signals)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_intent, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = best_score - second_score

    if best_score < MIN_ROUTE_SCORE:
        semantic_decision = _semantic_route(user_input)
        if semantic_decision["source"] == "semantic_examples":
            semantic_decision["ambiguity_signals"] = ambiguity_signals
            return semantic_decision
        llm_decision = _llm_classifier_route(user_input)
        if llm_decision["source"] == "llm_classifier":
            _record_llm_router_selection("selected")
            llm_decision["ambiguity_signals"] = ambiguity_signals
            return llm_decision
        return RouteDecision(
            intent="chat",
            confidence=0.0,
            reason=(
                "No route rule reached the minimum score; semantic fallback "
                f"did not decide; {llm_decision['reason']} Falling back to chat."
            ),
            source="fallback",
            scores=scores,
            matches=matches + llm_decision["matches"],
            ambiguity_signals=ambiguity_signals,
        )

    confidence = _confidence(best_score, margin)
    source = "weighted_rules"
    reason = (
        f"Selected {best_intent}: score={best_score:g}, "
        f"margin={margin:g}, confidence={confidence:g}."
    )
    if margin < MARGIN_FOR_HIGH_CONFIDENCE:
        reason += " Scores are close; keep this case in router evaluation."

    rule_decision = RouteDecision(
        intent=best_intent,  # type: ignore[typeddict-item]
        confidence=confidence,
        reason=reason,
        source=source,
        scores=scores,
        matches=matches,
        ambiguity_signals=ambiguity_signals,
    )

    llm_review_signals = [
        signal
        for signal in ambiguity_signals
        if signal in LLM_REVIEW_AMBIGUITY_SIGNALS
    ]
    if llm_review_signals and confidence >= SEMANTIC_TRIGGER_CONFIDENCE:
        llm_decision = _llm_classifier_route(user_input)
        if (
            llm_decision["source"] == "llm_classifier"
            and llm_decision["confidence"] > confidence
        ):
            llm_decision["ambiguity_signals"] = ambiguity_signals
            llm_decision["reason"] += (
                " Ambiguity detector triggered: "
                + ", ".join(llm_review_signals)
                + f". Deterministic decision was {best_intent}."
            )
            _record_llm_router_selection("selected")
            return llm_decision
        if llm_decision["source"] == "llm_classifier":
            _record_llm_router_selection("rejected_not_higher_confidence")
            rule_decision["matches"].append(
                "llm_rejected:not_higher_than_rule_confidence"
            )
        rule_decision["reason"] += (
            " Ambiguity detector triggered but LLM did not take over: "
            + ", ".join(llm_review_signals)
            + "."
        )
        rule_decision["matches"].extend(llm_decision["matches"])

    if confidence < SEMANTIC_TRIGGER_CONFIDENCE:
        semantic_decision = _semantic_route(user_input)
        if (
            semantic_decision["source"] == "semantic_examples"
            and semantic_decision["confidence"] > confidence
        ):
            semantic_decision["reason"] += (
                f" Rule router was low confidence: {reason}"
            )
            semantic_decision["ambiguity_signals"] = ambiguity_signals
            return semantic_decision
        llm_decision = _llm_classifier_route(user_input)
        if (
            llm_decision["source"] == "llm_classifier"
            and llm_decision["confidence"] > confidence
        ):
            llm_decision["reason"] += f" Rule router was low confidence: {reason}"
            llm_decision["ambiguity_signals"] = ambiguity_signals
            _record_llm_router_selection("selected")
            return llm_decision

    return rule_decision


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

    semantic = _semantic_route(text)
    if semantic["source"] == "semantic_examples":
        return semantic["intent"]
    return None


def _multi_intent_metadata(
    user_input: str,
    decision: RouteDecision,
) -> Tuple[List[Intent], List[Intent], str, bool]:
    """Derive observable multi-intent metadata without changing primary routing."""
    primary = decision["intent"]
    text = _normalize_text(user_input)
    clause_pattern = r"(?:，|,|；|;|。|然后|顺便|同时|并且|最好给(?:个)?|再(?=查|搜|给|分析|看|安排))"
    clauses = [part.strip() for part in re.split(clause_pattern, text) if part.strip()]

    observed: List[Intent] = []
    for clause in clauses:
        intent = _rule_intent_for_segment(clause)
        if intent and intent != primary and intent not in observed:
            observed.append(intent)

    for intent, score in sorted(
        decision["scores"].items(), key=lambda item: item[1], reverse=True
    ):
        if intent != primary and score >= MIN_ROUTE_SCORE and intent not in observed:
            observed.append(intent)  # type: ignore[arg-type]

    recipe_is_negated = (
        "recipe_negation" in decision.get("ambiguity_signals", [])
        or "不用给具体做法" in text
    )
    if recipe_is_negated and "mcp" in observed:
        observed.remove("mcp")

    if primary == "search":
        if decision["scores"].get("motion", 0.0) >= MIN_ROUTE_SCORE:
            observed = ["motion"]
        else:
            observed = ["chat"]
        if "什么动作最适合" in text:
            observed = ["chat"]
    elif primary == "motion" and not observed:
        if any(term in text for term in ("疼", "痛", "不舒服", "主要练哪里", "作用")):
            observed = ["chat"]
    elif primary == "chat":
        if "cross_domain_plan" in decision.get("ambiguity_signals", []):
            observed = ["diet"]
        elif "progress_diagnosis" in decision.get("ambiguity_signals", []):
            observed = ["diet"] if "体重没变" in text else []
        elif any(term in text for term in (
            "圆肩",
            "骨盆前倾",
            "恢复训练",
            "练什么动作",
            "练哪些动作",
        )):
            observed = ["motion"]
    elif primary == "diet":
        has_explicit_recipe_task = any(
            term in text
            for term in ("做法", "怎么做", "推荐一道", "具体晚餐菜", "一道菜")
        )
        has_ingredient_context = any(
            term in text for term in ("冰箱", "现有食材", "这些食材")
        )
        if recipe_is_negated or (
            "mcp" in observed and not has_explicit_recipe_task and not has_ingredient_context
        ):
            observed = [intent for intent in observed if intent != "mcp"]
        if has_ingredient_context and "mcp" not in observed:
            observed.append("mcp")
    elif primary == "mcp" and "diet" not in observed:
        if any(term in text for term in DIET_PLANNING_TERMS):
            observed.append("diet")

    explicit_sequence = (
        ("先" in text and any(token in text for token in ("再", "然后")))
        or any(token in text for token in ("顺便", "然后", "最好给", "再给"))
    )
    route_plan: List[Intent] = [primary]
    if explicit_sequence:
        route_plan.extend(intent for intent in observed if intent not in route_plan)

    ambiguity_signals = decision.get("ambiguity_signals", [])
    needs_clarification = (
        "cross_domain_plan" in ambiguity_signals and len(route_plan) == 1
    )
    if observed:
        reason = (
            f"Primary intent is {primary}; observed secondary intents: "
            + ", ".join(observed)
            + "."
        )
    else:
        reason = f"Only the primary intent {primary} was observed."
    if explicit_sequence and len(route_plan) > 1:
        reason += " Explicit sequencing language produced an ordered route plan."
    if needs_clarification:
        reason += " Cross-domain planning details are insufficient for safe composition."

    return observed, route_plan, reason, needs_clarification


def classify_intent_with_scores(user_input: str) -> RouteDecision:
    """Classify primary intent and attach Phase 4 multi-intent observations."""
    decision = _classify_primary_intent_with_scores(user_input)
    secondary, route_plan, reason, needs_clarification = _multi_intent_metadata(
        user_input, decision
    )
    decision["primary_intent"] = decision["intent"]
    decision["secondary_intents"] = secondary
    decision["route_plan"] = route_plan
    decision["multi_intent_reason"] = reason
    decision["needs_clarification"] = needs_clarification
    return decision


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

    if has_cooking_action and not has_diet_planning_term:
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


def classify_intent(user_input: str) -> str:
    """Return only the selected intent for backward-compatible callers."""
    return classify_intent_with_scores(user_input)["intent"]


def intent_classify_node(state: RouterState) -> RouterState:
    """Set intent and route metadata based on weighted rules."""
    decision = classify_intent_with_scores(state["user_input"])
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
    requested_plan = decision["route_plan"]
    plan_tuple = tuple(requested_plan)
    warnings: List[str] = []
    if decision["needs_clarification"]:
        execution_plan = [decision["primary_intent"]]
        warnings.append("multi_intent_execution_skipped:needs_clarification")
    elif len(requested_plan) == 1:
        execution_plan = requested_plan
    elif plan_tuple in SUPPORTED_ROUTE_COMBINATIONS:
        execution_plan = requested_plan
    else:
        execution_plan = [decision["primary_intent"]]
        warnings.append("multi_intent_execution_skipped:unsupported_route_plan")
    state["_route_execution_plan"] = execution_plan
    state["_route_execution_cursor"] = 0
    state["_active_intent"] = execution_plan[0]
    state["_route_results"] = []
    state["_route_execution_warnings"] = warnings
    state["_execution"] = []
    logger.info(
        "Intent: %s confidence=%.2f source=%s input=%s",
        decision["intent"],
        decision["confidence"],
        decision["source"],
        state["user_input"][:50],
    )
    return state


def route_to_subgraph(
    state: RouterState,
) -> Literal["search", "motion", "diet", "chat", "mcp"]:
    """Conditional edge: route based on intent."""
    return state.get("_active_intent", state["intent"])  # type: ignore


def collect_route_result_node(state: RouterState) -> RouterState:
    """Capture one subgraph output and prepare the next approved route step."""
    active_intent = state.get("_active_intent", state["intent"])
    record = {
        "intent": active_intent,
        "result": state.get("result", ""),
        "error": state.get("error"),
        "prompt": state.get("_prompt", ""),
        "sources": list(state.get("_sources", [])),  # type: ignore[arg-type]
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
    state["_prompt"] = prompt
    state["_sources"] = sources  # type: ignore[typeddict-unknown-key]
    state["error"] = None
    if state.get("_streaming"):
        state["result"] = ""
        return state

    from app.config import config
    from app.llm.loader import LLMLoader

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=config.model_max_tokens,
        temperature=config.model_temperature,
        top_p=config.model_top_p,
    )
    synthesized = llm.generate(prompt)
    if synthesized.startswith("[Error:"):
        state["_route_execution_warnings"].append("synthesis_failed:llm_error")
        state["result"] = "\n\n".join(
            f"[{record['intent']}] {record.get('result', '')}"
            for record in successful
            if record.get("result")
        ) or synthesized
    else:
        state["result"] = synthesized
    return state


def _safe_subgraph_node(intent: Intent, subgraph):
    """Isolate subgraph exceptions so approved route plans can degrade safely."""
    def run(state: RouterState) -> RouterState:
        try:
            return subgraph.invoke(state)
        except Exception as exc:
            logger.exception("%s subgraph failed", intent)
            state["result"] = ""
            state["error"] = f"{intent} subgraph failed: {exc}"
            state.setdefault("_route_execution_warnings", []).append(
                f"subgraph_failed:{intent}"
            )
            return state

    return run


def finalize_node(state: RouterState) -> RouterState:
    """Final node: ensure result is valid, log any errors."""
    if state.get("error"):
        state["result"] = f"Error: {state['error']}"
    return state


def build_router_graph():
    """Build the top-level router graph.

    Nodes: intent_classify -> [search/motion/diet/chat/mcp] -> finalize -> END
    """
    builder = StateGraph(RouterState)

    builder.add_node("intent_classify", intent_classify_node)
    builder.add_node("search", _safe_subgraph_node("search", build_search_subgraph()))
    builder.add_node("motion", _safe_subgraph_node("motion", build_motion_subgraph()))
    builder.add_node("diet", _safe_subgraph_node("diet", build_diet_subgraph()))
    builder.add_node("chat", _safe_subgraph_node("chat", build_chat_subgraph()))
    builder.add_node("mcp", _safe_subgraph_node("mcp", build_mcp_subgraph()))
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
        },
    )

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
