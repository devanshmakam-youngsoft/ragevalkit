"""RunManager: runs test cases through your function on a background thread and saves what it finds."""
import logging
import threading
import time
import uuid
from typing import Callable

import pandas as pd

from ragevalkit import metrics, recording
from ragevalkit.config import Config
from ragevalkit.evaluation.exceptions import RunBusy
from ragevalkit.evaluation.function_adapter import (
    answer_text_of,
    call_sync,
    detect_call_style,
    format_history,
    parameter_name_for,
)
from ragevalkit.evaluation.material import select_material
from ragevalkit.evaluation.run import Run, light_row
from ragevalkit.evaluation.source_check import check_sources_by_keyword, parse_source_groups
from ragevalkit.judging.exceptions import JudgeError
from ragevalkit.judging.fallback_insights import finish_insights
from ragevalkit.judging.judge import Judge
from ragevalkit.judging.run_summary_input import stats_for_llm
from ragevalkit.logs import EventLog
from ragevalkit.run_summary.builder import build_summary
from ragevalkit.run_summary.group_stats import build_group_stats
from ragevalkit.storage.store import EvalStore
from ragevalkit.test_cases.case_types import is_non_rag

logger = logging.getLogger(__name__)


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
        recording.configure(max_step_value_chars=config.step_value_chars, max_material_chars=config.material_chars)

        # Detect once at startup — inspection is expensive; cache the result.
        self._sig = detect_call_style(fn, self._s_aliases, self._h_aliases)
        # Cache the exact param name so _call_fn can pass it as a keyword arg.
        self._session_kwarg = parameter_name_for(fn, self._s_aliases) if self._sig == "session_id" else "session_id"
        self._history_kwarg = parameter_name_for(fn, self._h_aliases) if self._sig == "history" else "history"

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
            run.log = EventLog(self.config, "runs", version)
            run.notes = notes
            run.group_names = group_names or []
            run.from_library = from_library
            run.dataset_id = dataset_id
            self.runs[run.run_id] = run
        threading.Thread(
            target=self._execute_and_close_log, args=(run, df), daemon=True, name=f"eval-{version}"
        ).start()
        return run

    def _execute_and_close_log(self, run: Run, df: pd.DataFrame) -> None:
        try:
            self._execute(run, df)
        finally:
            run.log.info("Run %s %s after %d of %d questions, %d problems", run.version, run.status, run.done, run.total, run.log.issue_total)
            run.log.close()

    # ---

    def _call_fn(
        self, question: str, history: list[dict], session_id: str
    ) -> tuple[str, float, dict, str, list, dict, dict, dict]:
        """Call the developer's function; return (answer, elapsed, node_timings,
        material, sources, step_inputs, step_outputs, flags)."""
        _recording_active = self._record_mode != "off"
        if _recording_active:
            recording.begin_question(detail=self._record_detail)
        t0  = time.perf_counter()
        exc = None
        result = None
        try:
            fmt_history = format_history(history, self._history_fmt)
            if self._sig == "session_id":
                # Stateful backend — passes only the session token; backend owns history.
                result = call_sync(self.fn, question, **{self._session_kwarg: session_id})
            elif self._sig == "history":
                # Stateless backend — runner passes the full conversation history each turn.
                result = call_sync(self.fn, question, **{self._history_kwarg: fmt_history})
            else:
                result = call_sync(self.fn, question)
        except Exception as e:
            exc = e
        finally:
            if _recording_active:
                recording.end_question()

        elapsed   = round(time.perf_counter() - t0, 3)
        collected = recording.collect_question()
        steps     = collected["steps"]
        flags     = collected["flags"]

        if exc is not None:
            raise exc

        answer = answer_text_of(result, self._answer_keys)
        if result is not None and not isinstance(result, str):
            logger.info(
                "fn() returned %s — extracted answer string via answer_keys. "
                "Pass answer_keys= to serve() to customise.",
                type(result).__name__,
            )

        # A step that ran several times (an agent calling a tool in a loop, or the same search in parallel threads)
        # has its time added up: this is the time spent in that step.
        node_timings: dict[str, float] = {}
        for s in steps:
            node_timings[s["name"]] = round(node_timings.get(s["name"], 0.0) + s["elapsed"], 3)
        material = select_material(steps)
        sources      = [src for s in steps for src in (s.get("sources") or [])]
        step_inputs  = {s["name"]: s.get("inputs", {}) for s in steps}
        step_outputs = {s["name"]: s.get("output",  "") for s in steps}
        return answer, elapsed, node_timings, material, sources, step_inputs, step_outputs, flags

    def _grade(
        self, question: str, expected: str, generated: str | None,
        material: str, material_applicable: bool, run: Run, where: str,
    ) -> dict:
        """Grade using judge_fn if provided, otherwise the LLM judge."""
        if self._judge_fn is not None:
            try:
                raw = call_sync(self._judge_fn, question, expected, generated, material)
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
                issue = run.log.issue("custom_judge", e, where)
                return {
                    "answer_marks": 0, "answer_comment": issue.message,
                    "material_marks": None, "material_comment": "",
                }

        grade = self.judge.grade(question, expected, generated, material, material_applicable)
        return {
            "answer_marks":    grade.answer_marks,
            "answer_comment":  grade.answer_comment,
            "material_marks":  grade.material_marks,
            "material_comment": grade.material_comment,
        }

    def _process_row(self, row, session_id: str, history: list[dict], run: Run) -> dict:
        where = f"Question {run.done + 1} of {run.total} (chat {row.chat_id}, turn {row.turn_no})"
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
                        run.log.issue("source_check", e, where, severity="warning")
                        out.update(check_sources_by_keyword(expected_sources, sources))
                elif mode != "off":
                    out.update(check_sources_by_keyword(expected_sources, sources))

        except Exception as e:
            issue = run.log.issue("answer", e, where)
            out.update(
                status="generation_failed",
                error_message=issue.message,
                error_detail=issue.technical,
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
                out["keyword_recall"] = metrics.keyword_recall(row.expected_answer, gen)
            if self.config.run_bm25:
                out["bm25_score"] = metrics.bm25_score(row.expected_answer, gen)
            if self.config.run_semantic_similarity:
                try:
                    out["semantic_similarity"] = metrics.semantic_similarity(
                        row.expected_answer, gen, self.config.embedding_model
                    )
                except Exception as e:
                    run.log.issue("metric", e, f"{where}, semantic similarity", severity="warning")

        # Extra / custom metrics
        if out["status"] == "ok" and self._extra_metrics:
            gen = out.get("generated_answer", "")
            for name, fn in self._extra_metrics.items():
                try:
                    out[name] = call_sync(fn, row.expected_answer, gen)
                except Exception as e:
                    run.log.issue("metric", e, f"{where}, {name}", severity="warning")
                    out[name] = None

        # Grading (LLM judge or custom judge_fn)
        try:
            grade = self._grade(
                row.question, row.expected_answer,
                out.get("generated_answer"), out.get("material", ""),
                not conversational, run, where,
            )
            out.update(
                answer_marks=grade["answer_marks"],
                answer_remarks=grade["answer_comment"],
                material_marks=grade["material_marks"],
                material_remarks=grade["material_comment"],
            )
        except Exception as e:
            issue = run.log.issue("grading", e, where)
            if out["status"] == "ok":
                out["status"] = "grading_failed"
            out.update(answer_remarks=issue.message, material_remarks="Grading failed", error_message=issue.message, error_detail=issue.technical)

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
                run.log.issue("save", e, "importing the questions into the library", severity="warning")

        try:
            run.log.info(
                "Run %s started: %d questions from %s, judge model %s",
                run.version, run.total, run.dataset_name, "custom judge_fn" if self._judge_fn else self.config.judge_model,
            )
            run.emit("started")
            sessions:  dict[str, str]        = {}
            histories: dict[str, list[dict]] = {}

            for row in df.itertuples(index=False):
                # Check if a stop was requested before processing the next row.
                if run.stop_requested:
                    run.status = "stopped"
                    run.current_question = ""
                    run.log.info("Stop requested: stopped after %d of %d questions", run.done, run.total)
                    run.emit("stopped")
                    write_partial_results(self, run, rows, fingerprint, dataset_id)
                    return

                run.current_question = row.question[:120]
                chat_id = row.chat_id
                if chat_id not in sessions:
                    sessions[chat_id]  = self._session_id_fn(chat_id)
                    histories[chat_id] = []

                result = self._process_row(row, sessions[chat_id], histories[chat_id], run)
                if result.get("generated_answer"):
                    histories[chat_id].append({
                        "question": row.question,
                        "answer":   result["generated_answer"],
                    })
                rows.append(result)
                run.done += 1
                run.log.info(
                    "Question %d of %d | chat %s turn %s | %s | answer %s, material %s | %ss",
                    run.done, run.total, row.chat_id, row.turn_no, result["status"],
                    result.get("answer_marks"), result.get("material_marks"), result.get("total_time_taken", "-"),
                )
                run.emit("progress", row=light_row(result))

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
                run.log.issue("summary", JudgeError("The judge returned no usable summary"), "writing the findings", severity="warning")

            attach_run_log(summary, run)
            self.store.write(run.version, summary, rows)
            run.summary, run.status, run.current_question = summary, "completed", ""
            run.emit("done", summary=summary)

            # on_complete callback
            if self._on_complete is not None:
                try:
                    call_sync(self._on_complete, summary, rows)
                except Exception as e:
                    run.log.issue("callback", e, "on_complete", severity="warning")

        except Exception as e:
            issue = run.log.issue("run", e, f"after {run.done} of {run.total} questions")
            run.status, run.error, run.error_detail = "failed", issue.message, issue.technical
            run.emit("error")

            if self._on_complete is not None:
                try:
                    call_sync(self._on_complete, None, rows)
                except Exception:
                    pass


def attach_run_log(summary: dict, run: Run) -> None:
    """Keep the run's problems and the name of its log file with the saved results."""
    summary["issues"] = run.log.issue_dicts()
    summary["issue_total"] = run.log.issue_total
    summary["log_file"] = run.log.file_name


def write_partial_results(manager: RunManager, run: Run, rows: list[dict], fingerprint: str, dataset_id: str) -> None:
    """Write partial results when a run is stopped early."""
    try:
        summary = build_summary(
            run.version, rows, run.started, run.dataset_name,
            judge_model=manager.config.judge_model,
            question_fingerprint=fingerprint,
            dataset_id=dataset_id,
        )
        summary["comment"] = f"Run stopped after {run.done}/{run.total} rows."
        attach_run_log(summary, run)
        summary["stopped"] = True  # incomplete: never recommended or compared as a finished run
        summary["run_id"] = run.version
        summary["notes"] = run.notes
        summary["group_names"] = run.group_names
        summary["group_stats"] = build_group_stats(manager.store, run.group_names, rows)
        manager.store.write(run.version, summary, rows)
        run.summary = summary
    except Exception as e:
        logger.error("Could not write partial results for stopped run: %s", e)
