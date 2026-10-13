import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import pandas as _pd

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ragevalkit.dataset import REQUIRED_COLUMNS, DatasetError, load_dataset
from ragevalkit.routes.deps import require_user
from ragevalkit.runner import RunBusy
from ragevalkit.store import VersionNotFound, valid_version



router = APIRouter(prefix="/api", dependencies=[Depends(require_user)])


def _check_version(version: str) -> str:
    version = version.strip()
    if not valid_version(version):
        raise HTTPException(422, "Version may only contain letters, digits, '.', '_' or '-' (max 20 chars)")
    return version


# ---------------------------------------------------------------------------
# Dataset endpoints
# ---------------------------------------------------------------------------

@router.get("/dataset/default")
def default_dataset(request: Request) -> dict:
    cfg = request.app.state.config
    if not cfg.default_dataset:
        raise HTTPException(404, "No default dataset configured")
    try:
        df = load_dataset(cfg.default_dataset, cfg.dataset_sheet)
    except (DatasetError, FileNotFoundError) as e:
        raise HTTPException(404, f"Default dataset unavailable: {e}")
    return {
        "name": cfg.default_dataset.name,
        "rows": len(df),
        "chats": int(df.chat_id.nunique()),
        "required_columns": REQUIRED_COLUMNS,
        "fingerprint": df.attrs.get("fingerprint", ""),
    }


@router.post("/dataset/validate")
async def validate_dataset(request: Request, file: UploadFile = File(...)) -> dict:
    cfg = request.app.state.config
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.xlsx"
        path.write_bytes(await file.read())
        try:
            df = load_dataset(
                path, cfg.dataset_sheet,
                column_map=cfg.column_map or None,
                extra_columns=cfg.extra_columns or None,
            )
        except DatasetError as e:
            raise HTTPException(422, str(e))
    return {
        "name": file.filename,
        "rows": len(df),
        "chats": int(df.chat_id.nunique()),
        "fingerprint": df.attrs.get("fingerprint", ""),
    }


# ---------------------------------------------------------------------------
# Eval run endpoints
# ---------------------------------------------------------------------------

