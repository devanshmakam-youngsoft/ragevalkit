"""The older dataset endpoints, kept so existing dashboards and scripts keep working."""
from fastapi import APIRouter, Depends, File, UploadFile

from ragevalkit.core.config import Config
from ragevalkit.routers.dependencies import get_config, get_store, require_user
from ragevalkit.schemas.testcase_library.responses import (
    DatasetInfo,
    DatasetUploaded,
    GroupWithHistory,
)
from ragevalkit.services.db_services.store import EvalStore
from ragevalkit.services.spreadsheet_loader.legacy_datasets import (
    describe_default_dataset,
    describe_uploaded_dataset,
    import_uploaded_dataset,
)
from ragevalkit.services.version_recommender.recommendation_views import groups_with_history

router = APIRouter(prefix="/api", tags=["datasets"], dependencies=[Depends(require_user)])


@router.get("/dataset/default")
def default_dataset(cfg: Config = Depends(get_config)) -> DatasetInfo:
    """Describe the default dataset the server was started with: its file name, rows, chats and required columns.

    Answers 404 when no default dataset is configured or its file cannot be read.
    """
    return describe_default_dataset(cfg)


@router.post("/dataset/validate")
async def validate_dataset(file: UploadFile = File(...), cfg: Config = Depends(get_config)) -> DatasetInfo:
    """Check an uploaded spreadsheet and report what it holds (rows and chats), without saving or running it.

    Answers 422 when the file cannot be read or is missing required columns.
    """
    return describe_uploaded_dataset(cfg, file.filename, await file.read())


@router.get("/datasets")
def list_datasets(cfg: Config = Depends(get_config), store: EvalStore = Depends(get_store)) -> list[GroupWithHistory]:
    """Alias for /api/groups, for backward compatibility. Deleted groups are not included."""
    return groups_with_history(cfg, store, include_deleted=False)


@router.post("/datasets/upload", status_code=201)
async def upload_dataset(file: UploadFile = File(...), cfg: Config = Depends(get_config), store: EvalStore = Depends(get_store)) -> DatasetUploaded:
    """Upload an xlsx to the test case library without starting an eval run.

    The file's rows are added as test cases to the group named after the file; the group is created when it
    does not exist. ``dataset_id`` in the answer is that group's id. Answers 422 when the file cannot be read.
    """
    return import_uploaded_dataset(cfg, store, file.filename, await file.read())
