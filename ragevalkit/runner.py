"""
RunManager — the evaluation engine.

EXECUTION MODEL
---------------
Every call to RunManager.start() launches a daemon thread named "eval-{version}".
The HTTP response returns immediately (202 Accepted) while the thread works.
Progress is published via run.events (a plain list) which the SSE endpoint
streams to the dashboard by polling it every 0.3 s.

WHY a daemon thread (not asyncio)?
  The developer's fn() may block for seconds (LLM calls, DB queries).
  A daemon thread can block freely without stalling the FastAPI event loop.
  daemon=True means the thread is killed automatically if the server exits.

CALL FLOW (one question)
------------------------
  _execute()
    └─ _process_row()
         ├─ _call_fn()             ← calls developer's fn(); recording captures steps + flags
         ├─ _source_check()        ← compares expected_sources against recorded sources (if column present)
         ├─ lexical metrics        ← keyword_recall, bm25_score, semantic_similarity
         ├─ extra_metrics          ← any custom metric fns passed to serve()
         └─ _grade()              ← LLM judge or custom judge_fn

SIGNATURE DETECTION
-------------------
_detect_sig() inspects the developer's function ONCE at startup (not per call).
It checks parameter names against configurable alias sets and caches the
result so every question pays zero inspection cost at eval time.

HISTORY FORMAT
--------------
Internally history is always stored as [{"question": ..., "answer": ...}].
_build_history() converts to the format the developer's fn expects
("dict" stays as-is; "openai" → [{"role": "user", ...}, {"role": "assistant", ...}]).

STOP A RUNNING EVAL
-------------------
POST /api/runs/{run_id}/stop sets Run.stop_requested = True.
The _execute() loop checks this flag at the start of each row iteration.
When triggered, it finalises the partial results (writes them to store) and
emits a "stopped" event.

QUESTION FINGERPRINTING
-----------------------
The dataset's question set is hashed on load and stored in the run summary as
question_fingerprint. The dashboard can compare fingerprints across versions to
warn when questions changed between runs.
"""
import asyncio
import inspect
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

import pandas as pd

from ragevalkit import lexical, recording
from ragevalkit.casetypes import is_non_rag
from ragevalkit.config import Config
from ragevalkit.dataset import parse_source_groups
from ragevalkit.exceptions import RunBusy
from ragevalkit.judge import Judge
from ragevalkit.store import EvalStore, build_group_stats, build_summary, finish_insights, stats_for_llm

logger = logging.getLogger(__name__)

# Module-level defaults — overridden by Config values at RunManager init time.
_ANSWER_KEYS    = ("answer", "response", "output", "result", "text", "content",
                   "message", "generated_text", "generation", "completion")
_HISTORY_ALIASES = {"history", "chat_history", "messages", "conversation", "turns", "context"}
_SESSION_ALIASES = {"session_id", "session", "thread_id", "conversation_id", "user_id"}



# ---------------------------------------------------------------------------
# Signature / return-value helpers
# ---------------------------------------------------------------------------

def _detect_sig(fn: Callable, session_aliases=None, history_aliases=None) -> str:
    """Returns 'session_id' | 'history' | 'question' based on fn's parameter names.

    Priority: session_id > history > question.
    A function that accepts a session_id is assumed to be stateful (manages its own
    conversation history); the runner still builds history but passes it only to
    functions that explicitly declare a history parameter.
    """
    s_aliases = set(session_aliases) if session_aliases is not None else _SESSION_ALIASES
    h_aliases = set(history_aliases) if history_aliases is not None else _HISTORY_ALIASES
    params = set(inspect.signature(fn).parameters)
    if params & s_aliases:
        return "session_id"
    if params & h_aliases:
        return "history"
    return "question"


def _sig_kwarg(fn: Callable, aliases: set[str]) -> str:
    """Return the actual parameter name from fn that matches one of the aliases."""
    matched = set(inspect.signature(fn).parameters) & aliases
    return next(iter(matched), list(aliases)[0])


