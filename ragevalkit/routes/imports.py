"""Bulk import of test cases: a preview step that saves nothing, then the import itself."""
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile

from ragevalkit.exceptions import ConflictError, DatasetError, GroupNotFound
from ragevalkit.importing import (
    FIELD_LABELS, FIELDS, MAX_BYTES, clean_mapping, detect_mapping, parse_rows, read_table, template_workbook,
)
from ragevalkit.routes.deps import require_user

router = APIRouter(prefix="/api/test-cases/import", dependencies=[Depends(require_user)])

PREVIEW_SAMPLE = 10
PREVIEW_PROBLEMS = 50
MAX_PROBLEM_ROWS = 2000


async def _load(request: Request, file: UploadFile, sheet: str | None, mapping_json: str | None):
    """Read the upload and work out the column mapping. Returns (rows, problems, info)."""
    cfg = request.app.state.config
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB. Split it into smaller files.")
    suffix = Path(file.filename or "upload.xlsx").suffix or ".xlsx"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(data)
        try:
            df, sheets, used = read_table(path, sheet)
        except DatasetError as e:
            raise HTTPException(422, str(e))

    columns = list(df.columns)
    detected = detect_mapping(columns, cfg.column_map or None)
    try:
        requested = json.loads(mapping_json) if mapping_json else None
    except ValueError:
        raise HTTPException(422, "mapping must be JSON")
    mapping = clean_mapping(columns, requested, detected)
    rows, problems = parse_rows(df, mapping)
    info = {
        "filename": file.filename,
        "sheets": sheets,
        "sheet": used,
        "columns": columns,
        "mapping": mapping,
        "field_labels": FIELD_LABELS,
        "fields": list(FIELDS),
        "ignored_columns": [c for c in columns if c not in mapping.values()],
        "question_missing": mapping.get("question") is None,
        "auto_chat": mapping.get("chat_id") is None,
        "auto_turn": mapping.get("turn_no") is None,
        "total_rows": len(rows) + len(problems),
    }
    return rows, problems, info


def _group_names_in(rows: list[dict]) -> list[str]:
    seen: dict[str, str] = {}
    for r in rows:
        for name in r["groups"]:
            seen.setdefault(name.lower(), name)
    return sorted(seen.values(), key=str.lower)


@router.get("/template")
def download_template() -> Response:
    """A ready-to-fill .xlsx with the right columns, example rows and a short guide."""
    return Response(
        content=template_workbook(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=test_cases_template.xlsx"},
    )


@router.post("/preview")
async def preview_import(
    request: Request,
    file: UploadFile = File(...),
    sheet: str | None = Form(None),
    mapping: str | None = Form(None),
) -> dict:
    """What importing this file would do — new, updated, unchanged, unusable rows — without saving anything."""
    store = request.app.state.store
    rows, problems, info = await _load(request, file, sheet, mapping)
    result = store.import_cases(rows, dry_run=True)
    outcome_of = {o["row"]: o["outcome"] for o in result["outcomes"]}
    return {
        **info,
        "counts": {
            "new": result["new"], "update": result["updated"], "unchanged": result["unchanged"],
            "skipped_deleted": result["skipped_deleted"], "problem": len(problems),
        },
        "slot_conflicts": result["slot_conflicts"],
        "sample": [{**r, "outcome": outcome_of.get(r["row"])} for r in rows[:PREVIEW_SAMPLE]],
        "problems": [p.as_dict() for p in problems[:PREVIEW_PROBLEMS]],
        "group_names_in_file": _group_names_in(rows),
        "new_group_names": result["groups_created"],
    }


@router.post("", status_code=201)
async def import_test_cases(
    request: Request,
    file: UploadFile = File(...),
    sheet: str | None = Form(None),
    mapping: str | None = Form(None),
    group_ids: str | None = Form(None),       # JSON array: add every imported case to these groups
    new_group_name: str | None = Form(None),  # ...and to this group, created if needed
    update_by_slot: bool = Form(False),       # same chat + turn, different question: update instead of add
) -> dict:
    """Import the file's usable rows. Rows that cannot be used are returned so they can be fixed and re-imported."""
    store = request.app.state.store
    rows, problems, info = await _load(request, file, sheet, mapping)
    if info["question_missing"]:
        raise HTTPException(422, "No question column found. Choose which column holds the questions.")
    try:
        ids = json.loads(group_ids) if group_ids else []
        result = store.import_cases(
            rows, group_ids=[str(i) for i in ids], new_group_name=new_group_name or None,
            update_by_slot=update_by_slot,
        )
    except GroupNotFound as e:
        raise HTTPException(404, str(e))
    except (ConflictError, ValueError) as e:
        raise HTTPException(409, str(e))
    result.pop("outcomes")
    return {
        **result,
        "problems": len(problems),
        "problem_rows": [p.as_dict() for p in problems[:MAX_PROBLEM_ROWS]],
        "columns": info["columns"],
    }
