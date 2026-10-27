"""``ragevalkit.serve``: validate the options, build the config and app, and run the server."""
import logging
import secrets
import threading
import webbrowser
from typing import Callable

from ragevalkit import llm
from ragevalkit.api import create_app
from ragevalkit.config import Config
from ragevalkit.config.dotenv import load_dotenv
from ragevalkit.exceptions import ConfigError
from ragevalkit.logs import configure_logging


def serve(
    fn: Callable,
    # --- server ---
    port: int = 8001,
    store_path: str = "eval_store.json",
    open_browser: bool = True,
    # --- environment / recording modes ---
    eval_env: str = "dev",
    record_mode: str = "eval",
    record_detail: str = "all",
    max_step_value_chars: int = 1000,
    max_material_chars: int = 20000,
    # --- judge (LLM or custom) ---
    judge_model: str = "groq/openai/gpt-oss-120b",
    judge_api_key: str | None = None,
    judge_prompt: str | None = None,
    judge_retries: int = 3,
    judge_fn: Callable | None = None,
    # --- writing test cases from documents ---
    generator_model: str | None = None,
    # --- scoring / recommendation ---
    answer_weight: float = 0.6,
    material_weight: float = 0.4,
    recommendation_tolerance: float = 0.25,
    max_response_time: float | None = None,
    # --- built-in metrics ---
    run_keyword_recall: bool = True,
    run_bm25: bool = True,
    run_semantic_similarity: bool = True,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    # --- custom / extra metrics ---
    extra_metrics: dict[str, Callable] | None = None,
    # --- access control ---
    users: str = "admin:admin123",
    secret: str | None = None,
    require_login: bool = True,
    # --- dataset ---
    default_dataset: str | None = None,
    column_map: dict[str, str] | None = None,
    extra_columns: list[str] | None = None,
    # --- fn signature / return-value detection ---
    answer_keys: list[str] | None = None,
    history_params: list[str] | None = None,
    session_params: list[str] | None = None,
    history_format: str = "dict",
    # --- type / conversational detection ---
    conversational_types: list[str] | None = None,
    # --- source verification ---
    source_check_mode: str = "keyword",
    # --- hooks ---
    on_complete: Callable | None = None,
    session_id_fn: Callable | None = None,
    summary_prompt: str | None = None,
) -> None:
    """Start the ragevalkit evaluation server.

    Blocks until the server is stopped (Ctrl+C). Opens a browser automatically
    unless ``open_browser=False``.

    Args:
        fn: Your pipeline function. Accepted signatures::

                fn(question: str) -> str
                fn(question: str, history: list) -> str   # stateless, runner passes history
                fn(question: str, session_id: str) -> str # stateful, you manage history

            Can also return a ``dict`` (ragevalkit extracts the answer via ``answer_keys``)
            or a Pydantic model. Async functions are supported.
        port: HTTP port for the server. Default ``8001``.
        store_path: Path to the TinyDB JSON results file. Created automatically.
        open_browser: Open the dashboard in a browser 1.5 s after startup.
        eval_env: Environment mode. ``"dev"`` (default) enables the full dashboard.
            ``"prod"`` blocks the dashboard and all eval routes — only ``/api/health``
            responds, suitable for embedding the function behind a production server
            without exposing the eval UI.  ``"uat"`` is like dev but logs that UAT
            recording is active.
        record_mode: Controls when ``@ragevalkit.step()`` fires. ``"eval"`` (default)
            records steps only during eval runner calls. ``"off"`` disables step
            recording entirely even during eval (eval still runs, just no step data).
        record_detail: Controls how much detail each step captures. ``"all"`` (default)
            records inputs, outputs, material, sources, and timing. ``"selected"``
            records only steps where the developer explicitly set ``.material`` or
            ``.sources``. ``"off"`` records only step name and elapsed time.
        max_step_value_chars: How much of a step's inputs, output and ``note()`` values is kept for display
            (default 1000). A longer value ends with "… (+N more characters)"; a long list of numbers, such as
            an embedding, is shown as ``[N numbers]``.
        max_material_chars: How much retrieved text the judge reads per question (default 20000), cut with the
            same kind of marker. Material comes from steps that declare it (``s.material = …`` or
            ``@step("retrieval", material=True)``).
        judge_model: LiteLLM model string. Examples: ``"groq/llama-3.3-70b-versatile"``,
            ``"gemini/gemini-1.5-pro"``, ``"openai/gpt-4o"``, ``"ollama/llama3"``.
        judge_api_key: Explicit API key for the judge. If omitted, LiteLLM reads the
            matching env var (``GROQ_API_KEY``, ``GEMINI_API_KEY``, ``OPENAI_API_KEY``…).
        judge_prompt: Custom system prompt for the grader. Replaces the built-in rubric
            entirely — useful for non-RAG systems (customer support, coding assistants…).
        judge_retries: Retries on transient LLM failures before the row is marked failed.
        judge_fn: Callable that fully replaces the LLM judge::

                def my_judge(question, expected, generated, material) -> dict:
                    return {"answer_marks": 8, "answer_comment": "Good."}

        generator_model: LiteLLM model that writes test cases from uploaded documents (Test Cases →
            Generate from documents). Defaults to ``judge_model``. The text of the documents is sent to it,
            so choose a model you are allowed to send them to (a local ``ollama/...`` model works).
        answer_weight: Weight of ``answer_marks`` in the version recommendation score.
        material_weight: Weight of ``material_marks``. Set to ``0`` for systems with no retrieval.
        recommendation_tolerance: Versions within this quality-score delta are considered tied.
        max_response_time: Exclude version candidates slower than this (seconds) from recommendation.
        run_keyword_recall: Compute keyword recall between expected and generated answers.
        run_bm25: Compute BM25 lexical similarity score.
        run_semantic_similarity: Compute cosine similarity via a local embedding model.
        embedding_model: ``sentence-transformers`` model name for semantic similarity.
        extra_metrics: Additional scoring functions run alongside built-ins::

                extra_metrics={"rouge_1": lambda exp, gen: rouge(exp, gen)}

            Each callable receives ``(expected_answer, generated_answer)`` and returns a float.
        users: Comma-separated ``"name:password"`` pairs, e.g. ``"alice:pw1,bob:pw2"``.
        secret: Cookie signing secret. Auto-generated (random) if omitted.
        require_login: Set to ``False`` to disable the login screen entirely (useful locally).
        default_dataset: Path to a default ``.xlsx`` or ``.csv`` dataset shown in the dashboard.
        column_map: Rename xlsx columns before validation, e.g.
            ``{"user_query": "question", "gold_answer": "expected_answer"}``.
        extra_columns: Extra xlsx columns to carry into every result receipt, e.g.
            ``["difficulty", "topic"]``.
        answer_keys: Keys tried (in order) when ``fn()`` returns a dict. Default covers the
            most common names: ``answer``, ``response``, ``output``, ``result``…
        history_params: Parameter names that mean "pass conversation history", e.g.
            ``["history", "chat_history", "messages"]``.
        session_params: Parameter names that mean "pass a session ID", e.g.
            ``["session_id", "thread_id"]``.
        history_format: Format of the history list passed to ``fn()``.
            ``"dict"`` (default) → ``[{"question": …, "answer": …}]``;
            ``"openai"`` → ``[{"role": "user", …}, {"role": "assistant", …}]``.
        conversational_types: Row ``type`` values (case-insensitive) that skip material
            scoring and lexical metrics, e.g. ``["conversational", "greeting"]``.
        source_check_mode: How to verify retrieved sources against ``expected_sources`` in
            the dataset. ``"keyword"`` (default) uses substring matching — separate AND-groups
            with ``|`` and OR-alternatives within a group with ``,`` (e.g.
            ``"doc_a | doc_b.pdf,doc_c"`` requires doc_a AND either doc_b or doc_c).
            ``"llm"`` uses the judge model for fuzzy / alias-tolerant matching.
            ``"off"`` disables source verification entirely.
        on_complete: Called once after a run finishes (success or failure)::

                def on_complete(summary: dict, rows: list[dict]) -> None:
                    send_slack_notification(summary)

        session_id_fn: Returns the session ID for a given ``chat_id``. Defaults to
            ``uuid.uuid4()``. Supply a deterministic function to replay conversations
            with the same session against a stateful backend::

                session_id_fn=lambda chat_id: f"eval-{chat_id}"

        summary_prompt: Override the system prompt used by the LLM to write the run's
            "pitfalls and suggestions" shown in the dashboard. The required JSON reply format is
            appended automatically, so only describe what to look for and the tone.
    """
    # --- input validation (fail fast with a clear message) ---
    _VALID_SOURCE_MODES = {"keyword", "llm", "off"}
    if not callable(fn):
        raise ConfigError(f"fn must be callable, got {type(fn).__name__!r}")
    if source_check_mode not in _VALID_SOURCE_MODES:
        raise ConfigError(
            f"source_check_mode={source_check_mode!r} is not valid. "
            f"Choose one of: {sorted(_VALID_SOURCE_MODES)}"
        )
    if judge_retries < 1:
        raise ConfigError(f"judge_retries must be >= 1, got {judge_retries}")
    if answer_weight < 0 or material_weight < 0:
        raise ConfigError("answer_weight and material_weight must be >= 0")
    if history_format not in {"dict", "openai"}:
        raise ConfigError(
            f"history_format={history_format!r} is not valid. Choose 'dict' or 'openai'."
        )

    import uvicorn

    load_dotenv()  # populate os.environ so LiteLLM can find GROQ_API_KEY, GEMINI_API_KEY, etc.

    # Build overrides for Config fields that have sensible defaults.
    # Only pass a key when the caller explicitly set it — passing None would
    # overwrite the pydantic-settings default with an empty/None value.
    cfg_extra: dict = {}
    if answer_keys is not None:
        cfg_extra["answer_keys"] = answer_keys
    if history_params is not None:
        cfg_extra["history_params"] = history_params
    if session_params is not None:
        cfg_extra["session_params"] = session_params
    if conversational_types is not None:
        cfg_extra["conversational_types"] = conversational_types
    if column_map is not None:
        cfg_extra["column_map"] = column_map
    if extra_columns is not None:
        cfg_extra["extra_columns"] = extra_columns
    if summary_prompt is not None:
        cfg_extra["summary_prompt"] = summary_prompt
    cfg_extra["source_check_mode"] = source_check_mode
    if generator_model:
        cfg_extra["generator_model"] = generator_model

    config = Config(
        backend_port=port,
        store_path=store_path,
        eval_env=eval_env,
        record_mode=record_mode,
        record_detail=record_detail,
        step_value_chars=max_step_value_chars,
        material_chars=max_material_chars,
        judge_model=judge_model,
        judge_api_key=judge_api_key or "",
        judge_prompt_override=judge_prompt or "",
        judge_retries=judge_retries,
        answer_weight=answer_weight,
        material_weight=material_weight,
        recommendation_tolerance=recommendation_tolerance,
        max_response_time=max_response_time,
        run_keyword_recall=run_keyword_recall,
        run_bm25=run_bm25,
        run_semantic_similarity=run_semantic_similarity,
        embedding_model=embedding_model,
        eval_users=users,
        eval_secret=secret or secrets.token_hex(32),
        require_login=require_login,
        default_dataset=default_dataset,
        history_format=history_format,
        **cfg_extra,
    )
    configure_logging(config)
    if config.eval_env != "prod":
        try:
            llm.load_litellm()   # once, here, before the server and its worker threads exist (see llm/loader.py)
        except ImportError:
            logging.getLogger(__name__).warning("litellm is not installed: judging and test case generation will not work.")
    app = create_app(
        config, fn=fn,
        judge_fn=judge_fn,
        extra_metrics=extra_metrics,
        on_complete=on_complete,
        session_id_fn=session_id_fn,
    )
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=port)
