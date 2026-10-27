"""Finished runs ("versions"): their results and the Excel download."""
from fastapi import APIRouter, Depends, Response

from ragevalkit.api.dependencies import get_store, require_user
from ragevalkit.api.services.versions import export_version, get_version_with_deleted_flags
from ragevalkit.storage.store import EvalStore

router = APIRouter(prefix="/api/versions", tags=["versions"], dependencies=[Depends(require_user)])

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("")
def list_versions(store: EvalStore = Depends(get_store)) -> list[dict]:
    return store.list_versions()


@router.get("/{version}")
def get_version(version: str, store: EvalStore = Depends(get_store)) -> dict:
    return get_version_with_deleted_flags(store, version)


@router.get("/{version}/download")
def download_version(version: str, store: EvalStore = Depends(get_store)) -> Response:
    return Response(
        content=export_version(store, version),
        media_type=EXCEL_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename=version_{version}_results.xlsx"},
    )