@router.post("/runs", status_code=202)
async def start_run(
    request: Request,
    version: str = Form(...),
    overwrite: bool = Form(False),
    file: UploadFile | None = File(None),
    group_id: str | None = Form(None),
    group_ids: str | None = Form(None),  # JSON array of group IDs for multi-group runs
    dataset_id: str | None = Form(None),  # backward-compat alias for group_id
    status_filter: str = Form("active"),
    save_as_group: bool = Form(False),
    group_name: str | None = Form(None),
    notes: str = Form(""),
) -> dict:
    cfg, store, manager = request.app.state.config, request.app.state.store, request.app.state.manager
    version = _check_version(version)
    if store.exists(version) and not overwrite:
        raise HTTPException(409, f"Version {version} already exists")

    # Parse multi-group IDs (JSON string from frontend)
    parsed_group_ids: list[str] = []
    if group_ids:
        try:
            parsed_group_ids = json.loads(group_ids)
        except Exception:
            parsed_group_ids = [g.strip() for g in group_ids.split(",") if g.strip()]

    # Resolve effective groups: multi-group > single group_id > dataset_id alias
    effective_groups = parsed_group_ids or ([group_id] if group_id else []) or ([dataset_id] if dataset_id else [])
    effective_group = effective_groups[0] if len(effective_groups) == 1 else None

    run_group_names: list[str] = []

    if len(effective_groups) > 1:
        # Multi-group run: merge test cases from all selected groups
        all_groups = store.list_groups()
        dfs = []
        for gid in effective_groups:
            df_part = store.test_cases_as_df(group_id=gid, status=status_filter)
            if not df_part.empty:
                dfs.append(df_part)
            grp_meta = next((g for g in all_groups if g["group_id"] == gid), None)
            run_group_names.append(grp_meta["name"] if grp_meta else gid)
        if not dfs:
            raise HTTPException(404, f"No {status_filter} test cases found in selected groups")
        df = _pd.concat(dfs, ignore_index=True).drop_duplicates(subset=["chat_id", "turn_no"])
        dataset_name = " + ".join(run_group_names)
    elif effective_group:
        # Run from a single saved group of test cases
        df = store.test_cases_as_df(group_id=effective_group, status=status_filter)
        if df.empty:
            raise HTTPException(404, f"No {status_filter} test cases found for group {effective_group!r}")
        groups = store.list_groups()
        grp_meta = next((g for g in groups if g["group_id"] == effective_group), None)
        dataset_name = grp_meta["name"] if grp_meta else effective_group
        run_group_names = [dataset_name]
    elif file is not None and file.filename and save_as_group and group_name:
        run_group_names = [group_name]
        # Upload file, save as group, then run from it
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "upload.xlsx"
            path.write_bytes(await file.read())
            try:
                df = load_dataset(
                    path, cfg.dataset_sheet,
                    column_map=cfg.column_map or None,
                    extra_columns=cfg.extra_columns or None,
                )
            except DatasetError as e:
                raise HTTPException(422, str(e))
        new_group_id = store.create_group(group_name)
        store.import_into_group(new_group_id, df)
        df = store.test_cases_as_df(group_id=new_group_id, status=status_filter)
        dataset_name = group_name
    elif file is not None and file.filename:
        cfg.inputs_dir.mkdir(parents=True, exist_ok=True)
        dataset_path = cfg.inputs_dir / f"version_{version}_input.xlsx"
        with dataset_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        dataset_name = file.filename
        try:
            df = load_dataset(
                dataset_path, cfg.dataset_sheet,
                column_map=cfg.column_map or None,
                extra_columns=cfg.extra_columns or None,
            )
        except FileNotFoundError:
            raise HTTPException(404, "Dataset file not found")
        except DatasetError as e:
            raise HTTPException(422, str(e))
    elif cfg.default_dataset:
        dataset_path, dataset_name = cfg.default_dataset, cfg.default_dataset.name
        try:
            df = load_dataset(
                dataset_path, cfg.dataset_sheet,
                column_map=cfg.column_map or None,
                extra_columns=cfg.extra_columns or None,
            )
        except FileNotFoundError:
            raise HTTPException(404, "Dataset file not found")
        except DatasetError as e:
            raise HTTPException(422, str(e))
    else:
        raise HTTPException(400, "No dataset provided and no default_dataset configured")

    try:
        run = manager.start(version, df, dataset_name, notes=notes, group_names=run_group_names)
    except RunBusy as e:
        raise HTTPException(409, str(e))
    return run.snapshot()


@router.post("/runs/{run_id}/stop", status_code=202)
def stop_run(run_id: str, request: Request) -> dict:
    """Request an early stop for a running eval. Partial results are saved."""
    run = request.app.state.manager.runs.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if run.status != "running":
        raise HTTPException(409, f"Run is not running (status: {run.status})")
    run.stop_requested = True
    return {"run_id": run_id, "message": "Stop requested — run will finish current row and save partial results."}


@router.get("/runs")
def list_runs(request: Request) -> list[dict]:
    return request.app.state.store.list_runs(include_archived=False)


@router.delete("/runs/{run_id}", status_code=200)
def delete_run(run_id: str, request: Request) -> dict:
    """Delete a completed run and all its receipts from the store."""
    ok = request.app.state.store.delete_run(run_id)
    if not ok:
        raise HTTPException(404, "Run not found")
    return {"run_id": run_id, "deleted": True}


@router.patch("/runs/{run_id}/archive", status_code=200)
def archive_run(run_id: str, request: Request) -> dict:
    """Archive a run so it is hidden from the default dashboard listing."""
    ok = request.app.state.store.archive_run(run_id)
    if not ok:
        raise HTTPException(404, "Run not found")
    return {"run_id": run_id, "archived": True}


