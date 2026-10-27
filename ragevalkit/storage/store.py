"""``EvalStore``: the results file, assembled from one repository per kind of data."""
from pathlib import Path

from ragevalkit.storage.case_import_repository import CaseImportRepository
from ragevalkit.storage.datasets_repository import DatasetsRepository
from ragevalkit.storage.generation_batches_repository import GenerationBatchesRepository
from ragevalkit.storage.groups_repository import GroupsRepository
from ragevalkit.storage.runs_repository import RunsRepository
from ragevalkit.storage.case_library_repository import CaseLibraryRepository


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
