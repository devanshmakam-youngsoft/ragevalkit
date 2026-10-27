"""Generated test cases waiting for your approval."""
import json
import logging
from datetime import datetime, timezone

from tinydb import Query

from ragevalkit.storage.base import StoreBase

logger = logging.getLogger(__name__)


class GenerationBatchesRepository(StoreBase):
    """Review batches: saved while questions are written, deleted when approved or when they expire."""

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