def _coerce_to_str(result, answer_keys=None) -> str:
    """
    Turn any RAG function return value into a plain string.
    Handles str, dict (tries answer_keys in order), pydantic model, or any object.
    """
    keys = answer_keys if answer_keys is not None else _ANSWER_KEYS
    if isinstance(result, str):
        return result
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    elif hasattr(result, "dict") and callable(result.dict):
        try:
            result = result.dict()
        except Exception:
            pass
    if isinstance(result, dict):
        for key in keys:
            if key in result:
                return str(result[key]) if not isinstance(result[key], str) else result[key]
        import json
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            return str(result)
    for key in keys:
        val = getattr(result, key, None)
        if val is not None:
            return str(val)
    return str(result)


def _call_sync(fn: Callable, *args, **kwargs):
    """Call fn whether it is sync or async; always returns synchronously."""
    if inspect.iscoroutinefunction(fn):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    return ex.submit(asyncio.run, fn(*args, **kwargs)).result()
            return loop.run_until_complete(fn(*args, **kwargs))
        except RuntimeError:
            return asyncio.run(fn(*args, **kwargs))
    return fn(*args, **kwargs)


def _build_history(turns: list[dict], fmt: str) -> list[dict]:
    """
    Convert internal history to the format the developer's function expects.

    fmt="dict"   → [{"question": "...", "answer": "..."}]   (default)
    fmt="openai" → [{"role": "user", "content": "..."},
                    {"role": "assistant", "content": "..."}]
    """
    if fmt == "openai":
        msgs = []
        for t in turns:
            msgs.append({"role": "user",      "content": t.get("question", "")})
            msgs.append({"role": "assistant", "content": t.get("answer",   "")})
        return msgs
    return list(turns)  # default "dict" format


def _source_check(expected_str: str, recorded: list) -> dict:
    """Compare expected_sources against recorded sources.

    Format: groups separated by | (ALL must pass);
            alternatives within a group separated by , (ANY ONE satisfies the group).

    Example: "1.txt , 2.txt | 3.txt"
      Group 1: 1.txt OR 2.txt must be retrieved (any one is enough)
      Group 2: 3.txt must be retrieved
      Both groups must pass for source_match = True.

    Single-level usage (no commas) is identical to the old pipe-only format.
    """
    groups = parse_source_groups(expected_str)
    if not groups:
        return {"source_match": None, "matched_sources": [], "missing_sources": []}
    recorded_lower = [str(s).lower() for s in (recorded or [])]
    matched_sources: list[str] = []
    missing_sources: list[str] = []
    for alternatives in groups:
        hit = next(
            (alt for alt in alternatives
             if any(alt.lower() in r or r in alt.lower() for r in recorded_lower)),
            None,
        )
        if hit:
            matched_sources.append(hit)
        else:
            missing_sources.append(" , ".join(alternatives))
    return {
        "source_match": len(missing_sources) == 0,
        "matched_sources": matched_sources,
        "missing_sources": missing_sources,
    }


# ---------------------------------------------------------------------------
# Run / RunManager
# ---------------------------------------------------------------------------

class Run:
    def __init__(self, version: str, total: int, dataset_name: str):
        self.run_id   = str(uuid.uuid4())
        self.version  = version
        self.dataset_name = dataset_name
        self.status   = "running"
        self.total    = total
        self.done     = 0
        self.current_question = ""
        self.started  = datetime.now(timezone.utc)
        self.error: str | None = None
        self.events: list[dict] = []
        self.summary: dict | None = None
        self.stop_requested: bool = False  # set True via POST /api/runs/{run_id}/stop
        self.notes: str = ""
        self.group_names: list[str] = []
        self.from_library: bool = False   # df came from stored test cases (no re-import needed)
        self.dataset_id: str = ""         # source group id for single-group library runs

    def snapshot(self) -> dict:
        return {
            "run_id": self.run_id,
            "version": self.version,
            "status": self.status,
            "total": self.total,
            "done": self.done,
            "current_question": self.current_question,
            "date": self.started.isoformat(),
            "dataset": self.dataset_name,
            "error": self.error,
        }

    def emit(self, event_type: str, **data) -> None:
        self.events.append({"type": event_type, **self.snapshot(), **data})


