"""The AI judge: which model grades answers, and how it is called."""
from ragevalkit.core.config.base import Settings


class JudgeSettings(Settings):
    """Options for the LLM judge: model, credentials, prompts and how retrieved sources are checked."""

    # Any LiteLLM model string: "groq/...", "gemini/...", "openai/...", "ollama/..."
    judge_model: str = "groq/openai/gpt-oss-120b"
    judge_api_key: str = ""        # optional; LiteLLM also reads env vars automatically
    judge_prompt_override: str = ""  # replaces the built-in grading rubric when set; the JSON reply format is always added
    judge_temperature: float | None = None   # None: the model's own default is used
    judge_retries: int = 3

    # Override the LLM summary prompt (the one that writes the run's watch-outs and suggestions).
    summary_prompt: str = ""

    # Source check mode
    # "keyword" — fast substring match on pipe-separated expected_sources (default)
    # "llm"     — LLM decides whether retrieved sources cover expected sources; adds source_score + source_comment
    # "off"     — skip source verification entirely
    source_check_mode: str = "keyword"
