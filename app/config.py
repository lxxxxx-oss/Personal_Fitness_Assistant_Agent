"""全局配置管理."""
import os
from dataclasses import dataclass, field


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

    # Memory
    memory_max_turns: int = field(
        default_factory=lambda: _get_int_env("MEMORY_MAX_TURNS", 6)
    )
    memory_db_path: str = field(
        default_factory=lambda: os.getenv("MEMORY_DB_PATH", "data/memory/memory.db")
    )
    context_compact_trigger_chars: int = field(
        default_factory=lambda: _get_int_env("COMPACT_TRIGGER_CHARS", 6000)
    )
    context_max_prompt_chars: int = field(
        default_factory=lambda: _get_int_env("MAX_PROMPT_CHARS", 8192)
    )

    # Retriever
    retriever_top_k: int = field(
        default_factory=lambda: _get_int_env("RETRIEVER_TOP_K", 5)
    )
    retriever_threshold: float = field(
        default_factory=lambda: _get_float_env("RETRIEVER_THRESHOLD", 0.5)
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv(
            "EMBEDDING_MODEL",
            "shibing624/text2vec-base-chinese",
        )
    )
    retriever_backend: str = field(
        default_factory=lambda: os.getenv("RETRIEVER_BACKEND", "memory").lower()
    )
    retriever_fallback_to_memory: bool = field(
        default_factory=lambda: _get_bool_env(
            "RETRIEVER_FALLBACK_TO_MEMORY", True
        )
    )
    milvus_uri: str = field(
        default_factory=lambda: os.getenv(
            "MILVUS_URI", "http://127.0.0.1:19530"
        )
    )
    milvus_token: str = field(
        default_factory=lambda: os.getenv("MILVUS_TOKEN", ""),
        repr=False,
    )
    milvus_collection_name: str = field(
        default_factory=lambda: os.getenv("MILVUS_COLLECTION_NAME")
        or os.getenv("MILVUS_COLLECTION", "fitness_knowledge")
    )
    memory_milvus_enabled: bool = field(
        default_factory=lambda: _get_bool_env("MEMORY_MILVUS_ENABLED", False)
    )
    memory_milvus_collection_name: str = field(
        default_factory=lambda: os.getenv(
            "MEMORY_MILVUS_COLLECTION_NAME",
            "fitness_user_memory",
        )
    )
    milvus_index_type: str = field(
        default_factory=lambda: os.getenv("MILVUS_INDEX_TYPE", "IVF_FLAT").upper()
    )
    milvus_nlist: int = field(
        default_factory=lambda: _get_int_env("MILVUS_NLIST", 128)
    )
    milvus_nprobe: int = field(
        default_factory=lambda: _get_int_env("MILVUS_NPROBE", 16)
    )
    milvus_timeout_seconds: float = field(
        default_factory=lambda: _get_float_env("MILVUS_TIMEOUT_SECONDS", 3.0)
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


# 全局单例
config = Config()
