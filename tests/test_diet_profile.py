"""Structured Diet profile extraction tests."""
from app.graph.subgraphs.diet import DietProfile, extract_profile_node, parse_diet_profile


def test_parse_diet_profile_accepts_json_inside_model_text():
    profile, warning = parse_diet_profile(
        '结果如下：\n```json\n{"height_cm": "170", "weight_kg": 80, '
        '"gender": "男性", "goal": "减脂", "preferences": ["素食", "不吃辣"]}\n```'
    )

    assert warning is None
    assert profile.height_cm == 170
    assert profile.weight_kg == 80
    assert profile.gender == "男"
    assert profile.preferences == "素食、不吃辣"


def test_parse_diet_profile_normalizes_unknown_values():
    profile, warning = parse_diet_profile(
        '{"height_cm":"未知","weight_kg":null,"gender":"未知",'
        '"goal":"增肌","preferences":"素食"}'
    )

    assert warning is None
    assert profile.height_cm is None
    assert profile.weight_kg is None
    assert profile.goal == "增肌"


def test_parse_diet_profile_rejects_out_of_range_values():
    profile, warning = parse_diet_profile(
        '{"height_cm":999,"weight_kg":80,"gender":"男",'
        '"goal":"减脂","preferences":"无"}'
    )

    assert profile == DietProfile()
    assert warning == "profile_validation_failed"


def test_extract_profile_node_records_safe_fallback_warning(monkeypatch):
    from app.llm.loader import LLMLoader

    monkeypatch.setattr(LLMLoader, "generate", lambda self, prompt: "not-json")
    state = {
        "user_input": "我想减脂",
        "_route_execution_warnings": [],
    }

    result = extract_profile_node(state)

    assert result["_user_profile"] == DietProfile().model_dump()
    assert result["_route_execution_warnings"] == [
        "diet_profile_fallback:profile_json_missing"
    ]
