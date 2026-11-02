"""Bulk import of test cases: a preview step that saves nothing, then the import itself."""
from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from ragevalkit.core.config import Config
from ragevalkit.routers.dependencies import get_config, get_store, require_user
from ragevalkit.schemas.testcase_library import ImportPreview, ImportResult
from ragevalkit.services.db_services import EvalStore
from ragevalkit.services.testcases.testcase_import import (
    preview_import,
    read_upload,
    run_import,
    template_workbook,
)

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
) -> ImportPreview:
    """What importing this file would do (new, updated, unchanged, unusable rows) without saving anything.

    Accepts ``.xlsx``, ``.xlsm``, ``.csv``, ``.tsv`` and ``.txt`` files. ``sheet`` picks the worksheet of a
    workbook (default: one named ``dataset``, else the first). ``mapping`` is a JSON object that says which
    file column holds each field, for example ``{"question": "Query"}``; columns it leaves out are detected
    from their headers. Answers 413 when the file is over 10 MB and 422 when it cannot be read, has too many
    rows or ``mapping`` is not JSON.
    """
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
) -> ImportResult:
    """Import the file's usable rows. Rows that cannot be used are returned so they can be fixed and re-imported.

    ``file``, ``sheet`` and ``mapping`` work as in ``POST /api/test-cases/import/preview``. Importing the same
    file twice changes nothing the second time. Every imported case is also put in the groups given by
    ``group_ids`` and ``new_group_name``, and in any groups named in the file's own ``groups`` column.
    Answers 404 when a group in ``group_ids`` does not exist, 413 when the file is over 10 MB, and 422 when
    the file cannot be read, no question column is found or ``mapping`` is not JSON.
    """
    rows, problems, info = read_upload(cfg, file.filename, await file.read(), sheet, mapping)
    return run_import(store, rows, problems, info, group_ids_json=group_ids, new_group_name=new_group_name, update_by_slot=update_by_slot)
