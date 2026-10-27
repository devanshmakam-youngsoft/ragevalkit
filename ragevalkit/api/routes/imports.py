"""Bulk import of test cases: a preview step that saves nothing, then the import itself."""
from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from ragevalkit.api.dependencies import get_config, get_store, require_user
from ragevalkit.api.services.imports import preview_import, read_upload, run_import
from ragevalkit.config import Config
from ragevalkit.storage.store import EvalStore
from ragevalkit.test_cases.importing.template import template_workbook

router = APIRouter(prefix="/api/test-cases/import", tags=["import"], dependencies=[Depends(require_user)])


@router.get("/template")
def download_template() -> Response:
    """A ready-to-fill .xlsx with the right columns, example rows and a short guide."""
    return Response(
        content=template_workbook(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=test_cases_template.xlsx"},
    )


@router.post("/preview")
async def preview_test_case_import(
    file: UploadFile = File(...),
    sheet: str | None = Form(None),
    mapping: str | None = Form(None),
    cfg: Config = Depends(get_config),
    store: EvalStore = Depends(get_store),
) -> dict:
    """What importing this file would do (new, updated, unchanged, unusable rows) without saving anything."""
    rows, problems, info = read_upload(cfg, file.filename, await file.read(), sheet, mapping)
    return preview_import(store, rows, problems, info)


@router.post("", status_code=201)
async def import_test_cases(
    file: UploadFile = File(...),
    sheet: str | None = Form(None),
    mapping: str | None = Form(None),
    group_ids: str | None = Form(None),       # JSON array: add every imported case to these groups
    new_group_name: str | None = Form(None),  # ...and to this group, created if needed
    update_by_slot: bool = Form(False),       # same chat + turn, different question: update instead of add
    cfg: Config = Depends(get_config),
    store: EvalStore = Depends(get_store),
) -> dict:
    """Import the file's usable rows. Rows that cannot be used are returned so they can be fixed and re-imported."""
    rows, problems, info = read_upload(cfg, file.filename, await file.read(), sheet, mapping)
    return run_import(store, rows, problems, info, group_ids_json=group_ids, new_group_name=new_group_name, update_by_slot=update_by_slot)
