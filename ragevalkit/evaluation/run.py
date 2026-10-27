"""The state of one evaluation run while it is going on."""
import uuid
from datetime import datetime, timezone

from ragevalkit.logs import EventLog


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
        self.error: str | None = None          # plain-language reason a run failed
        self.error_detail: str = ""            # the technical version of it, shown on request
        self.log: EventLog | None = None
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
            "error_detail": self.error_detail,
            "issue_count": self.log.issue_total if self.log else 0,
        }

    def emit(self, event_type: str, **data) -> None:
        self.events.append({"type": event_type, **self.snapshot(), **data})


def light_row(r: dict) -> dict:
    return {
        k: r.get(k)
        for k in ("chat_id", "turn_no", "type", "question", "answer_marks", "material_marks", "status")
    }
