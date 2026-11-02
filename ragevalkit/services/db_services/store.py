"""``EvalStore``: the results file, assembled from one repository per kind of data."""
from pathlib import Path

from ragevalkit.services.db_services.datasets import DatasetsRepository
from ragevalkit.services.db_services.evaluation_runs import RunsRepository
from ragevalkit.services.db_services.generated_batches import GenerationBatchesRepository
from ragevalkit.services.db_services.testcase_groups import GroupsRepository
from ragevalkit.services.db_services.testcase_import import CaseImportRepository
from ragevalkit.services.db_services.testcases import CaseLibraryRepository


class EvalStore(
    RunsRepository,
    CaseLibraryRepository,
    GroupsRepository,
    CaseImportRepository,
    DatasetsRepository,
    GenerationBatchesRepository,
):
    """Everything ragevalkit saves, in one TinyDB file: runs and receipts, test cases, groups and review batches."""

    def __init__(self, path: Path):
        super().__init__(path)
        self._drop_legacy_deleted()
