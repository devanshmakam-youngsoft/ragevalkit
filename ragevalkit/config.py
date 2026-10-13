"""Library configuration. All values come from serve() parameters; .env overrides are also supported."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Access control
    eval_users: str = "admin:admin123"
    eval_secret: str = "dev-only-change-me"
    session_hours: int = 12
    session_cookie: str = "eval_session"
    require_login: bool = True

    # Environment mode
    # "dev"  — full dashboard + eval routes (default)
    # "uat"  — same as dev, but exposes UAT recording endpoint (/api/uat/ask)
    # "prod" — blocks dashboard and all eval routes; only /api/health responds
    eval_env: str = "dev"

    # Recording mode (controls what @step captures during eval runs)
    # "eval"     — record steps only during eval runner calls (default)
    # "uat"      — eval + UAT endpoint calls
    # "off"      — disable all step recording (eval still runs, just no step data)
    record_mode: str = "eval"

    # Recording detail level (controls HOW MUCH is captured per step)
    # "all"      — inputs, outputs, material, sources, timing (default)
    # "selected" — only steps where developer explicitly set .material or .sources
    # "off"      — only step name + elapsed time (no content captured)
    record_detail: str = "all"

    # Judge LLM (any LiteLLM model string: "groq/...", "gemini/...", "openai/...", "ollama/...")
    judge_model: str = "groq/openai/gpt-oss-120b"
    judge_api_key: str = ""        # optional; LiteLLM also reads env vars automatically
    judge_prompt_override: str = ""  # replaces GRADER_PROMPT entirely when set
    judge_temperature: float = 0.0
    judge_retries: int = 3

    # Scoring / recommendation
    answer_weight: float = 0.6
    material_weight: float = 0.4
    recommendation_tolerance: float = 0.25
    max_response_time: float | None = None

    # Metrics to run
    run_keyword_recall: bool = True
    run_bm25: bool = True
    run_semantic_similarity: bool = True
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Storage
    store_path: Path = Path("eval_store.json")
    dataset_sheet: str = "dataset"
    default_dataset: Path | None = None

    # Server
    backend_host: str = "127.0.0.1"
    backend_port: int = 8001

    # --- Answer extraction: keys tried when fn() returns a dict/object ---
    answer_keys: list[str] = [
        "answer", "response", "output", "result", "text",
        "content", "message", "generated_text", "generation", "completion",
    ]

    # --- Signature detection: parameter name aliases ---
    history_params: list[str] = [
        "history", "chat_history", "messages", "conversation", "turns", "context",
    ]
    session_params: list[str] = [
        "session_id", "session", "thread_id", "conversation_id", "user_id",
    ]

    # --- History format passed to fn() ---
    # "dict"  → [{"question": "...", "answer": "..."}]  (default, simple)
    # "openai" → [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    history_format: str = "dict"

    # --- Dataset / column handling ---
    # Map the developer's xlsx column names → internal names.
    # Example: {"user_query": "question", "gold_answer": "expected_answer"}
    column_map: dict[str, str] = {}
    # Extra xlsx columns to carry through into every result receipt.
    extra_columns: list[str] = []

    # --- Type detection ---
    # Rows whose `type` value (lowercased) is in this set are treated as conversational:
    # they skip material scoring and lexical metrics.
    conversational_types: list[str] = ["conversational"]

    # --- Prompts ---
    # Override the LLM summary prompt (the one that writes the run commentary).
    summary_prompt: str = ""

    @property
    def inputs_dir(self) -> Path:
        return self.store_path.parent / "eval_inputs"
