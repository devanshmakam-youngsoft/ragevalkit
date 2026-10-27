"""Versions of an evaluation: their summaries and per-question results."""
import logging

from tinydb import Query

from ragevalkit.run_summary.case_scores import build_case_scores
from ragevalkit.run_summary.nodes import summary_nodes
from ragevalkit.storage.base import StoreBase
from ragevalkit.storage.excel_export import build_results_workbook
from ragevalkit.storage.exceptions import VersionNotFound
from ragevalkit.test_cases.identity import case_id_for

logger = logging.getLogger(__name__)


class RunsRepository(StoreBase):
    """Reads and writes the finished runs (versions) and their receipts."""

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
                tc = r.get("tc_id") or case_id_for(str(r.get("chat_id", "")), int(r.get("turn_no") or 1), str(r.get("question", "")))
                r["groups"] = sorted(names_of.get(tc, []))

    def export_xlsx(self, version: str) -> bytes:
        """The results of one version as an Excel workbook."""
        return build_results_workbook(self.get(version))
