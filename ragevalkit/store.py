"""
TinyDB-backed persistence for ragevalkit.

FOUR-TABLE DESIGN
-----------------
  runs        — one document per version (summary stats + AI commentary)
  receipts    — one document per question per version (the raw grade + metrics)
  datasets    — one document per unique dataset file (fingerprint + metadata)
  test_cases  — one document per version of each test case (stable tc_id + version counter)

WHY two eval tables (runs + receipts)?
  The dashboard's list view only needs the `runs` table (fast, small).
  Loading all receipts for every version on every page load would be slow.
  The detail view / download hits `receipts` only when the user asks.

WHY a test_cases table?
  Gives every question a stable tc_id that survives across dataset re-uploads.
  Each edit creates a new version record (the old one stays for history).
  Eval receipts reference tc_id so you can join eval results with the test case
  that was active at the time — and see how questions evolved over runs.

WHY TinyDB (not SQLite)?
  Zero setup — a single JSON file the developer can open in any text editor,
  commit to git, or copy between machines. No schema migrations needed.
  The lock is a plain threading.Lock because TinyDB is not thread-safe by
  itself and the runner writes from a background thread while FastAPI reads.
"""
import hashlib
import io
import json
import logging
import math
import re
import statistics
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from tinydb import Query, TinyDB
from tinydb.operations import delete

from ragevalkit.dataset import compute_fingerprint
from ragevalkit.exceptions import ConflictError, GroupNotFound, VersionNotFound

logger = logging.getLogger(__name__)

VERSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,20}$")


