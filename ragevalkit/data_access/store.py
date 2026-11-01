"""``EvalStore``: the results file, assembled from one repository per kind of data."""
from pathlib import Path

from ragevalkit.data_access.datasets import DatasetsRepository
from ragevalkit.data_access.evaluation_runs import RunsRepository
from ragevalkit.data_access.generated_batches import GenerationBatchesRepository
from ragevalkit.data_access.testcase_groups import GroupsRepository
from ragevalkit.data_access.testcase_import import CaseImportRepository
from ragevalkit.data_access.testcases import CaseLibraryRepository


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
