"""Tests for the minimal ToolRegistry governance layer."""

import pytest

from app.tools.registry import (
    ToolRegistry,
    ToolSpec,
    build_default_tool_registry,
    validate_input_schema,
)
from app.tools.types import ErrorCode, ToolResult


def _echo_spec(name="test.echo", executor=None, **overrides):
    return ToolSpec(
        name=name,
        description="Echo a query string.",
        input_schema={
            "type": "object",
            "required": ["query"],
            "additionalProperties": False,
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 20},
            },
        },
        permission="read_only",
        executor=executor or (lambda args: ToolResult.ok(data=args["query"])),
        **overrides,
    )


def test_register_and_execute_success():
    registry = ToolRegistry()
    registry.register(_echo_spec())

    result = registry.execute("test.echo", {"query": "squat"})

    assert result.ok
    assert result.data == "squat"
    assert result.meta["tool_name"] == "test.echo"
    assert result.meta["permission"] == "read_only"
    assert registry.audit_log[-1]["ok"] is True


def test_duplicate_register_raises():
    registry = ToolRegistry()
    spec = _echo_spec()
    registry.register(spec)

    with pytest.raises(ValueError):
        registry.register(spec)


def test_missing_tool_returns_data_not_found():
    registry = ToolRegistry()

    result = registry.execute("missing.tool", {})

    assert not result.ok
    assert result.error_code == ErrorCode.DATA_NOT_FOUND


def test_schema_validation_rejects_missing_required_param():
    schema = {
        "type": "object",
        "required": ["query"],
        "properties": {"query": {"type": "string"}},
    }

    result = validate_input_schema(schema, {})

    assert not result.ok
    assert result.error_code == ErrorCode.INVALID_PARAM
    assert "query" in result.error_message


def test_schema_validation_rejects_wrong_type_and_unknown_param():
    registry = ToolRegistry()
    registry.register(_echo_spec())

    wrong_type = registry.execute("test.echo", {"query": 123})
    unknown = registry.execute("test.echo", {"query": "ok", "extra": True})

    assert wrong_type.error_code == ErrorCode.INVALID_PARAM
    assert unknown.error_code == ErrorCode.INVALID_PARAM


def test_permission_denied_when_context_restricts_permissions():
    registry = ToolRegistry()
    registry.register(_echo_spec())

    result = registry.execute(
        "test.echo",
        {"query": "squat"},
        context={"allowed_permissions": ["network"]},
    )

    assert not result.ok
    assert result.error_code == ErrorCode.PERMISSION_DENIED


def test_executor_exception_is_wrapped():
    registry = ToolRegistry()
    registry.register(
        _echo_spec(executor=lambda args: (_ for _ in ()).throw(RuntimeError("boom")))
    )

    result = registry.execute("test.echo", {"query": "squat"})

    assert not result.ok
    assert result.error_code == ErrorCode.INTERNAL_ERROR
    assert "boom" in result.error_message


def test_retry_and_fallback_are_bounded():
    calls = {"primary": 0}

    def primary(args):
        calls["primary"] += 1
        return ToolResult.fail(ErrorCode.NETWORK_ERROR, "temporary")

    registry = ToolRegistry()
    registry.register(
        _echo_spec(
            name="test.primary",
            executor=primary,
            max_retries=1,
            fallback_tool="test.fallback",
        )
    )
    registry.register(
        _echo_spec(
            name="test.fallback",
            executor=lambda args: ToolResult.ok(data="fallback"),
        )
    )

    result = registry.execute("test.primary", {"query": "squat"})

    assert result.ok
    assert result.data == "fallback"
    assert result.meta["fallback_from"] == "test.primary"
    assert calls["primary"] == 2


def test_default_registry_exposes_representative_tools():
    registry = build_default_tool_registry()
    names = {spec.name for spec in registry.list_tools()}

    assert {
        "knowledge.retrieve",
        "search.tavily",
        "motion.compare_pose",
        "mcp.call_tool",
    }.issubset(names)


def test_default_search_tool_can_execute_in_mock_mode(monkeypatch):
    from app import config as config_module

    monkeypatch.setattr(config_module.config, "tavily_api_key", "")
    registry = build_default_tool_registry()

    result = registry.execute(
        "search.tavily",
        {"query": "squat form", "max_results": 1},
        context={"allowed_permissions": ["network"]},
    )

    assert result.ok
    assert result.meta["is_mock"] is True
    assert result.meta["tool_name"] == "search.tavily"
