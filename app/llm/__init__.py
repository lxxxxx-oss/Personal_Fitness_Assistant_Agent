__all__ = ["LLMLoader"]


def __getattr__(name):
    """Keep the public import without loading the model stack during config import."""
    if name == "LLMLoader":
        from app.llm.loader import LLMLoader

        return LLMLoader
    raise AttributeError(name)
