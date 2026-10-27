"""The older upload-a-file datasets, kept so existing stores keep working."""
import logging

import pandas as pd
from tinydb import Query

from ragevalkit.storage.base import StoreBase

logger = logging.getLogger(__name__)


class DatasetsRepository(StoreBase):
    """Datasets uploaded as files; each is stored as a group of test cases."""

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

    def list_datasets(self) -> list[dict]:
        """Backward-compat alias for list_groups()."""
        return self.list_groups()
