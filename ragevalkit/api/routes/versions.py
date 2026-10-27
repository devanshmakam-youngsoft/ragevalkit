"""Finished runs ("versions"): their results and the Excel download."""
from fastapi import APIRouter, Depends, Response

from ragevalkit.api.dependencies import get_config, get_store, require_user
from ragevalkit.api.services.versions import (
    export_version,
    get_version_with_deleted_flags,
    read_version_log,
)
from ragevalkit.config import Config
from ragevalkit.storage.store import EvalStore

router = APIRouter(prefix="/api/versions", tags=["versions"], dependencies=[Depends(require_user)])

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("")
def list_versions(store: EvalStore = Depends(get_store)) -> list[dict]:
    return store.list_versions()


@router.get("/{version}")
def get_version(version: str, store: EvalStore = Depends(get_store)) -> dict:
    return get_version_with_deleted_flags(store, version)


@router.get("/{version}/log")
def download_version_log(version: str, cfg: Config = Depends(get_config), store: EvalStore = Depends(get_store)) -> Response:
    """The technical log of the run that produced this version, for whoever needs the details."""
    return Response(
        content=read_version_log(cfg, store, version),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=version_{version}_log.txt"},
    )


@router.get("/{version}/download")
def download_version(version: str, store: EvalStore = Depends(get_store)) -> Response:
    return Response(
        content=export_version(store, version),
        media_type=EXCEL_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename=version_{version}_results.xlsx"},
    )
