"""How your pipeline function is called and how its answer is read."""
from ragevalkit.config.base import Settings


class FunctionAdapterSettings(Settings):
    # Answer extraction: keys tried when fn() returns a dict/object
    answer_keys: list[str] = [
        "answer", "response", "output", "result", "text",
        "content", "message", "generated_text", "generation", "completion",
    ]

    # Signature detection: parameter name aliases
    history_params: list[str] = [
        "history", "chat_history", "messages", "conversation", "turns", "context",
    ]
    session_params: list[str] = [
        "session_id", "session", "thread_id", "conversation_id", "user_id",
    ]

    # History format passed to fn()
    # "dict"  → [{"question": "...", "answer": "..."}]  (default, simple)
    # "openai" → [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    history_format: str = "dict"

    # Rows whose `type` value (lowercased) is in this set are treated as conversational:
    # they skip material scoring and text metrics.
    conversational_types: list[str] = ["conversational"]
