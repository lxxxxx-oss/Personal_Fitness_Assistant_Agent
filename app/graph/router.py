"""Top-level router graph: intent classification + conditional dispatch."""
import json
import logging
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict

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
    return f"""You are an intent classifier for a fitness assistant.

Choose exactly one intent:
- chat: general fitness knowledge, explanations, greetings, unclear requests
- search: latest/recent/news/research/look-up requests
- diet: personal diet, weight control, meal planning, calories, macros
- motion: exercise posture, motion analysis, uploaded .npz, technique review
- mcp: cooking recipes, dish recommendations, cooking steps

Return JSON only, with this schema:
{{
  "intent": "chat|search|diet|motion|mcp",
  "confidence": 0.0,
  "reason": "short reason",
  "needs_clarification": false
}}

User input:
{user_input}
"""


def _call_llm_router(prompt: str) -> Optional[str]:
    """LLM router provider hook.

    Phase 3 defines the contract but intentionally does not call a real model.
    Tests can monkeypatch this function; production can later wire it to LLMLoader.
    """
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


def _llm_classifier_route(user_input: str) -> RouteDecision:
    """Try the LLM classifier fallback contract.

    A decision is accepted only when the JSON is valid, the intent is allowed,
    no clarification is requested, and confidence is high enough.
    """
    prompt = _build_llm_router_prompt(user_input)
    raw = _call_llm_router(prompt)
    if not raw:
        return RouteDecision(
            intent="chat",
            confidence=0.0,
            reason="LLM router provider is not configured.",
            source="llm_unavailable",
            scores=_empty_scores(),
            matches=[],
        )

    payload = _extract_json_object(raw)
    if payload is None:
        return RouteDecision(
            intent="chat",
            confidence=0.0,
            reason="LLM router returned invalid JSON.",
            source="llm_parse_error",
            scores=_empty_scores(),
            matches=[f"llm_raw:{raw[:120]}"],
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
        return RouteDecision(
            intent="chat",
            confidence=0.0,
            reason=f"LLM router returned invalid intent: {intent!r}.",
            source="llm_invalid",
            scores=_empty_scores(),
            matches=[f"llm_payload:{payload}"],
        )

    if needs_clarification:
        return RouteDecision(
            intent="chat",
            confidence=confidence,
            reason=f"LLM router requested clarification: {reason}",
            source="llm_clarification",
            scores=_empty_scores(),
            matches=[f"llm_intent:{intent}", "needs_clarification:true"],
        )

    if confidence < LLM_ROUTER_MIN_CONFIDENCE:
        return RouteDecision(
            intent="chat",
            confidence=confidence,
            reason=(
                f"LLM router confidence {confidence:.2f} is below "
                f"{LLM_ROUTER_MIN_CONFIDENCE:.2f}: {reason}"
            ),
            source="llm_low_confidence",
            scores=_empty_scores(),
            matches=[f"llm_intent:{intent}"],
        )

    return RouteDecision(
        intent=intent,  # type: ignore[typeddict-item]
        confidence=round(min(confidence, 0.99), 2),
        reason=f"Selected {intent} by LLM classifier fallback: {reason}",
        source="llm_classifier",
        scores=_empty_scores(),
        matches=[f"llm_intent:{intent}"],
    )


def classify_intent_with_scores(user_input: str) -> RouteDecision:
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

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_intent, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = best_score - second_score

    if best_score < MIN_ROUTE_SCORE:
        semantic_decision = _semantic_route(user_input)
        if semantic_decision["source"] == "semantic_examples":
            return semantic_decision
        llm_decision = _llm_classifier_route(user_input)
        if llm_decision["source"] == "llm_classifier":
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
    )

    if confidence < SEMANTIC_TRIGGER_CONFIDENCE:
        semantic_decision = _semantic_route(user_input)
        if (
            semantic_decision["source"] == "semantic_examples"
            and semantic_decision["confidence"] > confidence
        ):
            semantic_decision["reason"] += (
                f" Rule router was low confidence: {reason}"
            )
            return semantic_decision
        llm_decision = _llm_classifier_route(user_input)
        if (
            llm_decision["source"] == "llm_classifier"
            and llm_decision["confidence"] > confidence
        ):
            llm_decision["reason"] += f" Rule router was low confidence: {reason}"
            return llm_decision

    return rule_decision


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
    return state["intent"]  # type: ignore


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
    builder.add_node("search", build_search_subgraph())
    builder.add_node("motion", build_motion_subgraph())
    builder.add_node("diet", build_diet_subgraph())
    builder.add_node("chat", build_chat_subgraph())
    builder.add_node("mcp", build_mcp_subgraph())
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
        builder.add_edge(intent, "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()
