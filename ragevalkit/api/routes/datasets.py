"""The older dataset endpoints, kept so existing dashboards and scripts keep working."""
from fastapi import APIRouter, Depends, File, UploadFile

from ragevalkit.api.dependencies import get_config, get_store, require_user
from ragevalkit.api.services.datasets import (
    describe_default_dataset,
    describe_uploaded_dataset,
    import_uploaded_dataset,
)
from ragevalkit.api.services.recommendations import groups_with_history
from ragevalkit.config import Config
from ragevalkit.storage.store import EvalStore

router = APIRouter(prefix="/api", tags=["datasets"], dependencies=[Depends(require_user)])


@router.get("/dataset/default")
def default_dataset(cfg: Config = Depends(get_config)) -> dict:
    return describe_default_dataset(cfg)


@router.post("/dataset/validate")
async def validate_dataset(file: UploadFile = File(...), cfg: Config = Depends(get_config)) -> dict:
    return describe_uploaded_dataset(cfg, file.filename, await file.read())


@router.get("/datasets")
def list_datasets(cfg: Config = Depends(get_config), store: EvalStore = Depends(get_store)) -> list[dict]:
    """Alias for /api/groups, for backward compatibility."""
    return groups_with_history(cfg, store, include_deleted=False)


@router.post("/datasets/upload", status_code=201)
async def upload_dataset(file: UploadFile = File(...), cfg: Config = Depends(get_config), store: EvalStore = Depends(get_store)) -> dict:
    """Upload an xlsx to the test case library without starting an eval run."""
    return import_uploaded_dataset(cfg, store, file.filename, await file.read())
