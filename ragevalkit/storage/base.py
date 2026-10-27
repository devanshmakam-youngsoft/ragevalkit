"""The TinyDB file, its tables and the lock that guards them."""
import threading
from pathlib import Path

from tinydb import TinyDB


class StoreBase:
    """Opens the results file. TinyDB is not thread-safe by itself, and the runner writes from a background thread
    while the web server reads, so every repository takes ``self._lock`` around its table access."""

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

    def close(self):
        self.db.close()