def _clean_es(val) -> str:
    """Convert a potential NaN/None expected_sources value to clean empty string."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s
COLUMNS_BEFORE_NODES = [
    "chat_id", "session_id", "turn_no", "type", "question", "expected_answer",
    "generated_answer", "material", "sources", "status", "total_time_taken",
    # node-level detail (populated when @ragevalkit.step() is used as a decorator)
    "step_inputs", "step_outputs",
]
COLUMNS_AFTER_NODES = [
    "answer_marks", "answer_remarks", "material_marks", "material_remarks",
    "keyword_recall", "bm25_score", "semantic_similarity",
]
# Optional receipt columns — included in Excel when at least one row has a value.
OPTIONAL_RECEIPT_COLUMNS = [
    "source_match", "matched_sources", "missing_sources", "flags",
]
METRIC_AVGS = {"answer_marks", "material_marks", "total_time", "keyword_recall", "bm25_score", "semantic_similarity"}
EXCEL_CELL_LIMIT = 32000



def valid_version(version: str) -> bool:
    return bool(VERSION_RE.match(version))


def node_order(rows: list[dict]) -> list[str]:
    order: list[str] = []
    for r in rows:
        seq = list((r.get("node_timings") or {}).keys())
        for i, name in enumerate(seq):
            if name in order:
                continue
            if i == 0:
                order.insert(0, name)
            else:
                order.insert(order.index(seq[i - 1]) + 1, name)
    return order


def summary_nodes(summary: dict) -> list[dict]:
    return [
        {"name": k[4:], "avg": v}
        for k, v in summary.items()
        if k.startswith("avg_") and k[4:] not in METRIC_AVGS and v is not None and not _isnan(v)
    ]


def _isnan(v) -> bool:
    try:
        return math.isnan(v)
    except (TypeError, ValueError):
        return False


def _mean(values: list, nd: int = 2) -> float | None:
    vals = [v for v in values if v is not None and not _isnan(v)]
    return round(statistics.fmean(vals), nd) if vals else None


def _col(rows: list[dict], key: str) -> list:
    return [r.get(key) for r in rows]


def build_scores(rows: list[dict]) -> dict:
    """The detailed scores of one run, saved on its summary so every later comparison reads them
    instead of recomputing from receipts: overall averages, score tiers, per-question-type
    averages, response-time spread and source-check results."""
    graded = [r for r in rows if r.get("answer_marks") is not None]
    marks = [r["answer_marks"] for r in graded]
    times = sorted(t for t in _col(rows, "total_time_taken") if t is not None and not _isnan(t))
    by_type: dict[str, list[dict]] = {}
    for r in graded:
        by_type.setdefault(str(r.get("type") or "unknown"), []).append(r)
    checked = [r for r in rows if r.get("source_match") is not None]
    return {
        "graded_rows": len(graded),
        "answer_marks": _mean(marks),
        "material_marks": _mean(_col(rows, "material_marks")),
        "lexical": {
            "keyword_recall": _mean(_col(rows, "keyword_recall"), 3),
            "bm25_score": _mean(_col(rows, "bm25_score"), 3),
            "semantic_similarity": _mean(_col(rows, "semantic_similarity"), 3),
        },
        "tiers": {
            "high": sum(1 for m in marks if m >= 8),
            "mid": sum(1 for m in marks if 5 <= m < 8),
            "low": sum(1 for m in marks if m < 5),
        },
        "by_type": {
            t: {
                "rows": len(rs),
                "answer_marks": _mean(_col(rs, "answer_marks")),
                "material_marks": _mean(_col(rs, "material_marks")),
            }
            for t, rs in by_type.items()
        },
        "time": {
            "avg": _mean(times, 3),
            "p95": round(times[max(0, math.ceil(0.95 * len(times)) - 1)], 3) if times else None,
        },
        "sources": {"checked": len(checked), "matched": sum(1 for r in checked if r["source_match"])},
    }


def case_key(chat_id, turn_no, question, expected_answer) -> str:
    """Identifies one test case *as it was asked*: the same chat, turn, question and expected answer.

    Versions are compared on cases with the same key, so a case whose question or expected answer was
    edited between two runs is not mistaken for the same test."""
    raw = f"{chat_id}\x1f{turn_no}\x1f{str(question).strip()}\x1f{str(expected_answer).strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def build_case_scores(rows: list[dict]) -> list[dict]:
    """The compact per-case scores of one run, saved on its summary so any two versions can later be
    compared on the cases they share: {k: case key, a: answer marks, m: material marks, t: seconds,
    ok: answered and graded, g: the groups the case belonged to when it ran}."""
    out = []
    for r in rows:
        t = r.get("total_time_taken")
        out.append({
            "k": case_key(r.get("chat_id", ""), r.get("turn_no", 1), r.get("question", ""), r.get("expected_answer", "")),
            "a": r.get("answer_marks"),
            "m": r.get("material_marks"),
            "t": None if t is None or _isnan(t) else t,
            "ok": r.get("status") == "ok",
            "g": list(r.get("groups") or []),
        })
    return out


def build_summary(
    version: str,
    rows: list[dict],
    started: datetime,
    dataset_name: str,
    *,
    judge_model: str = "",
    question_fingerprint: str = "",
    dataset_id: str = "",
) -> dict:
    finished = datetime.now(timezone.utc)
    summary = {
        "version": version,
        "date": started.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 1),
        "dataset": dataset_name,
        "dataset_id": dataset_id,
        "total_rows": len(rows),
        "failed_rows": sum(1 for r in rows if r["status"] != "ok"),
        "avg_answer_marks": _mean(_col(rows, "answer_marks")),
        "avg_material_marks": _mean(_col(rows, "material_marks")),
        "avg_total_time": _mean(_col(rows, "total_time_taken"), 3),
        "avg_keyword_recall": _mean(_col(rows, "keyword_recall"), 3),
        "avg_bm25_score": _mean(_col(rows, "bm25_score"), 3),
        "avg_semantic_similarity": _mean(_col(rows, "semantic_similarity"), 3),
        # Traceability fields — enables "did the questions change?" dashboard warnings.
        "judge_model": judge_model,
        "question_fingerprint": question_fingerprint,
        "comment": "",
        "scores": build_scores(rows),
        "case_scores": build_case_scores(rows),
    }
    for n in node_order(rows):
        summary[f"avg_{n}"] = _mean([(r.get("node_timings") or {}).get(n) for r in rows], 3)
    return summary


def build_group_stats(store: "EvalStore", group_names: list[str], rows: list[dict]) -> dict:
    """Per-group score averages for the groups a run covered.

    A test case can sit in several groups; it is then counted once in the run's overall scores and
    once in *each* of its groups, so every group's numbers describe exactly its own cases. Group
    membership comes from the labels each row carried when it ran (falling back to the library's
    current labels for rows saved before that was recorded)."""
    if not group_names:
        return {}
    if not all("groups" in r for r in rows):
        with store._lock:
            ids = {g["group_id"]: g["name"] for g in store.groups.all()}
            members = list(store.group_members.all())
        names_of: dict[str, set[str]] = {}
        for m in members:
            if m["group_id"] in ids:
                names_of.setdefault(m["tc_id"], set()).add(ids[m["group_id"]])
        rows = [
            {**r, "groups": r.get("groups") or sorted(names_of.get(
                r.get("tc_id") or _tc_id(str(r.get("chat_id", "")), int(r.get("turn_no") or 1), str(r.get("question", ""))),
                set()))}
            for r in rows
        ]
    stats: dict = {}
    for gname in group_names:
        group_rows = [r for r in rows if gname in (r.get("groups") or [])]
        if group_rows:
            stats[gname] = {
                "avg_answer_marks": _mean(_col(group_rows, "answer_marks")),
                "avg_material_marks": _mean(_col(group_rows, "material_marks")),
                "avg_total_time": _mean(_col(group_rows, "total_time_taken"), 3),
                "avg_keyword_recall": _mean(_col(group_rows, "keyword_recall"), 3),
                "avg_bm25_score": _mean(_col(group_rows, "bm25_score"), 3),
                "avg_semantic_similarity": _mean(_col(group_rows, "semantic_similarity"), 3),
                "total_rows": len(group_rows),
                "failed_rows": sum(1 for r in group_rows if r.get("status") != "ok"),
            }
    return stats


def stats_for_llm(summary: dict, rows: list[dict]) -> str:
    by_type: dict[str, list[float]] = {}
    for r in rows:
        if r.get("answer_marks") is not None:
            by_type.setdefault(r["type"], []).append(r["answer_marks"])
    type_line = ", ".join(f"{t}: {statistics.fmean(v):.1f} over {len(v)} rows" for t, v in by_type.items())
    worst = sorted((r for r in rows if r.get("answer_marks") is not None), key=lambda r: r["answer_marks"])[:3]
    worst_lines = "\n".join(
        f"- [{r['answer_marks']}/10] {r['question'][:100]} :: {str(r.get('answer_remarks'))[:160]}"
        for r in worst
    )
    nodes = ", ".join(f"{n['name']}={n['avg']}s" for n in summary_nodes(summary))
    group_line = ", ".join(
        f"{g}: answer {st['avg_answer_marks']}, context {st['avg_material_marks']} over {st['total_rows']} rows"
        for g, st in (summary.get("group_stats") or {}).items()
    ) or "n/a"
    sources = (summary.get("scores") or {}).get("sources") or {}
    source_line = (
        f"{sources['matched']} of {sources['checked']} rows retrieved all expected sources"
        if sources.get("checked") else "no source checks"
    )
    tiers = (summary.get("scores") or {}).get("tiers") or {}
    return (
        f"Score tiers (answer): {tiers.get('high', 0)} high (8+), {tiers.get('mid', 0)} middling (5-7), {tiers.get('low', 0)} low (<5)\n"
        f"By group: {group_line}\nSource checks: {source_line}\n"
        f"Rows: {summary['total_rows']} (failed: {summary['failed_rows']})\n"
        f"Avg answer marks: {summary['avg_answer_marks']}/10, avg material marks: {summary['avg_material_marks']}/10\n"
        f"Avg keyword recall: {summary['avg_keyword_recall']}, semantic similarity: {summary['avg_semantic_similarity']}\n"
        f"Avg end-to-end time: {summary['avg_total_time']}s; avg node timings: {nodes}\n"
        f"Answer marks by type: {type_line}\nLowest scoring rows:\n{worst_lines}"
    )


def _cell(v):
    if isinstance(v, (list, dict)):
        v = json.dumps(v, ensure_ascii=False)
    if isinstance(v, str):
        # Collapse newlines so Excel doesn't expand row height
        v = v.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        if len(v) > EXCEL_CELL_LIMIT:
            v = v[:EXCEL_CELL_LIMIT]
    return v


# ---------------------------------------------------------------------------
# Test case helpers
# ---------------------------------------------------------------------------

def _tc_id(chat_id: str, turn_no: int, question: str) -> str:
    """Stable test case ID — keyed by content so the same question always gets the same ID."""
    key = f"{chat_id}|{turn_no}|{question.strip()}"
    return "tc_" + hashlib.sha256(key.encode()).hexdigest()[:12]


def _natural(text) -> list:
    """Sort key that orders 'c2' before 'c10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(text))]


def _case_order(tc: dict):
    return (_natural(tc.get("chat_id", "")), tc.get("turn_no", 0))


