"""全局配置管理."""
import os
from dataclasses import dataclass, field

from app.llm.context_window import derive_context_budget, resolve_model_context_window


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_KNOWLEDGE_DB_PATH = "data/rag/knowledge.db"
DEFAULT_MEMORY_VECTOR_DB_PATH = "data/memory/memory_vectors.db"


def _get_int_env(name: str, default: int) -> int:
    """Read an integer environment variable with a safe fallback."""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float_env(name: str, default: float) -> float:
    """Read a float environment variable with a safe fallback."""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_bool_env(name: str, default: bool) -> bool:
    """Read a boolean environment variable with a safe fallback."""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass
class Config:
    # LLM
    model_path: str = field(
        default_factory=lambda: os.getenv(
            "MODEL_PATH",
            "D:/Users/Agent/model/models/Qwen/Qwen3-0___6B",
        )
    )
    model_device: str = field(default_factory=lambda: os.getenv("MODEL_DEVICE", "cpu"))
    model_max_tokens: int = field(
        default_factory=lambda: _get_int_env("MODEL_MAX_TOKENS", 1024)
    )
    model_context_window_override: int = field(
        default_factory=lambda: _get_int_env("MODEL_CONTEXT_WINDOW", 0)
    )
    model_context_fallback_tokens: int = field(
        default_factory=lambda: _get_int_env("MODEL_CONTEXT_FALLBACK_TOKENS", 4096)
    )
    context_safety_tokens: int = field(
        default_factory=lambda: _get_int_env("CONTEXT_SAFETY_TOKENS", 256)
    )
    context_compact_trigger_ratio: float = field(
        default_factory=lambda: _get_float_env("CONTEXT_COMPACT_TRIGGER_RATIO", 0.8)
    )
    model_context_window_tokens: int = field(init=False, default=0)
    model_context_window_source: str = field(init=False, default="")
    model_temperature: float = field(
        default_factory=lambda: _get_float_env("MODEL_TEMPERATURE", 0.6)
    )
    model_top_p: float = field(default_factory=lambda: _get_float_env("MODEL_TOP_P", 0.95))
    llm_mock: bool = field(
        default_factory=lambda: os.getenv("LLM_MOCK", "").lower() in {"1", "true", "yes"}
    )
    llm_router_enabled: bool = field(
        default_factory=lambda: os.getenv("LLM_ROUTER_ENABLED", "").lower()
        in {"1", "true", "yes"}
    )
    llm_router_max_tokens: int = field(
        default_factory=lambda: _get_int_env("LLM_ROUTER_MAX_TOKENS", 128)
    )
    router_embedding_enabled: bool = field(
        default_factory=lambda: _get_bool_env("ROUTER_EMBEDDING_ENABLED", False)
    )
    router_embedding_model: str = field(
        default_factory=lambda: os.getenv("ROUTER_EMBEDDING_MODEL")
        or os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    )
    router_embedding_min_confidence: float = field(
        default_factory=lambda: _get_float_env("ROUTER_EMBEDDING_MIN_CONFIDENCE", 0.68)
    )
    router_embedding_min_margin: float = field(
        default_factory=lambda: _get_float_env("ROUTER_EMBEDDING_MIN_MARGIN", 0.05)
    )

    # Memory
    memory_max_turns: int = field(
        default_factory=lambda: _get_int_env("MEMORY_MAX_TURNS", 6)
    )
    memory_db_path: str = field(
        default_factory=lambda: os.getenv("MEMORY_DB_PATH", "data/memory/memory.db")
    )
    context_compact_trigger_chars: int = field(
        default_factory=lambda: _get_int_env("COMPACT_TRIGGER_CHARS", 0)
    )
    context_max_prompt_chars: int = field(
        default_factory=lambda: _get_int_env("MAX_PROMPT_CHARS", 0)
    )
    context_compact_trigger_tokens: int = field(
        default_factory=lambda: _get_int_env("COMPACT_TRIGGER_TOKENS", 0)
    )
    context_max_prompt_tokens: int = field(
        default_factory=lambda: _get_int_env("MAX_PROMPT_TOKENS", 0)
    )
    conversation_summary_enabled: bool = field(
        default_factory=lambda: _get_bool_env("CONVERSATION_SUMMARY_ENABLED", True)
    )
    conversation_summary_trigger_chars: int = field(
        default_factory=lambda: _get_int_env(
            "CONVERSATION_SUMMARY_TRIGGER_CHARS",
            3000,
        )
    )
    conversation_summary_max_chars: int = field(
        default_factory=lambda: _get_int_env("CONVERSATION_SUMMARY_MAX_CHARS", 1200)
    )
    conversation_summary_trigger_tokens: int = field(
        default_factory=lambda: _get_int_env(
            "CONVERSATION_SUMMARY_TRIGGER_TOKENS", 900
        )
    )
    conversation_summary_max_tokens: int = field(
        default_factory=lambda: _get_int_env("CONVERSATION_SUMMARY_MAX_TOKENS", 360)
    )
    # Retriever
    retriever_top_k: int = field(
        default_factory=lambda: _get_int_env("RETRIEVER_TOP_K", 5)
    )
    retriever_strategy: str = field(
        default_factory=lambda: os.getenv("RETRIEVER_STRATEGY", "hybrid").lower()
    )
    retriever_candidate_k: int = field(
        default_factory=lambda: _get_int_env("RETRIEVER_CANDIDATE_K", 20)
    )
    retriever_rrf_k: int = field(
        default_factory=lambda: _get_int_env("RETRIEVER_RRF_K", 60)
    )
    retriever_threshold: float = field(
        default_factory=lambda: _get_float_env("RETRIEVER_THRESHOLD", 0.5)
    )
    retriever_chunk_chars: int = field(
        default_factory=lambda: _get_int_env("RETRIEVER_CHUNK_CHARS", 500)
    )
    retriever_chunk_overlap_chars: int = field(
        default_factory=lambda: _get_int_env("RETRIEVER_CHUNK_OVERLAP_CHARS", 80)
    )
    retriever_knowledge_version: str = field(
        default_factory=lambda: os.getenv("RETRIEVER_KNOWLEDGE_VERSION", "v2")
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv(
            "EMBEDDING_MODEL",
            DEFAULT_EMBEDDING_MODEL,
        )
    )
    retriever_backend: str = field(
        default_factory=lambda: os.getenv("RETRIEVER_BACKEND", "sqlite_faiss").lower()
    )
    retriever_fallback_to_memory: bool = field(
        default_factory=lambda: _get_bool_env(
            "RETRIEVER_FALLBACK_TO_MEMORY", True
        )
    )
    retriever_db_path: str = field(
        default_factory=lambda: os.getenv(
            "RETRIEVER_DB_PATH", DEFAULT_KNOWLEDGE_DB_PATH
        )
    )
    memory_vector_enabled: bool = field(
        default_factory=lambda: _get_bool_env("MEMORY_VECTOR_ENABLED", False)
    )
    memory_vector_db_path: str = field(
        default_factory=lambda: os.getenv(
            "MEMORY_VECTOR_DB_PATH", DEFAULT_MEMORY_VECTOR_DB_PATH
        )
    )
    retriever_timeout_seconds: float = field(
        default_factory=lambda: _get_float_env("RETRIEVER_TIMEOUT_SECONDS", 3.0)
    )

    # Tavily Search
    tavily_api_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))

    # Motion
    motion_library_dir: str = field(
        default_factory=lambda: os.getenv("MOTION_LIBRARY_DIR", "data/motions")
    )
    react_max_iterations: int = field(
        default_factory=lambda: _get_int_env("REACT_MAX_ITERATIONS", 5)
    )

    # MCP
    mcp_server_command: str = field(
        default_factory=lambda: os.getenv("MCP_SERVER_COMMAND", "mock")
    )

    # API
    api_host: str = field(default_factory=lambda: os.getenv("API_HOST", "127.0.0.1"))
    api_port: int = field(default_factory=lambda: _get_int_env("API_PORT", 8000))

    def __post_init__(self) -> None:
        """Reject internally inconsistent settings before serving requests."""
        context_window = resolve_model_context_window(
            self.model_path,
            override_tokens=self.model_context_window_override,
            fallback_tokens=self.model_context_fallback_tokens,
        )
        budget = derive_context_budget(
            context_window.tokens,
            output_reserve_tokens=self.model_max_tokens,
            safety_tokens=self.context_safety_tokens,
            compact_trigger_ratio=self.context_compact_trigger_ratio,
            max_prompt_cap_tokens=self.context_max_prompt_tokens,
            compact_trigger_cap_tokens=self.context_compact_trigger_tokens,
        )
        self.model_context_window_tokens = context_window.tokens
        self.model_context_window_source = context_window.source
        self.context_max_prompt_tokens = budget.max_prompt_tokens
        self.context_compact_trigger_tokens = budget.compact_trigger_tokens
        if self.context_max_prompt_chars == 0:
            self.context_max_prompt_chars = self.context_max_prompt_tokens * 4
        if self.context_compact_trigger_chars == 0:
            self.context_compact_trigger_chars = self.context_compact_trigger_tokens * 4

        positive_values = {
            "model_max_tokens": self.model_max_tokens,
            "model_context_fallback_tokens": self.model_context_fallback_tokens,
            "context_safety_tokens": self.context_safety_tokens,
            "memory_max_turns": self.memory_max_turns,
            "context_compact_trigger_chars": self.context_compact_trigger_chars,
            "context_max_prompt_chars": self.context_max_prompt_chars,
            "context_compact_trigger_tokens": self.context_compact_trigger_tokens,
            "context_max_prompt_tokens": self.context_max_prompt_tokens,
            "conversation_summary_trigger_chars": self.conversation_summary_trigger_chars,
            "conversation_summary_max_chars": self.conversation_summary_max_chars,
            "conversation_summary_trigger_tokens": self.conversation_summary_trigger_tokens,
            "conversation_summary_max_tokens": self.conversation_summary_max_tokens,
            "retriever_top_k": self.retriever_top_k,
            "retriever_candidate_k": self.retriever_candidate_k,
            "retriever_rrf_k": self.retriever_rrf_k,
            "retriever_chunk_chars": self.retriever_chunk_chars,
            "api_port": self.api_port,
        }
        invalid = [name for name, value in positive_values.items() if value <= 0]
        if invalid:
            raise ValueError(f"configuration values must be positive: {', '.join(invalid)}")
        if self.context_max_prompt_chars < 1200:
            raise ValueError("MAX_PROMPT_CHARS must be at least 1200")
        if self.context_max_prompt_tokens < 1200:
            raise ValueError("MAX_PROMPT_TOKENS must be at least 1200")
        if self.context_compact_trigger_chars > self.context_max_prompt_chars:
            raise ValueError("COMPACT_TRIGGER_CHARS must not exceed MAX_PROMPT_CHARS")
        if self.context_compact_trigger_tokens > self.context_max_prompt_tokens:
            raise ValueError("COMPACT_TRIGGER_TOKENS must not exceed MAX_PROMPT_TOKENS")
        if not 0.0 <= self.retriever_threshold <= 1.0:
            raise ValueError("RETRIEVER_THRESHOLD must be between 0 and 1")
        if self.retriever_strategy not in {"dense", "hybrid"}:
            raise ValueError("RETRIEVER_STRATEGY must be 'dense' or 'hybrid'")
        if self.retriever_backend not in {"sqlite_faiss", "memory"}:
            raise ValueError(
                "RETRIEVER_BACKEND must be 'sqlite_faiss' or 'memory'"
            )
        if not self.retriever_db_path.strip():
            raise ValueError("RETRIEVER_DB_PATH must not be empty")
        if not self.memory_vector_db_path.strip():
            raise ValueError("MEMORY_VECTOR_DB_PATH must not be empty")
        if self.retriever_timeout_seconds <= 0:
            raise ValueError("RETRIEVER_TIMEOUT_SECONDS must be positive")
        if self.retriever_candidate_k > 100:
            raise ValueError("RETRIEVER_CANDIDATE_K must be at most 100")
        if not 0.0 <= self.router_embedding_min_confidence <= 1.0:
            raise ValueError("ROUTER_EMBEDDING_MIN_CONFIDENCE must be between 0 and 1")
        if not 0.0 <= self.router_embedding_min_margin <= 1.0:
            raise ValueError("ROUTER_EMBEDDING_MIN_MARGIN must be between 0 and 1")
        if not 0.0 < self.model_top_p <= 1.0:
            raise ValueError("MODEL_TOP_P must be greater than 0 and at most 1")
        if self.model_temperature < 0.0:
            raise ValueError("MODEL_TEMPERATURE must not be negative")


# 全局单例
config = Config()
