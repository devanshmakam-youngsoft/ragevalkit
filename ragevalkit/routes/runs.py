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
from ragevalkit.exceptions import ConflictError, GroupNotFound
from ragevalkit.recommend import group_overview, recommend
from ragevalkit.runner import RunBusy
from ragevalkit.store import RunSelection, VersionNotFound, valid_version



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

def _json_list(raw: str | None) -> list[str]:
    """A list of ids sent as a JSON array (or, leniently, comma-separated) in a form field."""
    if not raw:
        return []
    try:
        val = json.loads(raw)
        if isinstance(val, list):
            return [str(v) for v in val]
    except ValueError:
        pass
    return [part.strip() for part in raw.split(",") if part.strip()]


def _resolve(store, group_ids: list[str], tc_ids: list[str], status: str, include_context: bool) -> RunSelection:
    """Resolve a selection or raise the matching HTTP error."""
    try:
        return store.resolve_selection(group_ids, tc_ids, status=status, include_context=include_context)
    except GroupNotFound as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


def _collision_message(collisions: list[dict]) -> str:
    first = collisions[0]
    more = f" (and {len(collisions) - 1} more)" if len(collisions) > 1 else ""
    return (
        f"Chat {first['chat_id']!r} turn {first['turn_no']} is used by {len(first['tc_ids'])} different "
        f"test cases in this selection{more}. Deselect one or change its chat / turn number."
    )


class SelectionBody(BaseModel):
    group_ids: list[str] = []
    tc_ids: list[str] = []
    status_filter: str = "active"
    include_context: bool = True


@router.post("/runs/preview")
def preview_run(body: SelectionBody, request: Request) -> dict:
    """Dry run: what would a run with this selection execute? Powers the live count in the Execute dialog."""
    sel = _resolve(request.app.state.store, body.group_ids, body.tc_ids, body.status_filter, body.include_context)
    return {
        "selected": sel.selected,
        "context": sel.context,
        "total": sel.total,
        "missing": sel.missing,
        "group_names": sel.group_names,
        "collisions": sel.collisions,
    }