@router.patch("/runs/{run_id}/unarchive", status_code=200)
def unarchive_run(run_id: str, request: Request) -> dict:
    """Restore an archived run to the default dashboard listing."""
    ok = request.app.state.store.unarchive_run(run_id)
    if not ok:
        raise HTTPException(404, "Run not found")
    return {"run_id": run_id, "archived": False}


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request):
    run = request.app.state.manager.runs.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")

    async def gen():
        sent = 0
        while True:
            while sent < len(run.events):
                yield f"data: {json.dumps(run.events[sent], default=str)}\n\n"
                sent += 1
            if run.status not in ("running",) and sent >= len(run.events):
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.3)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------------------
# Version (completed eval result) endpoints
# ---------------------------------------------------------------------------

@router.get("/versions")
def list_versions(request: Request) -> list[dict]:
    return request.app.state.store.list_versions()


@router.get("/versions/{version}")
def get_version(version: str, request: Request) -> dict:
    try:
        return request.app.state.store.get(version)
    except VersionNotFound:
        raise HTTPException(404, "Version not found")


@router.get("/versions/{version}/download")
def download_version(version: str, request: Request):
    store = request.app.state.store
    if not valid_version(version) or not store.exists(version):
        raise HTTPException(404, "Version not found")
    try:
        data = store.export_xlsx(version)
    except VersionNotFound:
        raise HTTPException(404, "Version not found")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=version_{version}_results.xlsx"},
    )


# ---------------------------------------------------------------------------
# Test case management endpoints
# ---------------------------------------------------------------------------

class TestCaseUpdate(BaseModel):
    question: str | None = None
    expected_answer: str | None = None
    expected_sources: str | None = None
    type: str | None = None


class TestCaseStatusUpdate(BaseModel):
    status: str  # "active" | "inactive" | "deleted"