def _latest_versions(records: list[dict]) -> dict[str, dict]:
    """Collapse versioned test-case records to the newest one per tc_id."""
    by_id: dict[str, dict] = {}
    for rec in records:
        cur = by_id.get(rec["tc_id"])
        if cur is None or rec["version"] > cur["version"]:
            by_id[rec["tc_id"]] = rec
    return by_id


@dataclass
class RunSelection:
    """The test cases a run would execute, as resolved by EvalStore.resolve_selection()."""
    df: "pd.DataFrame"
    selected: int          # distinct cases the caller asked for (via groups and/or ids)
    context: int           # earlier turns added so multi-turn chats keep their history
    missing: int           # requested tc_ids that do not exist
    group_names: list[str] = field(default_factory=list)
    collisions: list[dict] = field(default_factory=list)  # distinct cases sharing a chat + turn

    @property
    def total(self) -> int:
        return len(self.df)


def _cases_to_df(cases: list[dict], group_names_of: dict[str, list[str]] | None = None) -> "pd.DataFrame":
    """Test cases as the DataFrame the runner consumes. ``tc_id`` and the names of the groups each case
    belonged to *at run time* ride along into every receipt, so later group scores never depend on
    what the groups look like then."""
    if not cases:
        return pd.DataFrame()
    rows = []
    for tc in cases:
        row: dict = {
            "chat_id": str(tc["chat_id"]),
            "turn_no": int(tc["turn_no"]),
            "type": tc.get("type", ""),
            "question": tc["question"],
            "expected_answer": tc["expected_answer"],
            "tc_id": tc["tc_id"],
            "groups": tuple((group_names_of or {}).get(tc["tc_id"], ())),
        }
        es = _clean_es(tc.get("expected_sources", ""))
        if es:
            row["expected_sources"] = es
        rows.append(row)
    df = pd.DataFrame(rows)
    df.attrs["fingerprint"] = compute_fingerprint(df)
    return df


def _group_id() -> str:
    import uuid
    return "grp_" + uuid.uuid4().hex[:8]


def _ds_id(fingerprint: str) -> str:
    return "ds_" + fingerprint[:8]


# ---------------------------------------------------------------------------
# EvalStore
# ---------------------------------------------------------------------------

class EvalStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = TinyDB(str(self.path))
        self.runs = self.db.table("runs")
        self.receipts = self.db.table("receipts")
        self.datasets = self.db.table("datasets")  # kept for backward compat
        self.test_cases = self.db.table("test_cases")
        self.groups = self.db.table("groups")
        self.group_members = self.db.table("group_members")
        self.batches = self.db.table("gen_batches")  # generated test cases waiting for review
        self._lock = threading.Lock()
        self._drop_legacy_deleted()

    # ------------------------------------------------------------------
    # Eval runs
    # ------------------------------------------------------------------

    def exists(self, version: str) -> bool:
        with self._lock:
            return bool(self.runs.search(Query().version == version))

    def write(self, version: str, summary: dict, rows: list[dict]) -> None:
        with self._lock:
            Q = Query()
            self.runs.upsert(summary, Q.version == version)
            self.receipts.remove(Q.version == version)
            self.receipts.insert_multiple([{**r, "version": version} for r in rows])

    @staticmethod
    def _plain(summary: dict) -> dict:
        """A summary as the dashboard lists it: without the bulky per-case scores."""
        entry = dict(summary)
        entry.pop("case_scores", None)
        return entry

    def list_versions_for_comparison(self) -> list[dict]:
        """Run summaries *with* per-case scores, for comparing versions. Runs saved before per-case
        scores existed are filled in from their saved results once, then kept."""
        with self._lock:
            missing = [r["version"] for r in self.runs.all() if "case_scores" not in r]
        for version in missing:
            with self._lock:
                rows = [dict(r) for r in self.receipts.search(Query().version == version)]
            if not rows:
                continue  # nothing saved to score from: such a run is compared on its totals
            self._label_old_rows(rows)
            scores = build_case_scores(rows)
            with self._lock:
                self.runs.update({"case_scores": scores}, Query().version == version)
        with self._lock:
            summaries = [dict(r) for r in self.runs.all()]
        out = []
        for entry in summaries:
            entry["nodes"] = summary_nodes(entry)
            out.append(entry)
        return sorted(out, key=lambda s: str(s.get("date", "")))

    def list_versions(self) -> list[dict]:
        with self._lock:
            summaries = self.runs.all()
        out = []
        for s in summaries:
            entry = self._plain(s)
            entry["nodes"] = summary_nodes(entry)
            out.append(entry)
        return sorted(out, key=lambda s: str(s.get("date", "")))

    def list_runs(self, include_archived: bool = False) -> list[dict]:
        """Return run summaries from the store, excluding archived runs by default."""
        with self._lock:
            summaries = self.runs.all()
        out = []
        for s in summaries:
            entry = self._plain(s)
            if not include_archived and entry.get("archived"):
                continue
            entry["nodes"] = summary_nodes(entry)
            out.append(entry)
        return sorted(out, key=lambda s: str(s.get("date", "")))

    def delete_run(self, run_id: str) -> bool:
        """Delete a run and all its receipts from the store. run_id is the version string."""
        with self._lock:
            Q = Query()
            removed = self.runs.remove(Q.version == run_id)
            self.receipts.remove(Q.version == run_id)
        return bool(removed)

    def archive_run(self, run_id: str) -> bool:
        """Mark a run as archived. run_id is the version string."""
        with self._lock:
            Q = Query()
            updated = self.runs.update({"archived": True}, Q.version == run_id)
        return bool(updated)

    def unarchive_run(self, run_id: str) -> bool:
        """Clear the archived flag on a run. run_id is the version string."""
        with self._lock:
            Q = Query()
            updated = self.runs.update({"archived": False}, Q.version == run_id)
        return bool(updated)

    def get(self, version: str) -> dict:
        with self._lock:
            hits = self.runs.search(Query().version == version)
            if not hits:
                raise VersionNotFound(version)
            summary = self._plain(hits[0])
            rows = [dict(r) for r in self.receipts.search(Query().version == version)]
        summary["nodes"] = summary_nodes(summary)
        for row in rows:
            row.pop("version", None)
        self._label_old_rows(rows)
        return {"summary": summary, "rows": rows}

    def _label_old_rows(self, rows: list[dict]) -> None:
        """Rows saved before run-time group labels existed get the library's current labels, so they
        can still be filtered by group (approximate: membership may have changed since)."""
        if all("groups" in r for r in rows):
            return
        with self._lock:
            ids = {g["group_id"]: g["name"] for g in self.groups.all() if not g.get("deleted_at")}
            members = list(self.group_members.all())
        names_of: dict[str, list[str]] = {}
        for m in members:
            if m["group_id"] in ids:
                names_of.setdefault(m["tc_id"], []).append(ids[m["group_id"]])
        for r in rows:
            if "groups" not in r:
                tc = r.get("tc_id") or _tc_id(str(r.get("chat_id", "")), int(r.get("turn_no") or 1), str(r.get("question", "")))
                r["groups"] = sorted(names_of.get(tc, []))

    def export_xlsx(self, version: str) -> bytes:
        data = self.get(version)
        rows = data["rows"]
        nodes = node_order(rows)

        # ── human-readable column order for the Results sheet ──────────────
        # Primary identification
        ID_COLS   = ["chat_id", "turn_no", "type", "groups", "status"]
        # The question/answer triplet — the heart of every row
        QA_COLS   = ["question", "expected_answer", "generated_answer"]
        # Judge scores + comments right after the answers
        JUDGE_COLS = ["answer_marks", "answer_remarks", "material_marks", "material_remarks"]
        # Retrieved context and sources
        CTX_COLS  = ["retrieved_context", "sources"]
        # Lexical / embedding metrics
        METRIC_COLS = ["keyword_recall", "bm25_score", "semantic_similarity"]
        # Timing
        TIME_COLS = ["total_time_taken", *[f"node_{n}" for n in nodes]]
        # Optional: source verification
        OPT_PRESENT = [c for c in OPTIONAL_RECEIPT_COLUMNS if any(r.get(c) is not None for r in rows)]
        # Anything else logged that isn't already covered
        _covered = set(ID_COLS + QA_COLS + JUDGE_COLS + ["material"] + CTX_COLS +
                       METRIC_COLS + ["total_time_taken"] + OPT_PRESENT +
                       ["session_id", "tc_id", "step_inputs", "step_outputs", "node_timings", "version"])
        extra: list[str] = []
        for r in rows:
            for k in r:
                if k not in _covered and k not in extra:
                    extra.append(k)

        columns = [*ID_COLS, *QA_COLS, *JUDGE_COLS, *CTX_COLS, *METRIC_COLS,
                   *TIME_COLS, *OPT_PRESENT, *extra]

        records = []
        for r in rows:
            rec: dict = {}
            for c in ID_COLS:
                rec[c] = ", ".join(r.get("groups") or []) if c == "groups" else _cell(r.get(c))
            for c in QA_COLS:
                rec[c] = _cell(r.get(c))
            for c in JUDGE_COLS:
                rec[c] = _cell(r.get(c))
            # "material" stored internally → rename to "retrieved_context" for clarity
            rec["retrieved_context"] = _cell(r.get("material"))
            rec["sources"] = _cell(r.get("sources"))
            for c in METRIC_COLS:
                rec[c] = _cell(r.get(c))
            rec["total_time_taken"] = _cell(r.get("total_time_taken"))
            nt = r.get("node_timings") or {}
            for n in nodes:
                rec[f"node_{n}"] = nt.get(n)
            for c in OPT_PRESENT:
                rec[c] = _cell(r.get(c))
            for c in extra:
                rec[c] = _cell(r.get(c))
            records.append(rec)

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            # Sheet 1 — Summary scores
            s = data["summary"]
            summary_display = {
                "version": s.get("version"), "date": s.get("date"),
                "dataset": s.get("dataset"), "notes": s.get("notes", ""),
                "groups": ", ".join(s.get("group_names") or []),
                "total_questions": s.get("total_rows"), "failed": s.get("failed_rows"),
                "avg_answer_marks": s.get("avg_answer_marks"),
                "avg_material_marks": s.get("avg_material_marks"),
                "avg_total_time_s": s.get("avg_total_time"),
                "avg_keyword_recall": s.get("avg_keyword_recall"),
                "avg_bm25_score": s.get("avg_bm25_score"),
                "avg_semantic_similarity": s.get("avg_semantic_similarity"),
                "judge_model": s.get("judge_model"),
                "duration_seconds": s.get("duration_seconds"),
                "comment": s.get("comment"),
            }
            pd.DataFrame([summary_display]).to_excel(xw, sheet_name="Summary", index=False)

            # Sheet 2 — Full results
            df_results = pd.DataFrame(records, columns=columns)
            df_results.to_excel(xw, sheet_name="Results", index=False)

            # Formatting: auto-width columns, wrap text in answer/context cells
            from openpyxl.utils import get_column_letter
            from openpyxl.styles import Alignment, Font, PatternFill
            WRAP_COLS = {"question", "expected_answer", "generated_answer",
                         "answer_remarks", "material_remarks", "retrieved_context"}
            HEADER_FILL = PatternFill("solid", fgColor="1A5276")
            HEADER_FONT = Font(bold=True, color="FFFFFF")

            for ws in xw.book.worksheets:
                # Style header row
                for cell in ws[1]:
                    cell.fill = HEADER_FILL
                    cell.font = HEADER_FONT
                    cell.alignment = Alignment(wrap_text=False, vertical="center")

                # Style data rows
                for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
                    for cell in row:
                        col_name = ws.cell(row=1, column=cell.column).value or ""
                        should_wrap = col_name in WRAP_COLS
                        cell.alignment = Alignment(wrap_text=should_wrap, vertical="top")
                    # Taller rows for the Results sheet to show wrapped text
                    if ws.title == "Results":
                        ws.row_dimensions[row_idx].height = 60

                # Auto-width (cap at 60 for readability)
                for col_idx, col_cells in enumerate(ws.columns, start=1):
                    col_letter = get_column_letter(col_idx)
                    header = ws.cell(row=1, column=col_idx).value or ""
                    if header in WRAP_COLS:
                        ws.column_dimensions[col_letter].width = 45
                    else:
                        max_len = max((len(str(c.value or "")) for c in col_cells), default=10)
                        ws.column_dimensions[col_letter].width = min(max_len + 2, 30)

        return buf.getvalue()

    # ------------------------------------------------------------------
    # Test cases
    #
    # A test case is the unit of the library; a group is just a label that can be put on any
    # number of cases (and one case can carry any number of labels). Runs are resolved from
    # groups and/or individual test cases — see resolve_selection().
    # ------------------------------------------------------------------

    def import_dataset(self, name: str, df: "pd.DataFrame", fingerprint: str) -> str:
        """Backward-compat wrapper: create/find a group by name and import test cases.

        Returns the group_id (used as dataset_id in run summaries for traceability).
        """
        with self._lock:
            Q = Query()
            existing = self.groups.search(Q.name == name)
        if existing:
            group_id = existing[0]["group_id"]
        else:
            group_id = self.create_group(name)
        self.import_into_group(group_id, df)
        return group_id

    def _with_groups(self, cases: list[dict]) -> list[dict]:
        """Copy each case and attach ``groups``: the labels it carries, as [{group_id, name}]."""
        with self._lock:
            names = {g["group_id"]: g["name"] for g in self.groups.all() if not g.get("deleted_at")}
            members = list(self.group_members.all())
        by_tc: dict[str, list[dict]] = {}
        for m in members:
            name = names.get(m["group_id"])
            if name is not None:
                by_tc.setdefault(m["tc_id"], []).append({"group_id": m["group_id"], "name": name})
        return [
            {**c, "groups": sorted(by_tc.get(c["tc_id"], []), key=lambda g: g["name"].lower())}
            for c in cases
        ]

    def list_test_cases(
        self,
        group_id: str | None = None,
        status: str | None = None,
        # backward-compat alias — ignored but accepted so old callers don't break
        dataset_id: str | None = None,
    ) -> list[dict]:
        """Return the latest version of each test case (with its group labels), optionally filtered."""
        effective_group = group_id or dataset_id  # dataset_id alias
        with self._lock:
            Q = Query()
            if effective_group:
                member_tcs = {m["tc_id"] for m in self.group_members.search(Q.group_id == effective_group)}
                if not member_tcs:
                    return []
                all_tc = self.test_cases.search(Q.tc_id.one_of(list(member_tcs)))
            else:
                all_tc = self.test_cases.all()

        result = list(_latest_versions(all_tc).values())
        if status:
            result = [r for r in result if r.get("status") == status]
        return self._with_groups(sorted(result, key=_case_order))

    def get_test_case_history(self, tc_id: str, dataset_id: str | None = None) -> list[dict]:
        """Return all versions of a test case, oldest first."""
        with self._lock:
            Q = Query()
            versions = self.test_cases.search(Q.tc_id == tc_id)
        return sorted(versions, key=lambda r: r.get("version", 1))

    def update_test_case_status(self, tc_id: str, status: str, dataset_id: str | None = None) -> bool:
        """Set status of all versions of a test case to active / inactive."""
        return bool(self.update_status_bulk([tc_id], status))

    def update_status_bulk(self, tc_ids: list[str], status: str) -> int:
        """Set the status of several test cases at once: ``active`` or ``inactive`` (inactive cases do not run).
        Removing a case is ``delete_test_cases``. Returns how many cases were found."""
        if status not in ("active", "inactive"):
            return 0
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            Q = Query()
            known = {r["tc_id"] for r in self.test_cases.search(Q.tc_id.one_of(list(tc_ids)))} if tc_ids else set()
            if known:
                self.test_cases.update({"status": status, "updated_at": now}, Q.tc_id.one_of(list(known)))
        return len(known)

    def delete_test_cases(self, tc_ids: list[str]) -> int:
        """Permanently remove test cases: every version, and their group labels. Returns how many existed.
        Results of past runs are untouched (each receipt keeps its own copy of the question and answer)."""
        if not tc_ids:
            return 0
        with self._lock:
            Q = Query()
            found = {r["tc_id"] for r in self.test_cases.search(Q.tc_id.one_of(list(tc_ids)))}
            if found:
                self.test_cases.remove(Q.tc_id.one_of(list(found)))
                self.group_members.remove(Q.tc_id.one_of(list(found)))
        return len(found)

    def existing_tc_ids(self) -> set[str]:
        """The ids of every test case that still exists (past results use this to tell which were deleted since)."""
        with self._lock:
            return {r["tc_id"] for r in self.test_cases.all()}

    def _drop_legacy_deleted(self) -> None:
        """Test cases are deleted for good now. Ones an older version only hid (status "deleted") are removed here."""
        with self._lock:
            latest = _latest_versions(list(self.test_cases.all()))
            gone = [tid for tid, tc in latest.items() if tc.get("status") == "deleted"]
            if gone:
                Q = Query()
                self.test_cases.remove(Q.tc_id.one_of(gone))
                self.group_members.remove(Q.tc_id.one_of(gone))
        if gone:
            logger.info("removed %d test case(s) that had been deleted earlier", len(gone))

    def edit_test_case(self, tc_id: str, updates: dict, dataset_id: str | None = None) -> dict | None:
        """Create a new version of a test case with the given field updates.

        Editable: question, expected_answer, expected_sources, type, chat_id, turn_no.
        The tc_id never changes, so group labels and history follow the case when its
        chat or turn is edited. Returns the new version record, or None if tc_id is unknown
        or there is nothing to change. Raises ValueError for an invalid value.
        """
        allowed = {"question", "expected_answer", "expected_sources", "type", "chat_id", "turn_no"}
        updates = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if not updates:
            return None
        if "chat_id" in updates:
            updates["chat_id"] = str(updates["chat_id"]).strip()
            if not updates["chat_id"]:
                raise ValueError("Chat ID cannot be empty")
        if "turn_no" in updates:
            try:
                updates["turn_no"] = int(updates["turn_no"])
            except (TypeError, ValueError):
                raise ValueError("Turn number must be a whole number") from None
            if updates["turn_no"] < 1:
                raise ValueError("Turn number must be 1 or higher")
        if "question" in updates and not str(updates["question"]).strip():
            raise ValueError("Question cannot be empty")

        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            Q = Query()
            existing = self.test_cases.search(Q.tc_id == tc_id)
            if not existing:
                return None
            latest = max(existing, key=lambda r: r.get("version", 1))
            new_record = {k: v for k, v in latest.items() if not k.startswith("_")}
            new_record.pop("doc_id", None)
            new_record["version"] = latest["version"] + 1
            new_record["updated_at"] = now
            new_record.update(updates)
            self.test_cases.insert(new_record)

        return self._with_groups([new_record])[0]

    def list_datasets(self) -> list[dict]:
        """Backward-compat alias for list_groups()."""
        return self.list_groups()

    def resolve_selection(
        self,
        group_ids: list[str] | tuple = (),
        tc_ids: list[str] | tuple = (),
        status: str = "active",
        include_context: bool = True,
    ) -> "RunSelection":
        """Work out exactly which test cases a run would execute.

        ``group_ids`` pulls in every case carrying one of those labels, filtered by ``status``
        (``active`` | ``inactive`` | ``all``). ``tc_ids`` adds
        individual cases regardless of their active/inactive state. A case in several of the
        chosen groups runs once.

        Conversations are replayed turn by turn, so a case at turn 3 needs turns 1-2 for context.
        With ``include_context`` those earlier active turns of the same chat (limited to a shared
        group when the case has one) are added; they are counted separately in the result.

        Raises GroupNotFound for an unknown group, ValueError for a bad ``status``.
        """
        if status not in ("active", "inactive", "all"):
            raise ValueError(f"status must be 'active', 'inactive' or 'all', got {status!r}")
        group_ids = list(dict.fromkeys(group_ids))
        tc_ids = list(dict.fromkeys(tc_ids))

        with self._lock:
            latest = _latest_versions(list(self.test_cases.all()))
            group_names = {g["group_id"]: g["name"] for g in self.groups.all() if not g.get("deleted_at")}
            members = [m for m in self.group_members.all()]
        for gid in group_ids:
            if gid not in group_names:
                raise GroupNotFound(gid)

        tcs_of_group: dict[str, set[str]] = {}
        groups_of_tc: dict[str, set[str]] = {}
        for m in members:
            if m["group_id"] not in group_names:
                continue  # deleted groups no longer label anything
            tcs_of_group.setdefault(m["group_id"], set()).add(m["tc_id"])
            groups_of_tc.setdefault(m["tc_id"], set()).add(m["group_id"])

        chosen: dict[str, dict] = {}
        for gid in group_ids:
            for tid in tcs_of_group.get(gid, ()):
                tc = latest.get(tid)
                if tc is None:
                    continue
                if status != "all" and tc.get("status") != status:
                    continue
                chosen[tid] = tc
        missing = 0
        for tid in tc_ids:
            tc = latest.get(tid)
            if tc is None:
                missing += 1
            else:
                chosen[tid] = tc

        context: dict[str, dict] = {}
        if include_context:
            active_by_chat: dict[str, list[dict]] = {}
            for tc in latest.values():
                if tc.get("status") == "active":
                    active_by_chat.setdefault(str(tc["chat_id"]), []).append(tc)
            for tc in chosen.values():
                if tc["turn_no"] <= 1:
                    continue
                mine = groups_of_tc.get(tc["tc_id"], set())
                for prev in active_by_chat.get(str(tc["chat_id"]), []):
                    if prev["turn_no"] >= tc["turn_no"] or prev["tc_id"] in chosen:
                        continue
                    if mine and not (mine & groups_of_tc.get(prev["tc_id"], set())):
                        continue
                    context[prev["tc_id"]] = prev

        cases = sorted({**context, **chosen}.values(), key=_case_order)

        # Two different cases in one run on the same chat + turn would share a conversation
        # slot and silently overwrite each other's history — surface that instead.
        slots: dict[tuple[str, int], list[str]] = {}
        for tc in cases:
            slots.setdefault((str(tc["chat_id"]), int(tc["turn_no"])), []).append(tc["tc_id"])
        collisions = [
            {"chat_id": chat, "turn_no": turn, "tc_ids": ids}
            for (chat, turn), ids in slots.items() if len(ids) > 1
        ]

        names_of_tc = {
            tid: sorted(group_names[g] for g in gids if g in group_names)
            for tid, gids in groups_of_tc.items()
        }
        return RunSelection(
            df=_cases_to_df(cases, names_of_tc),
            selected=len(chosen),
            context=len(context),
            missing=missing,
            group_names=[group_names[g] for g in group_ids],
            collisions=collisions,
        )

    def create_test_case(self, chat_id: str, turn_no: int,
                         question: str, expected_answer: str,
                         type: str = "rag", expected_sources: str = "",
                         group_id: str | None = None,
                         # backward-compat: dataset_id accepted but ignored
                         dataset_id: str | None = None) -> dict:
        """Create a new test case manually (without dataset upload)."""
        now = datetime.now(timezone.utc).isoformat()
        tc_id = _tc_id(chat_id, turn_no, question)
        record = {
            "tc_id": tc_id,
            "version": 1,
            "chat_id": chat_id,
            "turn_no": turn_no,
            "type": type,
            "question": question,
            "expected_answer": expected_answer,
            "expected_sources": expected_sources,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            Q = Query()
            existing = self.test_cases.search(Q.tc_id == tc_id)
            if existing:
                latest = max(existing, key=lambda r: r.get("version", 1))
                record["version"] = latest["version"] + 1
                record["created_at"] = latest["created_at"]
            self.test_cases.insert(record)
        if group_id:
            self.add_tc_to_group(group_id, tc_id)
        return self._with_groups([record])[0]

    # ------------------------------------------------------------------
    # Review batches: test cases written from documents, saved as they are made and kept until approved
    # ------------------------------------------------------------------

    def save_batch(self, batch: dict) -> None:
        with self._lock:
            self.batches.upsert(json.loads(json.dumps(batch)), Query().batch_id == batch["batch_id"])

    def get_batch(self, batch_id: str) -> dict | None:
        self.purge_expired_batches()
        with self._lock:
            hits = self.batches.search(Query().batch_id == batch_id)
            return dict(hits[0]) if hits else None

    def list_batches(self) -> list[dict]:
        """Batches waiting for review, newest first."""
        self.purge_expired_batches()
        with self._lock:
            return sorted((dict(b) for b in self.batches.all()), key=lambda b: b.get("created_at", ""), reverse=True)

    def delete_batch(self, batch_id: str) -> bool:
        with self._lock:
            return bool(self.batches.remove(Query().batch_id == batch_id))

    def purge_expired_batches(self) -> int:
        """Delete batches nobody approved in time (never one that is still being written)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            expired = [b.doc_id for b in self.batches.all() if b.get("status") != "running" and b.get("expires_at", "9") < now]
            if expired:
                self.batches.remove(doc_ids=expired)
        return len(expired)

    def interrupt_running_batches(self) -> int:
        """After a restart nothing is writing any more: mark such batches so what they saved can be reviewed."""
        with self._lock:
            running = [b.doc_id for b in self.batches.all() if b.get("status") == "running"]
            if running:
                self.batches.update({"status": "interrupted"}, doc_ids=running)
        return len(running)

    # ------------------------------------------------------------------
    # Group management (groups are labels on test cases)
    # ------------------------------------------------------------------

    def _group_name_taken(self, name: str, ignore_id: str | None = None) -> bool:
        wanted = name.strip().lower()
        return any(
            g["name"].strip().lower() == wanted and g["group_id"] != ignore_id and not g.get("deleted_at")
            for g in self.groups.all()
        )

    def _is_live_group(self, group_id: str) -> bool:
        """True for a group that exists and is not deleted. Caller holds the lock."""
        hit = self.groups.search(Query().group_id == group_id)
        return bool(hit) and not hit[0].get("deleted_at")

    def create_group(self, name: str) -> str:
        """Create a named group. Returns group_id. Raises ConflictError if the name is in use."""
        name = name.strip()
        if not name:
            raise ValueError("Group name cannot be empty")
        gid = _group_id()
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if self._group_name_taken(name):
                raise ConflictError(f"A group named {name!r} already exists")
            self.groups.insert({"group_id": gid, "name": name, "created_at": now})
        return gid

    def rename_group(self, group_id: str, name: str) -> bool:
        """Rename a group. Raises ConflictError if another group already has that name."""
        name = name.strip()
        if not name:
            raise ValueError("Group name cannot be empty")
        with self._lock:
            Q = Query()
            if not self._is_live_group(group_id):
                return False
            if self._group_name_taken(name, ignore_id=group_id):
                raise ConflictError(f"A group named {name!r} already exists")
            old = self.groups.search(Q.group_id == group_id)[0]["name"]
            self.groups.update({"name": name}, Q.group_id == group_id)
            if old != name:
                self._rename_in_runs(old, name)
        return True

    def _rename_in_runs(self, old: str, new: str) -> None:
        """Past runs record group names; follow a rename so group history and dashboard filters keep working.
        Caller holds the lock."""
        for run in self.runs.all():
            names = run.get("group_names") or []
            stats = run.get("group_stats") or {}
            if old not in names and old not in stats:
                continue
            changes: dict = {
                "group_names": [new if n == old else n for n in names],
                "group_stats": {(new if k == old else k): v for k, v in stats.items()},
            }
            if old in str(run.get("dataset", "")).split(" + "):
                changes["dataset"] = " + ".join(new if p == old else p for p in str(run["dataset"]).split(" + "))
            self.runs.update(changes, doc_ids=[run.doc_id])

    def list_groups(self, include_deleted: bool = False) -> list[dict]:
        """Return groups with member_count. Deleted groups are
        left out unless ``include_deleted``; they carry a ``deleted_at`` timestamp."""
        with self._lock:
            all_groups = [dict(g) for g in self.groups.all()]
            all_members = list(self.group_members.all())
            latest = _latest_versions(list(self.test_cases.all()))
        counts: dict[str, int] = {}
        for m in all_members:
            tc = latest.get(m["tc_id"])
            if tc is not None:
                counts[m["group_id"]] = counts.get(m["group_id"], 0) + 1
        out = []
        for g in all_groups:
            if g.get("deleted_at") and not include_deleted:
                continue
            g["member_count"] = counts.get(g["group_id"], 0)
            g.setdefault("deleted_at", None)
            out.append(g)
        return sorted(out, key=lambda g: g.get("created_at", ""))

    def import_into_group(self, group_id: str, df: "pd.DataFrame") -> int:
        """Upsert test cases from a DataFrame and label them with a group. Returns how many labels were added."""
        rows = [
            {
                "row": i + 2,
                "chat_id": str(r.chat_id),
                "turn_no": int(r.turn_no),
                "type": str(getattr(r, "type", "rag")),
                "question": str(r.question),
                "expected_answer": str(r.expected_answer),
                "expected_sources": _clean_es(getattr(r, "expected_sources", "")),
                "groups": [],
            }
            for i, r in enumerate(df.itertuples(index=False))
        ]
        return self.import_cases(rows, group_ids=[group_id])["labelled"]

    def import_cases(
        self,
        rows: list[dict],
        *,
        group_ids: list[str] | tuple = (),
        new_group_name: str | None = None,
        update_by_slot: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """Add or update test cases from parsed rows (see ragevalkit.importing.parse_rows).

        Each row is one of: ``new``; ``update`` (a case with the same chat, turn and question exists but its
        answer, sources or type differ: saved as a new version, keeping the case's chat/turn and status);
        ``unchanged``. Importing the same file twice therefore changes nothing the second time. A case that
        was deleted is simply gone, so a row for it is new again.

        Every row is labelled with ``group_ids`` and ``new_group_name`` (created if needed), and with the group
        names in its own ``groups`` list (created if needed). Names match existing groups case-insensitively.

        ``update_by_slot``: a row whose chat and turn match exactly one existing case that has a *different
        question* updates that case instead of being added as a new one (the case keeps its history).
        Either way such rows are counted in ``slot_conflicts``.

        ``dry_run`` computes the same result without saving or creating anything, so a preview cannot
        disagree with the import. Raises GroupNotFound for an unknown ``group_ids`` entry.
        """
        now = datetime.now(timezone.utc).isoformat()

        # ---- which groups: chosen ones, a new one, and the names written in the file
        with self._lock:
            live = {g["group_id"]: g["name"] for g in self.groups.all() if not g.get("deleted_at")}
        for gid in group_ids:
            if gid not in live:
                raise GroupNotFound(gid)
        wanted_names: dict[str, str] = {}
        for name in ([new_group_name] if new_group_name and new_group_name.strip() else []) + [
            n for r in rows for n in (r.get("groups") or [])
        ]:
            wanted_names.setdefault(name.strip().lower(), name.strip())
        by_name = {n.lower(): gid for gid, n in live.items()}
        groups_created: list[str] = []
        name_to_id: dict[str, str | None] = {}
        for key, name in wanted_names.items():
            if key in by_name:
                name_to_id[key] = by_name[key]
            else:
                groups_created.append(name)
                name_to_id[key] = f"__new__:{key}" if dry_run else self.create_group(name)  # placeholder: nothing is created in a dry run
        everywhere = list(dict.fromkeys(
            list(group_ids)
            + ([name_to_id[new_group_name.strip().lower()]] if new_group_name and new_group_name.strip() else [])
        ))

        result = {
            "new": 0, "updated": 0, "unchanged": 0,
            "slot_conflicts": 0, "labelled": 0, "groups_created": groups_created, "outcomes": [],
        }
        with self._lock:
            Q = Query()
            latest = _latest_versions(list(self.test_cases.all()))
            linked = {(m["group_id"], m["tc_id"]) for m in self.group_members.all()}
            slots: dict[tuple[str, int], list[str]] = {}
            for tc in latest.values():
                slots.setdefault((str(tc["chat_id"]), int(tc["turn_no"])), []).append(tc["tc_id"])
            inserts: list[dict] = []
            links: list[dict] = []
            touched: set[str] = set()

            for r in rows:
                tc_id = _tc_id(r["chat_id"], r["turn_no"], r["question"])
                fields = {
                    "question": r["question"],
                    "expected_answer": r["expected_answer"],
                    "expected_sources": _clean_es(r.get("expected_sources", "")),
                    "type": r.get("type") or "rag",
                }
                target: str | None = tc_id
                existing = latest.get(tc_id)
                if existing is None:
                    candidates = [t for t in slots.get((r["chat_id"], r["turn_no"]), []) if t != tc_id and t not in touched]
                    same_question = [t for t in candidates if latest[t]["question"] == r["question"]]
                    if same_question:
                        # e.g. a case whose question was updated by an earlier import: match it by content
                        target, existing = same_question[0], latest[same_question[0]]
                    elif candidates:
                        result["slot_conflicts"] += 1
                        if update_by_slot and len(candidates) == 1:
                            target, existing = candidates[0], latest[candidates[0]]

                if existing is not None:
                    changed = any(existing.get(k, "") != v for k, v in fields.items())
                    outcome = "update" if changed else "unchanged"
                    if changed:
                        record = {k: v for k, v in existing.items() if not k.startswith("_")}
                        record.pop("doc_id", None)
                        record.update(fields, version=existing["version"] + 1, updated_at=now)
                        if r.get("origin"):
                            record["origin"] = r["origin"]
                        inserts.append(record)
                        latest[target] = record
                else:
                    outcome = "new"
                    record = {
                        "tc_id": tc_id, "version": 1, "chat_id": r["chat_id"], "turn_no": r["turn_no"],
                        **fields, "status": "active", "created_at": now, "updated_at": now,
                        **({"origin": r["origin"]} if r.get("origin") else {}),  # e.g. generated from a document
                    }
                    inserts.append(record)
                    latest[tc_id] = record
                    slots.setdefault((r["chat_id"], r["turn_no"]), []).append(tc_id)

                result[{"new": "new", "update": "updated", "unchanged": "unchanged"}[outcome]] += 1
                result["outcomes"].append({"row": r["row"], "outcome": outcome, "tc_id": target})
                if target is None:
                    continue
                touched.add(target)
                for gid in everywhere + [name_to_id[n.lower()] for n in (r.get("groups") or [])]:
                    if gid is None or (gid, target) in linked:
                        continue
                    linked.add((gid, target))
                    links.append({"group_id": gid, "tc_id": target, "added_at": now})

            result["labelled"] = len(links)
            if not dry_run:
                if inserts:
                    self.test_cases.insert_multiple(inserts)
                if links:
                    self.group_members.insert_multiple(links)
        return result

    def get_group_test_cases(self, group_id: str, status: str | None = None) -> list[dict]:
        """Return test cases in a group (latest version each)."""
        return self.list_test_cases(group_id=group_id, status=status)

    def add_tc_to_group(self, group_id: str, tc_id: str) -> bool:
        return bool(self.add_tcs_to_group(group_id, [tc_id]))

    def add_tcs_to_group(self, group_id: str, tc_ids: list[str]) -> int:
        """Label test cases with a group. Returns how many were newly added (already-labelled
        and unknown tc_ids are skipped). Raises GroupNotFound for an unknown group."""
        now = datetime.now(timezone.utc).isoformat()
        added = 0
        with self._lock:
            Q = Query()
            if not self._is_live_group(group_id):
                raise GroupNotFound(group_id)
            for tc_id in dict.fromkeys(tc_ids):
                if not self.test_cases.search(Q.tc_id == tc_id):
                    continue
                if self.group_members.search((Q.group_id == group_id) & (Q.tc_id == tc_id)):
                    continue
                self.group_members.insert({"group_id": group_id, "tc_id": tc_id, "added_at": now})
                added += 1
        return added

    def remove_tc_from_group(self, group_id: str, tc_id: str) -> bool:
        return bool(self.remove_tcs_from_group(group_id, [tc_id]))

    def remove_tcs_from_group(self, group_id: str, tc_ids: list[str]) -> int:
        """Remove a group label from test cases. Returns how many labels were removed."""
        if not tc_ids:
            return 0
        with self._lock:
            Q = Query()
            removed = self.group_members.remove((Q.group_id == group_id) & Q.tc_id.one_of(list(tc_ids)))
        return len(removed)

    def set_test_case_groups(self, tc_id: str, group_ids: list[str]) -> bool:
        """Replace the full set of group labels on one test case. Returns False if it is unknown.
        Raises GroupNotFound for an unknown group."""
        now = datetime.now(timezone.utc).isoformat()
        wanted = list(dict.fromkeys(group_ids))
        with self._lock:
            Q = Query()
            if not self.test_cases.search(Q.tc_id == tc_id):
                return False
            known = {g["group_id"] for g in self.groups.all() if not g.get("deleted_at")}
            for gid in wanted:
                if gid not in known:
                    raise GroupNotFound(gid)
            # only touch labels from live groups: a deleted group's labels must survive for a restore
            self.group_members.remove((Q.tc_id == tc_id) & Q.group_id.one_of(list(known)))
            for gid in wanted:
                self.group_members.insert({"group_id": gid, "tc_id": tc_id, "added_at": now})
        return True

    def delete_group(self, group_id: str) -> bool:
        """Delete a group: it disappears from the app but is kept (with its labels), so past runs
        that refer to it stay readable and it can be restored. Test cases are never touched.
        Returns False if the group does not exist or is already deleted."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if not self._is_live_group(group_id):
                return False
            self.groups.update({"deleted_at": now}, Query().group_id == group_id)
        return True

    def restore_group(self, group_id: str) -> bool:
        """Bring a deleted group back with its labels. Raises ConflictError if another group
        has taken its name in the meantime. Returns False if it is not a deleted group."""
        with self._lock:
            Q = Query()
            hit = self.groups.search(Q.group_id == group_id)
            if not hit or not hit[0].get("deleted_at"):
                return False
            if self._group_name_taken(hit[0]["name"], ignore_id=group_id):
                raise ConflictError(f"A group named {hit[0]['name']!r} already exists; rename it first")
            self.groups.update(delete("deleted_at"), Q.group_id == group_id)
        return True

    def purge_group(self, group_id: str) -> bool:
        """Permanently remove a group that is already deleted, with its labels. Past runs keep
        the group's name and scores. Returns False if it is not a deleted group."""
        with self._lock:
            Q = Query()
            hit = self.groups.search(Q.group_id == group_id)
            if not hit or not hit[0].get("deleted_at"):
                return False
            self.groups.remove(Q.group_id == group_id)
            self.group_members.remove(Q.group_id == group_id)
        return True

    # ------------------------------------------------------------------

    def close(self):
        self.db.close()
