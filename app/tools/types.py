"""Shared types for tool results, error codes, and parameter validation.

All tools in the fitness assistant use these types to ensure
consistent error handling and output formatting across the system.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


# --- Error Codes ---

class ErrorCode:
    """Standardized error codes for all tools.

    Usage:
        return ToolResult.error(ErrorCode.NETWORK_ERROR, "Connection refused")
    """

    # Environment / configuration
    CONFIG_MISSING = "CONFIG_MISSING"       # API key, model path, etc. not set
    NETWORK_ERROR = "NETWORK_ERROR"         # DNS, timeout, connection refused
    PERMISSION_DENIED = "PERMISSION_DENIED" # Operation not allowed

    # Input validation
    INVALID_PARAM = "INVALID_PARAM"         # Parameter out of range, wrong type

    # Data / resource
    DATA_NOT_FOUND = "DATA_NOT_FOUND"       # File missing, search returned nothing

    # Internal
    INTERNAL_ERROR = "INTERNAL_ERROR"       # Unexpected failure, bug


# --- Tool Result ---

@dataclass
class ToolResult:
    """Unified return type for all tool operations.

    Success:
        ToolResult.ok(data={"items": [...]}, meta={"mode": "embedding"})

    Failure:
        ToolResult.fail(ErrorCode.NETWORK_ERROR, "Tavily API unreachable")
    """

    ok: bool
    data: Any = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    meta: dict = field(default_factory=dict)

    @classmethod
    def ok(cls, data: Any = None, **meta) -> "ToolResult":
        """Create a successful result."""
        return cls(ok=True, data=data, meta=meta if meta else {})

    @classmethod
    def fail(
        cls,
        error_code: str,
        error_message: str = "",
        data: Any = None,
        **meta,
    ) -> "ToolResult":
        """Create a failed result."""
        return cls(
            ok=False,
            data=data,
            error_code=error_code,
            error_message=error_message,
            meta=meta if meta else {},
        )


# --- Parameter Validators ---

def check_str_nonempty(value: str, param_name: str) -> Optional[str]:
    """Return error message if value is empty or not a string."""
    if not isinstance(value, str) or not value.strip():
        return f"'{param_name}' must be a non-empty string"
    return None


def check_str_len(
    value: str, param_name: str, min_len: int = 1, max_len: int = 4096
) -> Optional[str]:
    """Return error message if string length is out of range."""
    if not isinstance(value, str):
        return f"'{param_name}' must be a string"
    if len(value) < min_len:
        return f"'{param_name}' too short (min {min_len} chars)"
    if len(value) > max_len:
        return f"'{param_name}' too long (max {max_len} chars)"
    return None


def check_int_range(
    value: int, param_name: str, min_val: int = 1, max_val: int = 100
) -> Optional[str]:
    """Return error message if integer is out of range."""
    if not isinstance(value, int):
        return f"'{param_name}' must be an integer"
    if value < min_val or value > max_val:
        return f"'{param_name}' must be between {min_val} and {max_val}"
    return None


def check_float_range(
    value: float, param_name: str, min_val: float = 0.0, max_val: float = 1.0
) -> Optional[str]:
    """Return error message if float is out of range."""
    if not isinstance(value, (int, float)):
        return f"'{param_name}' must be a number"
    if value < min_val or value > max_val:
        return f"'{param_name}' must be between {min_val} and {max_val}"
    return None