@router.post("/runs", status_code=202)
async def start_run(
    request: Request,
    version: str = Form(...),
    overwrite: bool = Form(False),
    file: UploadFile | None = File(None),
    group_id: str | None = Form(None),
    group_ids: str | None = Form(None),  # JSON array of group IDs
    tc_ids: str | None = Form(None),     # JSON array of individual test case IDs
    include_context: bool = Form(True),  # add earlier turns of each selected chat
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

    # Library selection: groups and/or individually picked test cases (union).
    selected_groups = _json_list(group_ids) or ([group_id] if group_id else []) or ([dataset_id] if dataset_id else [])
    picked = _json_list(tc_ids)

    run_group_names: list[str] = []
    from_library = False
    source_dataset_id = ""

    if selected_groups or picked:
        sel = _resolve(store, selected_groups, picked, status_filter, include_context)
        if sel.collisions:
            raise HTTPException(409, _collision_message(sel.collisions))
        if sel.df.empty:
            raise HTTPException(404, "No runnable test cases in the selection")
        df, from_library = sel.df, True
        run_group_names = sel.group_names
        label = list(sel.group_names)
        if picked:
            n = len(picked)
            label.append(f"{n} picked test case{'s' if n != 1 else ''}")
        dataset_name = " + ".join(label)
        if len(selected_groups) == 1 and not picked:
            source_dataset_id = selected_groups[0]
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
        try:
            new_group_id = store.create_group(group_name)
        except ConflictError as e:
            raise HTTPException(409, str(e))
        store.import_into_group(new_group_id, df)
        sel = _resolve(store, [new_group_id], [], status_filter, False)
        df, from_library, source_dataset_id = sel.df, True, new_group_id
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
        run = manager.start(
            version, df, dataset_name, notes=notes, group_names=run_group_names,
            from_library=from_library, dataset_id=source_dataset_id,
        )
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


def _reco_settings(cfg, tolerance: float | None = None, max_time: float | None = None) -> dict:
    """Weights, tolerance and time ceiling from serve(), overridable per request."""
    return {
        "answer_weight": cfg.answer_weight,
        "material_weight": cfg.material_weight,
        "tolerance": cfg.recommendation_tolerance if tolerance is None else tolerance,
        "max_time": cfg.max_response_time if max_time is None else (max_time if max_time > 0 else None),
    }


@router.get("/recommendation")
def get_recommendation(
    request: Request,
    group: str | None = None,
    tolerance: float | None = None,
    max_time: float | None = None,
) -> dict:
    """Which version to ship, computed now from the saved scores of every non-archived run.

    ``group`` limits the comparison to one group's scores. ``tolerance`` and ``max_time`` override
    the ``serve()`` defaults for this request only.
    """
    if tolerance is not None and tolerance < 0:
        raise HTTPException(422, "tolerance must be 0 or higher")
    cfg, store = request.app.state.config, request.app.state.store
    return recommend(store.list_versions_for_comparison(), group=group, **_reco_settings(cfg, tolerance, max_time))


# ---------------------------------------------------------------------------
# Test case management endpoints
# ---------------------------------------------------------------------------

class TestCaseUpdate(BaseModel):
    chat_id: str | None = None
    turn_no: int | None = None
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
    try:
        result = request.app.state.store.edit_test_case(tc_id, body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(422, str(e))
    if result is None:
        raise HTTPException(404, "Test case not found or no valid fields provided")
    return result


class BulkStatusUpdate(BaseModel):
    tc_ids: list[str]
    status: str  # "active" | "inactive" | "deleted"


@router.post("/test-cases/status")
def set_test_cases_status(body: BulkStatusUpdate, request: Request) -> dict:
    """Activate, deactivate or delete (hide, keeping the data) several test cases at once.
    Setting a deleted case back to 'active' restores it."""
    if body.status not in ("active", "inactive", "deleted"):
        raise HTTPException(422, f"Invalid status '{body.status}'")
    updated = request.app.state.store.update_status_bulk(body.tc_ids, body.status)
    return {"updated": updated, "status": body.status}


class TcIdList(BaseModel):
    tc_ids: list[str]


@router.post("/test-cases/purge")
def purge_test_cases(body: TcIdList, request: Request) -> dict:
    """Permanently remove test cases that are already deleted (all versions and group labels).
    Past run results are kept. Cases that are not deleted are ignored."""
    return {"purged": request.app.state.store.purge_deleted_test_cases(body.tc_ids)}


class TestCaseGroups(BaseModel):
    group_ids: list[str]


@router.put("/test-cases/{tc_id}/groups")
def set_test_case_groups(tc_id: str, body: TestCaseGroups, request: Request) -> dict:
    """Replace the group labels on one test case."""
    try:
        ok = request.app.state.store.set_test_case_groups(tc_id, body.group_ids)
    except GroupNotFound as e:
        raise HTTPException(404, str(e))
    if not ok:
        raise HTTPException(404, "Test case not found")
    return {"tc_id": tc_id, "group_ids": body.group_ids}


@router.patch("/test-cases/{tc_id}/status")
def set_test_case_status(tc_id: str, body: TestCaseStatusUpdate, request: Request) -> dict:
    """Activate, deactivate or delete (hide) a test case."""
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
def list_groups(request: Request, include_deleted: bool = False) -> list[dict]:
    """List groups, each with its test case count and how it has done: last run and best version so far.
    Deleted groups are only included on request (``include_deleted=true``) and carry ``deleted_at``."""
    cfg, store = request.app.state.config, request.app.state.store
    versions = store.list_versions_for_comparison()
    out = []
    for g in store.list_groups(include_deleted=include_deleted):
        overview = group_overview(versions, g["name"], **_reco_settings(cfg))
        out.append({
            **g,
            "run_count": overview["run_count"],
            "last_run": overview["last"],
            "best_run": overview["best"],
        })
    return out


@router.get("/groups/{group_id}/runs")
def group_runs(group_id: str, request: Request) -> dict:
    """One group's history across non-archived runs (newest first), its last run and its best version."""
    cfg, store = request.app.state.config, request.app.state.store
    group = next((g for g in store.list_groups() if g["group_id"] == group_id), None)
    if group is None:
        raise HTTPException(404, "Group not found")
    return {"group": group, **group_overview(store.list_versions_for_comparison(), group["name"], **_reco_settings(cfg))}


@router.post("/groups", status_code=201)
def create_group(body: CreateGroup, request: Request) -> dict:
    store = request.app.state.store
    try:
        gid = store.create_group(body.name)
    except ConflictError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    groups = store.list_groups()
    return next(g for g in groups if g["group_id"] == gid)


@router.patch("/groups/{group_id}")
def rename_group(group_id: str, body: CreateGroup, request: Request) -> dict:
    store = request.app.state.store
    try:
        ok = store.rename_group(group_id, body.name)
    except ConflictError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not ok:
        raise HTTPException(404, "Group not found")
    return next(g for g in store.list_groups() if g["group_id"] == group_id)


class TcIds(BaseModel):
    tc_ids: list[str]


@router.post("/groups/{group_id}/members", status_code=200)
def add_many_to_group(group_id: str, body: TcIds, request: Request) -> dict:
    """Label several test cases with this group."""
    try:
        added = request.app.state.store.add_tcs_to_group(group_id, body.tc_ids)
    except GroupNotFound as e:
        raise HTTPException(404, str(e))
    return {"group_id": group_id, "added": added}


@router.post("/groups/{group_id}/members/remove", status_code=200)
def remove_many_from_group(group_id: str, body: TcIds, request: Request) -> dict:
    """Remove this group's label from several test cases."""
    removed = request.app.state.store.remove_tcs_from_group(group_id, body.tc_ids)
    return {"group_id": group_id, "removed": removed}


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
    try:
        ok = request.app.state.store.add_tc_to_group(group_id, tc_id)
    except GroupNotFound as e:
        raise HTTPException(404, str(e))
    return {"group_id": group_id, "tc_id": tc_id, "added": ok}


@router.delete("/groups/{group_id}/members/{tc_id}", status_code=200)
def remove_from_group(group_id: str, tc_id: str, request: Request) -> dict:
    ok = request.app.state.store.remove_tc_from_group(group_id, tc_id)
    if not ok:
        raise HTTPException(404, "Member not found")
    return {"group_id": group_id, "tc_id": tc_id}


@router.delete("/groups/{group_id}", status_code=200)
def delete_group(group_id: str, request: Request) -> dict:
    """Delete a group. It is hidden but kept (with its labels), so past runs stay readable and it can be
    restored. Test cases are not touched."""
    ok = request.app.state.store.delete_group(group_id)
    if not ok:
        raise HTTPException(404, "Group not found")
    return {"group_id": group_id, "deleted": True}


@router.post("/groups/{group_id}/restore", status_code=200)
def restore_group(group_id: str, request: Request) -> dict:
    """Bring a deleted group back with its labels."""
    try:
        ok = request.app.state.store.restore_group(group_id)
    except ConflictError as e:
        raise HTTPException(409, str(e))
    if not ok:
        raise HTTPException(404, "Deleted group not found")
    return {"group_id": group_id, "restored": True}


@router.post("/groups/{group_id}/purge", status_code=200)
def purge_group(group_id: str, request: Request) -> dict:
    """Permanently remove a group that is already deleted. Past runs keep its name and scores."""
    if not request.app.state.store.purge_group(group_id):
        raise HTTPException(404, "Deleted group not found")
    return {"group_id": group_id, "purged": True}


@router.get("/datasets")
def list_datasets(request: Request) -> list[dict]:
    """Alias for /api/groups — backward compat."""
    return list_groups(request)


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
