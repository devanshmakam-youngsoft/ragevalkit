"""Finished runs ("versions"): their results and the Excel download."""
from fastapi import APIRouter, Depends, Response

from ragevalkit.core.config import Config
from ragevalkit.routers.dependencies import get_config, get_store, require_user
from ragevalkit.schemas.evaluation import VersionDetail, VersionSummary
from ragevalkit.services.db_services import EvalStore
from ragevalkit.services.evaluation_runner import (
    export_version,
    get_version_with_deleted_flags,
    read_version_log,
)

router = APIRouter(prefix="/api/versions", tags=["versions"], dependencies=[Depends(require_user)])

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("")
def list_versions(store: EvalStore = Depends(get_store)) -> list[VersionSummary]:
    """List every saved version with its scores, oldest first.

    Archived versions are included (their ``archived`` field is true). Per-question results are not part of
    the list; read them with ``GET /api/versions/{version}``.
    """
    return store.list_versions()


@router.get("/{version}")
def get_version(version: str, store: EvalStore = Depends(get_store)) -> VersionDetail:
    """Get one version: its summary and the result of every question.

    A result whose test case has been deleted since the run is marked ``case_deleted``. Answers 404 for an
    unknown version.
    """
    return get_version_with_deleted_flags(store, version)


@router.get("/{version}/log")
def download_version_log(version: str, cfg: Config = Depends(get_config), store: EvalStore = Depends(get_store)) -> Response:
    """The technical log of the run that produced this version, for whoever needs the details.

    Sent as a plain-text download. Answers 404 for an unknown version or when its log file is no longer available.
    """
    return Response(
        content=read_version_log(cfg, store, version),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=version_{version}_log.txt"},
    )


@router.get("/{version}/download")
def download_version(version: str, store: EvalStore = Depends(get_store)) -> Response:
    """Download a version's results as an Excel workbook (.xlsx). Answers 404 for an unknown version."""
    return Response(
        content=export_version(store, version),
        media_type=EXCEL_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename=version_{version}_results.xlsx"},
    )
