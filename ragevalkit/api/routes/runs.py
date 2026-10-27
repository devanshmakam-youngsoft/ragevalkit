"""Starting, watching, stopping and managing evaluation runs."""
import asyncio
import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from ragevalkit.api.dependencies import get_config, get_run_manager, get_store, require_user
from ragevalkit.api.schemas import SelectionBody
from ragevalkit.api.services.lookups import ensure_found
from ragevalkit.api.services.run_requests import (
    check_version_name,
    parse_id_list,
    plan_run,
    selection_preview,
)
from ragevalkit.api.services.runs import get_run, request_stop
from ragevalkit.config import Config
from ragevalkit.evaluation.runner import RunManager
from ragevalkit.storage.exceptions import ConflictError
from ragevalkit.storage.store import EvalStore

router = APIRouter(prefix="/api/runs", tags=["runs"], dependencies=[Depends(require_user)])

STREAM_POLL_SECONDS = 0.3      # how often a watching browser is sent new progress


@router.post("/preview")
def preview_run(body: SelectionBody, store: EvalStore = Depends(get_store)) -> dict:
    """Dry run: what would a run with this selection execute? Powers the live count in the Execute dialog."""
    selection = store.resolve_selection(body.group_ids, body.tc_ids, status=body.status_filter, include_context=body.include_context)
    return selection_preview(selection)


@router.post("", status_code=202)
async def start_run(
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
    cfg: Config = Depends(get_config),
    store: EvalStore = Depends(get_store),
    manager: RunManager = Depends(get_run_manager),
) -> dict:
    version = check_version_name(version)
    if store.exists(version) and not overwrite:
        raise ConflictError(f"Version {version} already exists")
    uploaded = file is not None and bool(file.filename)
    plan = plan_run(
        cfg, store, version=version,
        group_ids=parse_id_list(group_ids) or ([group_id] if group_id else []) or ([dataset_id] if dataset_id else []),
        picked=parse_id_list(tc_ids), status=status_filter, include_context=include_context,
        upload_name=file.filename if uploaded else None, upload_data=await file.read() if uploaded else None,
        save_as_group=save_as_group, group_name=group_name,
    )
    run = manager.start(
        version, plan.df, plan.dataset_name, notes=notes, group_names=plan.group_names,
        from_library=plan.from_library, dataset_id=plan.source_dataset_id,
    )
    return run.snapshot()


@router.get("")
def list_runs(store: EvalStore = Depends(get_store)) -> list[dict]:
    return store.list_runs(include_archived=False)


@router.post("/{run_id}/stop", status_code=202)
def stop_run(run_id: str, manager: RunManager = Depends(get_run_manager)) -> dict:
    """Request an early stop for a running eval. Partial results are saved."""
    return request_stop(manager, run_id)


@router.delete("/{run_id}", status_code=200)
def delete_run(run_id: str, store: EvalStore = Depends(get_store)) -> dict:
    """Delete a completed run and all its receipts from the store."""
    ensure_found(store.delete_run(run_id), "Run not found")
    return {"run_id": run_id, "deleted": True}


@router.patch("/{run_id}/archive", status_code=200)
def archive_run(run_id: str, store: EvalStore = Depends(get_store)) -> dict:
    """Archive a run so it is hidden from the default dashboard listing."""
    ensure_found(store.archive_run(run_id), "Run not found")
    return {"run_id": run_id, "archived": True}


@router.patch("/{run_id}/unarchive", status_code=200)
def unarchive_run(run_id: str, store: EvalStore = Depends(get_store)) -> dict:
    """Restore an archived run to the default dashboard listing."""
    ensure_found(store.unarchive_run(run_id), "Run not found")
    return {"run_id": run_id, "archived": False}


@router.get("/{run_id}/stream")
async def stream_run(run_id: str, request: Request, manager: RunManager = Depends(get_run_manager)):
    run = get_run(manager, run_id)

    async def events():
        sent = 0
        while True:
            while sent < len(run.events):
                yield f"data: {json.dumps(run.events[sent], default=str)}\n\n"
                sent += 1
            if run.status not in ("running",) and sent >= len(run.events):
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(STREAM_POLL_SECONDS)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
