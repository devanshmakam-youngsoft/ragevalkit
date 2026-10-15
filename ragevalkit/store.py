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
import math
import re
import statistics
import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from tinydb import Query, TinyDB

from ragevalkit.exceptions import VersionNotFound

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
    }
    for n in node_order(rows):
        summary[f"avg_{n}"] = _mean([(r.get("node_timings") or {}).get(n) for r in rows], 3)
    return summary


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
    return (
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
        self._lock = threading.Lock()

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

    def list_versions(self) -> list[dict]:
        with self._lock:
            summaries = self.runs.all()
        out = []
        for s in summaries:
            entry = dict(s)
            entry["nodes"] = summary_nodes(entry)
            out.append(entry)
        return sorted(out, key=lambda s: str(s.get("date", "")))

    def list_runs(self, include_archived: bool = False) -> list[dict]:
        """Return run summaries from the store, excluding archived runs by default."""
        with self._lock:
            summaries = self.runs.all()
        out = []
        for s in summaries:
            entry = dict(s)
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
            summary = dict(hits[0])
            rows = [dict(r) for r in self.receipts.search(Query().version == version)]
        summary["nodes"] = summary_nodes(summary)
        for row in rows:
            row.pop("version", None)
        return {"summary": summary, "rows": rows}

    def export_xlsx(self, version: str) -> bytes:
        data = self.get(version)
        rows = data["rows"]
        nodes = node_order(rows)

        # ── human-readable column order for the Results sheet ──────────────
        # Primary identification
        ID_COLS   = ["chat_id", "turn_no", "type", "status"]
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
                       ["session_id", "step_inputs", "step_outputs", "node_timings", "version"])
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
                rec[c] = _cell(r.get(c))
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
    # Dataset + test case management
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

    def list_test_cases(
        self,
        group_id: str | None = None,
        status: str | None = None,
        # backward-compat alias — ignored but accepted so old callers don't break
        dataset_id: str | None = None,
    ) -> list[dict]:
        """Return the latest version of each test case, optionally filtered by group."""
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

        by_key: dict[str, dict] = {}
        for tc in all_tc:
            key = tc["tc_id"]
            if key not in by_key or tc["version"] > by_key[key]["version"]:
                by_key[key] = tc

        result = list(by_key.values())
        if status:
            result = [r for r in result if r.get("status") == status]
        return sorted(result, key=lambda r: (r.get("chat_id", ""), r.get("turn_no", 0)))

    def get_test_case_history(self, tc_id: str, dataset_id: str | None = None) -> list[dict]:
        """Return all versions of a test case, oldest first."""
        with self._lock:
            Q = Query()
            versions = self.test_cases.search(Q.tc_id == tc_id)
        return sorted(versions, key=lambda r: r.get("version", 1))

    def update_test_case_status(self, tc_id: str, status: str, dataset_id: str | None = None) -> bool:
        """Set status of all versions of a test case to active / inactive / deleted."""
        if status not in ("active", "inactive", "deleted"):
            return False
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            Q = Query()
            updated = self.test_cases.update({"status": status, "updated_at": now}, Q.tc_id == tc_id)
        return bool(updated)

    def edit_test_case(self, tc_id: str, updates: dict, dataset_id: str | None = None) -> dict | None:
        """Create a new version of a test case with the given field updates.

        Only question, expected_answer, expected_sources, and type can be changed.
        Returns the new version record, or None if tc_id is not found.
        """
        allowed = {"question", "expected_answer", "expected_sources", "type"}
        updates = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if not updates:
            return None

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

        return new_record

    def list_datasets(self) -> list[dict]:
        """Backward-compat alias for list_groups()."""
        return self.list_groups()

    def test_cases_as_df(self, group_id: str | None = None, status: str = "active",
                         # backward-compat alias
                         dataset_id: str | None = None) -> "pd.DataFrame":
        """Export test cases as a DataFrame suitable for running an eval."""
        effective_group = group_id or dataset_id
        if effective_group:
            cases = self.get_group_test_cases(effective_group, status=status if status != "all" else None)
        else:
            cases = self.list_test_cases(status=status if status != "all" else None)
        if not cases:
            return pd.DataFrame()
        rows = []
        for tc in cases:
            row: dict = {
                "chat_id": tc["chat_id"],
                "turn_no": tc["turn_no"],
                "type": tc.get("type", ""),
                "question": tc["question"],
                "expected_answer": tc["expected_answer"],
            }
            es = _clean_es(tc.get("expected_sources", ""))
            if es:
                row["expected_sources"] = es
            rows.append(row)
        return pd.DataFrame(rows)

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
        return record

    # ------------------------------------------------------------------
    # Group management
    # ------------------------------------------------------------------

    def create_group(self, name: str) -> str:
        """Create a named test-case group. Returns group_id."""
        gid = _group_id()
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self.groups.insert({"group_id": gid, "name": name, "created_at": now})
        return gid

    def list_groups(self) -> list[dict]:
        """Return all groups with member_count."""
        with self._lock:
            all_groups = list(self.groups.all())
            all_members = list(self.group_members.all())
        counts: dict[str, int] = {}
        for m in all_members:
            counts[m["group_id"]] = counts.get(m["group_id"], 0) + 1
        for g in all_groups:
            g["member_count"] = counts.get(g["group_id"], 0)
        return sorted(all_groups, key=lambda g: g.get("created_at", ""))

    def import_into_group(self, group_id: str, df: "pd.DataFrame") -> int:
        """Upsert test cases from a DataFrame and link them to a group."""
        now = datetime.now(timezone.utc).isoformat()
        linked = 0
        with self._lock:
            Q = Query()
            for row in df.itertuples(index=False):
                tc_id = _tc_id(str(row.chat_id), int(row.turn_no), str(row.question))
                new_record = {
                    "tc_id": tc_id,
                    "version": 1,
                    "chat_id": str(row.chat_id),
                    "turn_no": int(row.turn_no),
                    "type": str(getattr(row, "type", "rag")),
                    "question": str(row.question),
                    "expected_answer": str(row.expected_answer),
                    "expected_sources": _clean_es(getattr(row, "expected_sources", "")),
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
                existing = self.test_cases.search(Q.tc_id == tc_id)
                if not existing:
                    self.test_cases.insert(new_record)
                else:
                    latest = max(existing, key=lambda r: r.get("version", 1))
                    if (latest["question"] != new_record["question"] or
                            latest["expected_answer"] != new_record["expected_answer"] or
                            latest.get("expected_sources", "") != new_record["expected_sources"]):
                        new_record["version"] = latest["version"] + 1
                        new_record["created_at"] = latest["created_at"]
                        self.test_cases.insert(new_record)
                # Link to group (idempotent)
                already = self.group_members.search(
                    (Q.group_id == group_id) & (Q.tc_id == tc_id)
                )
                if not already:
                    self.group_members.insert({"group_id": group_id, "tc_id": tc_id, "added_at": now})
                    linked += 1
        return linked

    def get_group_test_cases(self, group_id: str, status: str | None = None) -> list[dict]:
        """Return test cases in a group (latest version each)."""
        with self._lock:
            Q = Query()
            member_tcs = {m["tc_id"] for m in self.group_members.search(Q.group_id == group_id)}
            if not member_tcs:
                return []
            all_tc = self.test_cases.search(Q.tc_id.one_of(list(member_tcs)))
        by_key: dict[str, dict] = {}
        for tc in all_tc:
            tid = tc["tc_id"]
            if tid not in by_key or tc["version"] > by_key[tid]["version"]:
                by_key[tid] = tc
        result = list(by_key.values())
        if status:
            result = [r for r in result if r.get("status") == status]
        return sorted(result, key=lambda r: (r.get("chat_id", ""), r.get("turn_no", 0)))

    def add_tc_to_group(self, group_id: str, tc_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            Q = Query()
            already = self.group_members.search((Q.group_id == group_id) & (Q.tc_id == tc_id))
            if already:
                return False
            self.group_members.insert({"group_id": group_id, "tc_id": tc_id, "added_at": now})
        return True

    def remove_tc_from_group(self, group_id: str, tc_id: str) -> bool:
        with self._lock:
            Q = Query()
            removed = self.group_members.remove((Q.group_id == group_id) & (Q.tc_id == tc_id))
        return bool(removed)

    def delete_group(self, group_id: str) -> bool:
        """Delete a group and all its membership records. Test cases themselves are not removed."""
        with self._lock:
            Q = Query()
            removed = self.groups.remove(Q.group_id == group_id)
            self.group_members.remove(Q.group_id == group_id)
        return bool(removed)

    # ------------------------------------------------------------------

    def close(self):
        self.db.close()