@router.get("/test-cases")
def list_test_cases(
    request: Request,
    group_id: str | None = None,
    dataset_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List test cases. Optionally filter by group_id/dataset_id or status (active/inactive/deleted)."""
    return request.app.state.store.list_test_cases(group_id=group_id, dataset_id=dataset_id, status=status)


@router.get("/test-cases/{tc_id}")
def get_test_case(tc_id: str, request: Request) -> dict:
    """Get the latest version of a test case."""
    all_cases = request.app.state.store.list_test_cases()
    match = next((c for c in all_cases if c["tc_id"] == tc_id), None)
    if not match:
        raise HTTPException(404, "Test case not found")
    return match


@router.get("/test-cases/{tc_id}/history")
def get_test_case_history(tc_id: str, request: Request) -> list[dict]:
    """Return all version records for a test case, oldest first."""
    history = request.app.state.store.get_test_case_history(tc_id)
    if not history:
        raise HTTPException(404, "Test case not found")
    return history


@router.patch("/test-cases/{tc_id}")
def update_test_case(tc_id: str, body: TestCaseUpdate, request: Request) -> dict:
    """Edit a test case — creates a new version record. Old versions are preserved."""
    result = request.app.state.store.edit_test_case(tc_id, body.model_dump(exclude_none=True))
    if result is None:
        raise HTTPException(404, "Test case not found or no valid fields provided")
    return result


@router.patch("/test-cases/{tc_id}/status")
def set_test_case_status(tc_id: str, body: TestCaseStatusUpdate, request: Request) -> dict:
    """Activate, deactivate, or soft-delete a test case."""
    ok = request.app.state.store.update_test_case_status(tc_id, body.status)
    if not ok:
        raise HTTPException(404, f"Test case not found or invalid status '{body.status}'")
    return {"tc_id": tc_id, "status": body.status}


# ---------------------------------------------------------------------------
# Group endpoints
# ---------------------------------------------------------------------------

class CreateGroup(BaseModel):
    name: str


@router.get("/groups")
def list_groups(request: Request) -> list[dict]:
    """List all test case groups."""
    return request.app.state.store.list_groups()


@router.post("/groups", status_code=201)
def create_group(body: CreateGroup, request: Request) -> dict:
    store = request.app.state.store
    gid = store.create_group(body.name)
    groups = store.list_groups()
    return next(g for g in groups if g["group_id"] == gid)


@router.post("/groups/{group_id}/import", status_code=201)
async def import_into_group(group_id: str, request: Request, file: UploadFile = File(...)) -> dict:
    cfg, store = request.app.state.config, request.app.state.store
    groups = store.list_groups()
    if not any(g["group_id"] == group_id for g in groups):
        raise HTTPException(404, f"Group {group_id!r} not found")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.xlsx"
        path.write_bytes(await file.read())
        try:
            df = load_dataset(path, cfg.dataset_sheet, column_map=cfg.column_map or None, extra_columns=cfg.extra_columns or None)
        except DatasetError as e:
            raise HTTPException(422, str(e))
        count = store.import_into_group(group_id, df)
    return {"group_id": group_id, "linked": count}


@router.get("/groups/{group_id}/test-cases")
def group_test_cases(group_id: str, request: Request, status: str | None = None) -> list[dict]:
    return request.app.state.store.get_group_test_cases(group_id, status=status)


@router.post("/groups/{group_id}/members/{tc_id}", status_code=201)
def add_to_group(group_id: str, tc_id: str, request: Request) -> dict:
    ok = request.app.state.store.add_tc_to_group(group_id, tc_id)
    return {"group_id": group_id, "tc_id": tc_id, "added": ok}


@router.delete("/groups/{group_id}/members/{tc_id}", status_code=200)
def remove_from_group(group_id: str, tc_id: str, request: Request) -> dict:
    ok = request.app.state.store.remove_tc_from_group(group_id, tc_id)
    if not ok:
        raise HTTPException(404, "Member not found")
    return {"group_id": group_id, "tc_id": tc_id}


@router.delete("/groups/{group_id}", status_code=200)
def delete_group(group_id: str, request: Request) -> dict:
    """Delete a group and unlink all its members. Test cases themselves are not removed."""
    ok = request.app.state.store.delete_group(group_id)
    if not ok:
        raise HTTPException(404, "Group not found")
    return {"group_id": group_id, "deleted": True}


@router.get("/datasets")
def list_datasets(request: Request) -> list[dict]:
    """Alias for /api/groups — backward compat."""
    return request.app.state.store.list_groups()


@router.post("/datasets/upload", status_code=201)
async def upload_dataset(request: Request, file: UploadFile = File(...)) -> dict:
    """Upload an xlsx to the test case library without starting an eval run."""
    cfg, store = request.app.state.config, request.app.state.store
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.xlsx"
        path.write_bytes(await file.read())
        try:
            df = load_dataset(
                path, cfg.dataset_sheet,
                column_map=cfg.column_map or None,
                extra_columns=cfg.extra_columns or None,
            )
        except DatasetError as e:
            raise HTTPException(422, str(e))
        fingerprint = df.attrs.get("fingerprint", "")
        dataset_id = store.import_dataset(file.filename or "upload.xlsx", df, fingerprint)
    return {"dataset_id": dataset_id, "rows": len(df)}


class CreateTestCase(BaseModel):
    chat_id: str
    turn_no: int
    question: str
    expected_answer: str
    type: str = "rag"
    expected_sources: str = ""
    group_id: str | None = None
    dataset_id: str | None = None  # backward-compat alias


@router.post("/test-cases", status_code=201)
def create_test_case(body: CreateTestCase, request: Request) -> dict:
    """Create a single test case directly in the library (no xlsx upload needed)."""
    store = request.app.state.store
    effective_group = body.group_id or body.dataset_id
    if effective_group:
        groups = store.list_groups()
        if not any(g["group_id"] == effective_group for g in groups):
            raise HTTPException(404, f"Group {effective_group!r} not found in library")
    return store.create_test_case(
        chat_id=body.chat_id,
        turn_no=body.turn_no,
        question=body.question,
        expected_answer=body.expected_answer,
        type=body.type,
        expected_sources=body.expected_sources,
        group_id=effective_group,
    )