class RunManager:
    """
    Drives evaluation runs.

    Runtime hooks (all optional, passed via ``create_app``):

    * ``judge_fn(question, expected, generated, material) -> dict``
        Completely replaces the LLM judge.  The dict must contain at least
        ``answer_marks`` (int 0–10).  Optional keys: ``answer_comment``,
        ``material_marks``, ``material_comment``.

    * ``extra_metrics: dict[str, Callable[[str, str], float]]``
        Additional metrics run alongside built-ins.
        Each callable receives ``(expected_answer, generated_answer)``
        and should return a float.  Example::

            extra_metrics={"rouge_1": compute_rouge1, "bleu": compute_bleu}

    * ``on_complete(summary: dict, rows: list[dict]) -> None``
        Called once after a run finishes (success or failure).
        Use it to send notifications, write to a database, trigger CI, etc.

    * ``session_id_fn(chat_id: str) -> str``
        Returns the session ID for a chat.  Defaults to ``uuid.uuid4()``.
        Supply a deterministic function to replay conversations against a
        stateful backend with the same session every time.
    """

    def __init__(
        self,
        config: Config,
        store: EvalStore,
        fn: Callable,
        *,
        judge_fn: Callable | None = None,
        extra_metrics: dict[str, Callable] | None = None,
        on_complete: Callable | None = None,
        session_id_fn: Callable | None = None,
    ):
        self.config = config
        self.store  = store
        self.fn     = fn

        # --- callable hooks ---
        self._judge_fn      = judge_fn
        self._extra_metrics = extra_metrics or {}
        self._on_complete   = on_complete
        self._session_id_fn = session_id_fn or (lambda chat_id: str(uuid.uuid4()))

        # --- config-derived ---
        self._answer_keys   = list(config.answer_keys)
        self._s_aliases     = set(config.session_params)
        self._h_aliases     = set(config.history_params)
        self._conv_types    = {t.strip().lower() for t in config.conversational_types}
        self._history_fmt   = config.history_format
        self._record_detail = config.record_detail
        self._record_mode   = config.record_mode

        # Detect once at startup — inspection is expensive; cache the result.
        self._sig = _detect_sig(fn, self._s_aliases, self._h_aliases)
        # Cache the exact param name so _call_fn can pass it as a keyword arg.
        self._session_kwarg = _sig_kwarg(fn, self._s_aliases) if self._sig == "session_id" else "session_id"
        self._history_kwarg = _sig_kwarg(fn, self._h_aliases) if self._sig == "history" else "history"

        self.runs: dict[str, Run] = {}
        self._lock = threading.Lock()
        # Lazy-init: Judge loads LiteLLM which imports are slow; skip if judge_fn is provided.
        self._llm_judge: Judge | None = None

    # ---

    @property
    def judge(self) -> Judge:
        if self._llm_judge is None:
            self._llm_judge = Judge(self.config)
        return self._llm_judge

    def _is_conversational(self, row_type: str) -> bool:
        t = row_type.strip().lower()
        return t in self._conv_types or t.startswith("conv") or is_non_rag(t)

    def active(self) -> Run | None:
        return next((r for r in self.runs.values() if r.status == "running"), None)

    def start(
        self,
        version: str,
        df: pd.DataFrame,
        dataset_name: str,
        *,
        notes: str = "",
        group_names: list[str] | None = None,
        from_library: bool = False,
        dataset_id: str = "",
    ) -> Run:
        """Start a run in a background thread.

        ``from_library=True`` means ``df`` was resolved from test cases already in the store
        (groups and/or picked cases), so it is not imported again; ``dataset_id`` is then the
        source group's id when the run came from exactly one group.
        """
        with self._lock:
            if self.active():
                raise RunBusy("Another evaluation is already running")
            run = Run(version, len(df), dataset_name)
            run.notes = notes
            run.group_names = group_names or []
            run.from_library = from_library
            run.dataset_id = dataset_id
            self.runs[run.run_id] = run
        threading.Thread(
            target=self._execute, args=(run, df), daemon=True, name=f"eval-{version}"
        ).start()
        return run

    # ---

    def _call_fn(
        self, question: str, history: list[dict], session_id: str
    ) -> tuple[str, float, dict, str, list, dict, dict, dict]:
        """Call the developer's function; return (answer, elapsed, node_timings,
        material, sources, step_inputs, step_outputs, flags)."""
        _recording_active = self._record_mode != "off"
        if _recording_active:
            recording._activate(detail=self._record_detail)
        t0  = time.perf_counter()
        exc = None
        result = None
        try:
            fmt_history = _build_history(history, self._history_fmt)
            if self._sig == "session_id":
                # Stateful backend — passes only the session token; backend owns history.
                result = _call_sync(self.fn, question, **{self._session_kwarg: session_id})
            elif self._sig == "history":
                # Stateless backend — runner passes the full conversation history each turn.
                result = _call_sync(self.fn, question, **{self._history_kwarg: fmt_history})
            else:
                result = _call_sync(self.fn, question)
        except Exception as e:
            exc = e
        finally:
            if _recording_active:
                recording._deactivate()

        elapsed   = round(time.perf_counter() - t0, 3)
        collected = recording._collect()
        steps     = collected["steps"]
        flags     = collected["flags"]

        if exc is not None:
            raise exc

        answer = _coerce_to_str(result, self._answer_keys)
        if result is not None and not isinstance(result, str):
            logger.info(
                "fn() returned %s — extracted answer string via answer_keys. "
                "Pass answer_keys= to serve() to customise.",
                type(result).__name__,
            )

        node_timings = {s["name"]: s["elapsed"] for s in steps}
        material     = "\n\n".join(s["material"] for s in steps if s.get("material"))
        sources      = [src for s in steps for src in (s.get("sources") or [])]
        step_inputs  = {s["name"]: s.get("inputs", {}) for s in steps}
        step_outputs = {s["name"]: s.get("output",  "") for s in steps}
        return answer, elapsed, node_timings, material, sources, step_inputs, step_outputs, flags

    def _grade(
        self, question: str, expected: str, generated: str | None,
        material: str, material_applicable: bool
    ) -> dict:
        """Grade using judge_fn if provided, otherwise the LLM judge."""
        if self._judge_fn is not None:
            try:
                raw = _call_sync(self._judge_fn, question, expected, generated, material)
                if not isinstance(raw, dict):
                    raw = {"answer_marks": int(raw)}
                return {
                    "answer_marks":    int(raw.get("answer_marks", 0)),
                    "answer_comment":  str(raw.get("answer_comment", "")),
                    "material_marks":  raw.get("material_marks") if material_applicable else None,
                    "material_comment": str(raw.get("material_comment",
                        "Not applicable (no retrieval expected)." if not material_applicable else "")),
                }
            except Exception as e:
                logger.error("Custom judge_fn failed: %s", e)
                return {
                    "answer_marks": 0, "answer_comment": f"judge_fn error: {e}",
                    "material_marks": None, "material_comment": "",
                }

        grade = self.judge.grade(question, expected, generated, material, material_applicable)
        return {
            "answer_marks":    grade.answer_marks,
            "answer_comment":  grade.answer_comment,
            "material_marks":  grade.material_marks,
            "material_comment": grade.material_comment,
        }

    def _process_row(self, row, session_id: str, history: list[dict]) -> dict:
        out = {
            "chat_id":         row.chat_id,
            "turn_no":         row.turn_no,
            "type":            row.type,
            "question":        row.question,
            "expected_answer": row.expected_answer,
            "session_id":      session_id,
            "status":          "ok",
        }
        tc_id = getattr(row, "tc_id", None)
        if tc_id:
            out["tc_id"] = tc_id  # lets per-group stats find this row even after chat/turn edits
        groups = getattr(row, "groups", None)
        if groups is not None:
            out["groups"] = list(groups)  # the groups this case belonged to when it ran

        # Carry any extra columns from the row into the receipt
        for col in self.config.extra_columns:
            col_n = col.strip().lower()
            if hasattr(row, col_n):
                out[col_n] = getattr(row, col_n)

        try:
            answer, elapsed, node_timings, material, sources, step_inputs, step_outputs, flags = \
                self._call_fn(row.question, history, session_id)
            out.update(
                generated_answer=answer,
                total_time_taken=elapsed,
                node_timings=node_timings,
                material=material,
                sources=sources,
                step_inputs=step_inputs,
                step_outputs=step_outputs,
            )
            if flags:
                out["flags"] = flags

            # Source check — only if the dataset row has expected_sources
            expected_sources = str(getattr(row, "expected_sources", "") or "").strip()
            if expected_sources and expected_sources.lower() != "nan":
                mode = self.config.source_check_mode
                if mode == "llm":
                    try:
                        result = self.judge.check_sources(parse_source_groups(expected_sources), sources)
                        out.update(
                            source_match=result.source_match,
                            matched_sources=result.matched_sources,
                            missing_sources=result.missing_sources,
                            source_score=result.source_score,
                            source_comment=result.source_comment,
                        )
                    except Exception as e:
                        logger.warning("LLM source check failed, falling back to keyword: %s", e)
                        out.update(_source_check(expected_sources, sources))
                elif mode != "off":
                    out.update(_source_check(expected_sources, sources))

        except Exception as e:
            logger.error("Generation failed for chat %s turn %s: %s", row.chat_id, row.turn_no, e)
            out.update(
                status="generation_failed",
                generated_answer=None,
                material="",
                sources=[],
                node_timings={},
                step_inputs={},
                step_outputs={},
            )

        conversational = self._is_conversational(row.type)

        # Built-in lexical metrics (non-conversational only)
        if out["status"] == "ok" and not conversational:
            gen = out["generated_answer"]
            if self.config.run_keyword_recall:
                out["keyword_recall"] = lexical.keyword_recall(row.expected_answer, gen)
            if self.config.run_bm25:
                out["bm25_score"] = lexical.bm25_score(row.expected_answer, gen)
            if self.config.run_semantic_similarity:
                try:
                    out["semantic_similarity"] = lexical.semantic_similarity(
                        row.expected_answer, gen, self.config.embedding_model
                    )
                except Exception as e:
                    logger.warning("Semantic similarity failed: %s", e)

        # Extra / custom metrics
        if out["status"] == "ok" and self._extra_metrics:
            gen = out.get("generated_answer", "")
            for name, fn in self._extra_metrics.items():
                try:
                    out[name] = _call_sync(fn, row.expected_answer, gen)
                except Exception as e:
                    logger.warning("extra_metric '%s' failed: %s", name, e)
                    out[name] = None

        # Grading (LLM judge or custom judge_fn)
        try:
            grade = self._grade(
                row.question, row.expected_answer,
                out.get("generated_answer"), out.get("material", ""),
                not conversational,
            )
            out.update(
                answer_marks=grade["answer_marks"],
                answer_remarks=grade["answer_comment"],
                material_marks=grade["material_marks"],
                material_remarks=grade["material_comment"],
            )
        except Exception as e:
            logger.error("Grading failed: %s", e)
            if out["status"] == "ok":
                out["status"] = "grading_failed"
            out.update(answer_remarks=str(e)[:400], material_remarks="Grading failed")

        return out

    def _execute(self, run: Run, df: pd.DataFrame) -> None:
        rows: list[dict] = []

        # Import this dataset's questions into the test_cases table for traceability.
        # Skip for library runs (the cases already live in the store) and for multi-group runs
        # (import_dataset would create a spurious combined group).
        fingerprint = df.attrs.get("fingerprint", "")
        dataset_id = run.dataset_id
        if not run.from_library and len(run.group_names) <= 1:
            try:
                dataset_id = self.store.import_dataset(run.dataset_name, df, fingerprint)
            except Exception as e:
                logger.warning("Could not import dataset into test_cases table: %s", e)

        try:
            run.emit("started")
            sessions:  dict[str, str]        = {}
            histories: dict[str, list[dict]] = {}

            for row in df.itertuples(index=False):
                # Check if a stop was requested before processing the next row.
                if run.stop_requested:
                    run.status = "stopped"
                    run.current_question = ""
                    run.emit("stopped")
                    _partial_write(self, run, rows, fingerprint, dataset_id)
                    return

                run.current_question = row.question[:120]
                chat_id = row.chat_id
                if chat_id not in sessions:
                    sessions[chat_id]  = self._session_id_fn(chat_id)
                    histories[chat_id] = []

                result = self._process_row(row, sessions[chat_id], histories[chat_id])
                if result.get("generated_answer"):
                    histories[chat_id].append({
                        "question": row.question,
                        "answer":   result["generated_answer"],
                    })
                rows.append(result)
                run.done += 1
                run.emit("progress", row=_light(result))

            run.current_question = "Summarising run…"

            summary = build_summary(
                run.version, rows, run.started, run.dataset_name,
                judge_model=self.config.judge_model,
                question_fingerprint=fingerprint,
                dataset_id=dataset_id,
            )
            summary["run_id"] = run.version  # stable identifier used by dashboard actions
            summary["notes"] = run.notes
            summary["group_names"] = run.group_names
            summary["group_stats"] = build_group_stats(self.store, run.group_names, rows)
            insights = self.judge.summarize_run(stats_for_llm(summary, rows))
            if insights:
                insights = finish_insights(insights, summary, rows)      # every watch-out gets its suggestion
                summary["insights"] = insights
                # plain-text version for anything that only reads `comment` (xlsx, on_complete hooks)
                summary["comment"] = "\n".join(
                    f"• {i['watch_out']} → {i['suggestion']}" if i["watch_out"] and i["suggestion"] else f"• {i['watch_out'] or i['suggestion']}"
                    for i in insights["items"])
            else:
                summary["comment"] = "Summary could not be generated for this run."

            self.store.write(run.version, summary, rows)
            run.summary, run.status, run.current_question = summary, "completed", ""
            run.emit("done", summary=summary)

            # on_complete callback
            if self._on_complete is not None:
                try:
                    _call_sync(self._on_complete, summary, rows)
                except Exception as e:
                    logger.error("on_complete callback failed: %s", e)

        except Exception as e:
            logger.exception("Run %s failed", run.version)
            run.status, run.error = "failed", str(e)
            run.emit("error")

            if self._on_complete is not None:
                try:
                    _call_sync(self._on_complete, None, rows)
                except Exception:
                    pass


def _partial_write(manager: RunManager, run: Run, rows: list[dict], fingerprint: str, dataset_id: str) -> None:
    """Write partial results when a run is stopped early."""
    try:
        summary = build_summary(
            run.version, rows, run.started, run.dataset_name,
            judge_model=manager.config.judge_model,
            question_fingerprint=fingerprint,
            dataset_id=dataset_id,
        )
        summary["comment"] = f"Run stopped after {run.done}/{run.total} rows."
        summary["stopped"] = True  # incomplete: never recommended or compared as a finished run
        summary["run_id"] = run.version
        summary["notes"] = run.notes
        summary["group_names"] = run.group_names
        summary["group_stats"] = build_group_stats(manager.store, run.group_names, rows)
        manager.store.write(run.version, summary, rows)
        run.summary = summary
    except Exception as e:
        logger.error("Could not write partial results for stopped run: %s", e)


def _light(r: dict) -> dict:
    return {
        k: r.get(k)
        for k in ("chat_id", "turn_no", "type", "question", "answer_marks", "material_marks", "status")
    }
