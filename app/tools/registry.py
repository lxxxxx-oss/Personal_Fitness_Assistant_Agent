"""Minimal tool registry for controlled tool execution.

The registry is intentionally small: it records tool metadata, validates
structured arguments, checks a coarse permission label, executes the callable,
and normalizes every outcome as ToolResult.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.tools.types import ErrorCode, ToolResult


ToolExecutor = Callable[[Dict[str, Any]], ToolResult]


@dataclass(frozen=True)
class ToolSpec:
    """Metadata and execution policy for one internal tool."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    permission: str
    executor: ToolExecutor
    timeout_seconds: float = 10.0
    max_retries: int = 0
    retryable_error_codes: Tuple[str, ...] = (ErrorCode.NETWORK_ERROR,)
    fallback_tool: Optional[str] = None
    scope: str = "general"
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """Register, validate, and execute internal tools.

    This class does not decide business flow. LangGraph nodes still decide
    which tool to call; the registry only centralizes tool execution governance.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        self.audit_log: List[Dict[str, Any]] = []

    def register(self, spec: ToolSpec) -> None:
        err = _validate_tool_spec(spec)
        if err:
            raise ValueError(err)
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def list_tools(self, scope: Optional[str] = None) -> List[ToolSpec]:
        specs = list(self._tools.values())
        if scope is None:
            return specs
        return [spec for spec in specs if spec.scope == scope]

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(name)
        return self._tools[name]

    def validate_args(self, spec: ToolSpec, args: Dict[str, Any]) -> ToolResult:
        return validate_input_schema(spec.input_schema, args)

    def check_permission(
        self, spec: ToolSpec, context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        context = context or {}
        allowed = context.get("allowed_permissions")
        if allowed is None:
            return ToolResult.ok(permission=spec.permission)
        allowed_set = set(allowed)
        if spec.permission not in allowed_set:
            return ToolResult.fail(
                ErrorCode.PERMISSION_DENIED,
                f"Permission '{spec.permission}' is not allowed for tool '{spec.name}'",
                tool_name=spec.name,
                permission=spec.permission,
            )
        return ToolResult.ok(permission=spec.permission)

    def execute(
        self,
        name: str,
        args: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        context = context or {}
        execution_id = str(context.get("execution_id") or uuid.uuid4())
        return self._execute(
            name,
            args or {},
            context,
            visited=(),
            execution_id=execution_id,
            fallback_from=None,
        )

    def _execute(
        self,
        name: str,
        args: Dict[str, Any],
        context: Dict[str, Any],
        visited: Tuple[str, ...],
        execution_id: str,
        fallback_from: Optional[str],
    ) -> ToolResult:
        started = time.perf_counter()
        try:
            spec = self.get(name)
        except KeyError:
            result = ToolResult.fail(
                ErrorCode.DATA_NOT_FOUND,
                f"Tool is not registered: {name}",
                tool_name=name,
            )
            return self._finalize(
                name=name,
                spec=None,
                result=result,
                started=started,
                attempts=0,
                execution_id=execution_id,
                fallback_from=fallback_from,
            )

        validation = self.validate_args(spec, args)
        if not validation.ok:
            return self._finalize(
                name=name,
                spec=spec,
                result=validation,
                started=started,
                attempts=0,
                execution_id=execution_id,
                fallback_from=fallback_from,
            )

        permission = self.check_permission(spec, context)
        if not permission.ok:
            return self._finalize(
                name=name,
                spec=spec,
                result=permission,
                started=started,
                attempts=0,
                execution_id=execution_id,
                fallback_from=fallback_from,
            )

        attempts = 0
        result: Optional[ToolResult] = None
        max_attempts = max(1, spec.max_retries + 1)
        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            result = _run_executor(spec, args)
            if result.ok:
                break
            if result.error_code not in spec.retryable_error_codes:
                break

        assert result is not None
        result = self._finalize(
            name=name,
            spec=spec,
            result=result,
            started=started,
            attempts=attempts,
            execution_id=execution_id,
            fallback_from=fallback_from,
        )

        if (
            not result.ok
            and spec.fallback_tool
            and spec.fallback_tool not in visited
            and spec.fallback_tool != spec.name
        ):
            fallback = self._execute(
                spec.fallback_tool,
                args,
                context,
                visited=visited + (spec.name,),
                execution_id=execution_id,
                fallback_from=spec.name,
            )
            return fallback
        return result

    def _finalize(
        self,
        name: str,
        spec: Optional[ToolSpec],
        result: ToolResult,
        started: float,
        attempts: int,
        execution_id: str,
        fallback_from: Optional[str],
    ) -> ToolResult:
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        result.meta.update(
            {
                "execution_id": execution_id,
                "tool_name": spec.name if spec else name,
                "permission": spec.permission if spec else None,
                "attempts": attempts,
                "timeout_seconds": spec.timeout_seconds if spec else None,
                "duration_ms": duration_ms,
            }
        )
        if fallback_from:
            result.meta["fallback_from"] = fallback_from
        self._audit(
            name=name,
            result=result,
            attempts=attempts,
            execution_id=execution_id,
            duration_ms=duration_ms,
            permission=spec.permission if spec else None,
            fallback_from=fallback_from,
        )
        return result

    def _audit(
        self,
        name: str,
        result: ToolResult,
        attempts: int,
        execution_id: str,
        duration_ms: float,
        permission: Optional[str],
        fallback_from: Optional[str],
    ) -> None:
        self.audit_log.append(
            {
                "execution_id": execution_id,
                "tool_name": name,
                "permission": permission,
                "ok": result.ok,
                "error_code": result.error_code,
                "attempts": attempts,
                "duration_ms": duration_ms,
                "fallback_from": fallback_from,
            }
        )


def validate_input_schema(schema: Dict[str, Any], args: Dict[str, Any]) -> ToolResult:
    """Validate a small JSON-schema-like subset used by ToolSpec."""
    if not isinstance(args, dict):
        return ToolResult.fail(ErrorCode.INVALID_PARAM, "tool args must be a dict")
    if schema.get("type", "object") != "object":
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "input_schema root type must be object",
        )

    properties = schema.get("properties", {})
    required = schema.get("required", [])
    for field_name in required:
        if field_name not in args:
            return ToolResult.fail(
                ErrorCode.INVALID_PARAM,
                f"Missing required parameter: {field_name}",
            )

    for field_name, value in args.items():
        if field_name not in properties:
            if schema.get("additionalProperties", True):
                continue
            return ToolResult.fail(
                ErrorCode.INVALID_PARAM,
                f"Unknown parameter: {field_name}",
            )
        err = _validate_field(field_name, value, properties[field_name])
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err)
    return ToolResult.ok(data=args)


def build_default_tool_registry() -> ToolRegistry:
    """Create a registry with representative project tools.

    The default registry is a side-channel governance entry point. Existing
    LangGraph subgraphs do not depend on it yet.
    """
    from app.config import config
    from app.tools.mcp_client import MCPClient
    from app.tools.motion_tool import compute_pose_sequence_similarity
    from app.tools.retriever import get_shared_retriever
    from app.tools.search_tool import TavilySearchTool

    registry = ToolRegistry()

    registry.register(
        ToolSpec(
            name="knowledge.retrieve",
            description="Search the configured fitness knowledge retriever.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 500},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
                    "threshold": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
            },
            permission="read_knowledge",
            executor=lambda args: get_shared_retriever().search(
                args["query"],
                args.get("top_k", 5),
                args.get("threshold", 0.3),
            ),
            timeout_seconds=config.milvus_timeout_seconds,
            scope="knowledge",
        )
    )
    registry.register(
        ToolSpec(
            name="search.tavily",
            description="Search current fitness information through Tavily or mock fallback.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 500},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
                },
            },
            permission="network",
            executor=lambda args: TavilySearchTool(config.tavily_api_key).search(
                args["query"],
                args.get("max_results", 5),
            ),
            timeout_seconds=10.0,
            max_retries=1,
            scope="search",
        )
    )
    registry.register(
        ToolSpec(
            name="motion.compare_pose",
            description="Compare two schema-compatible PoseSequence objects.",
            input_schema={
                "type": "object",
                "required": ["user_sequence", "reference_sequence"],
                "additionalProperties": False,
                "properties": {
                    "user_sequence": {"type": "pose_sequence"},
                    "reference_sequence": {"type": "pose_sequence"},
                },
            },
            permission="local_compute",
            executor=lambda args: compute_pose_sequence_similarity(
                args["user_sequence"],
                args["reference_sequence"],
            ),
            timeout_seconds=20.0,
            scope="motion",
        )
    )
    registry.register(
        ToolSpec(
            name="mcp.call_tool",
            description="Call a configured MCP tool through the lightweight MCP client.",
            input_schema={
                "type": "object",
                "required": ["tool_name"],
                "additionalProperties": False,
                "properties": {
                    "tool_name": {"type": "string", "minLength": 1, "maxLength": 128},
                    "arguments": {"type": "object"},
                },
            },
            permission="subprocess",
            executor=lambda args: MCPClient(config.mcp_server_command).call_tool(
                args["tool_name"],
                args.get("arguments", {}),
            ),
            timeout_seconds=10.0,
            scope="mcp",
        )
    )
    return registry


def _validate_tool_spec(spec: ToolSpec) -> Optional[str]:
    if not isinstance(spec.name, str) or not spec.name.strip():
        return "ToolSpec.name must be a non-empty string"
    if not isinstance(spec.description, str) or not spec.description.strip():
        return "ToolSpec.description must be a non-empty string"
    if not isinstance(spec.input_schema, dict):
        return "ToolSpec.input_schema must be a dict"
    if not isinstance(spec.permission, str) or not spec.permission.strip():
        return "ToolSpec.permission must be a non-empty string"
    if not callable(spec.executor):
        return "ToolSpec.executor must be callable"
    if spec.timeout_seconds <= 0:
        return "ToolSpec.timeout_seconds must be positive"
    if spec.max_retries < 0:
        return "ToolSpec.max_retries must not be negative"
    return None


def _validate_field(name: str, value: Any, rules: Dict[str, Any]) -> Optional[str]:
    expected = rules.get("type")
    if expected == "string":
        if not isinstance(value, str):
            return f"'{name}' must be a string"
        if len(value) < rules.get("minLength", 0):
            return f"'{name}' too short"
        if "maxLength" in rules and len(value) > rules["maxLength"]:
            return f"'{name}' too long"
    elif expected == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return f"'{name}' must be an integer"
        if "minimum" in rules and value < rules["minimum"]:
            return f"'{name}' must be >= {rules['minimum']}"
        if "maximum" in rules and value > rules["maximum"]:
            return f"'{name}' must be <= {rules['maximum']}"
    elif expected == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return f"'{name}' must be a number"
        if "minimum" in rules and value < rules["minimum"]:
            return f"'{name}' must be >= {rules['minimum']}"
        if "maximum" in rules and value > rules["maximum"]:
            return f"'{name}' must be <= {rules['maximum']}"
    elif expected == "object":
        if not isinstance(value, dict):
            return f"'{name}' must be an object"
    elif expected == "array":
        if not isinstance(value, list):
            return f"'{name}' must be an array"
    elif expected == "pose_sequence":
        from app.tools.pose_sequence import PoseSequence

        if not isinstance(value, PoseSequence):
            return f"'{name}' must be a PoseSequence"
    elif expected is not None:
        return f"Unsupported schema type for '{name}': {expected}"

    if "enum" in rules and value not in rules["enum"]:
        return f"'{name}' must be one of {rules['enum']}"
    return None


def _run_executor(spec: ToolSpec, args: Dict[str, Any]) -> ToolResult:
    try:
        result = spec.executor(args)
    except Exception as exc:
        return ToolResult.fail(
            ErrorCode.INTERNAL_ERROR,
            f"Tool '{spec.name}' raised an exception: {exc}",
        )
    if isinstance(result, ToolResult):
        return result
    return ToolResult.fail(
        ErrorCode.INTERNAL_ERROR,
        f"Tool '{spec.name}' returned non-ToolResult output",
        data=result,
    )
