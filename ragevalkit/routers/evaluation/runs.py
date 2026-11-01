"""Starting, watching, stopping and managing evaluation runs."""
import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from ragevalkit.core.config import Config
from ragevalkit.core.exceptions.data_access import ConflictError
from ragevalkit.data_access.store import EvalStore
from ragevalkit.routers.dependencies import get_config, get_run_manager, get_store, require_user
from ragevalkit.schemas.evaluation.requests import SelectionBody
from ragevalkit.schemas.evaluation.responses import (
    RunArchiveState,
    RunDeleted,
    RunIssues,
    RunPreview,
    RunSnapshot,
    StopRequested,
    VersionSummary,
)
from ragevalkit.services.evaluation_runner.run_control import get_run, request_stop, run_issues
from ragevalkit.services.evaluation_runner.run_planning import (
    check_version_name,
    parse_id_list,
    plan_run,
    selection_preview,
)
from ragevalkit.services.evaluation_runner.runner import RunManager
from ragevalkit.utils.ensure_found import ensure_found

router = APIRouter(prefix="/api/runs", tags=["runs"], dependencies=[Depends(require_user)])

STREAM_POLL_SECONDS = 0.3      # how often a watching browser is sent new progress


@router.post("/preview")
def preview_run(body: SelectionBody, store: EvalStore = Depends(get_store)) -> RunPreview:
    """Dry run: what would a run with this selection execute? Powers the live count in the Execute dialog.

    Nothing is started or saved. Test cases carried by ``group_ids`` are filtered by ``status_filter``
    (``active``, ``inactive`` or ``all``); cases named in ``tc_ids`` are always included. With
    ``include_context`` the earlier turns of each selected chat are added so a conversation can be replayed.

    Answers 404 when a group does not exist and 422 when ``status_filter`` is not one of the three values.
    """
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
) -> RunSnapshot:
    """Start an evaluation run in the background and return its first snapshot (answers 202).

    The test cases come from the first source that applies: library groups and/or individual test cases
    (``group_ids`` and ``tc_ids``, or the older single ``group_id`` / ``dataset_id``), an uploaded
    spreadsheet (``file``), or the default dataset the server was started with. A library selection works
    as in ``POST /api/runs/preview``. Only one run can be going at a time.

    Args:
        version: Name for the new version: up to 20 letters, digits, ``.``, ``_`` or ``-``.
        overwrite: Replace an existing version of the same name when the new run finishes.
        file: Spreadsheet of test cases. Ignored when a library selection is given.
        save_as_group: Keep the uploaded ``file`` in the library as a new group called ``group_name``,
            instead of using it for this run only.
        status_filter: Which test cases of the selected groups run: ``active``, ``inactive`` or ``all``.
        notes: Free text saved with the version.

    Returns:
        The run as it stands at the start. Use its ``run_id`` to follow it with ``GET /api/runs/{run_id}/stream``
        or to stop it with ``POST /api/runs/{run_id}/stop``.

    Error answers:
        400 when there is nothing to run (no selection, no file and no default dataset);
        404 when a group does not exist or the selection holds no runnable test cases;
        409 when the version already exists and ``overwrite`` is false, when another run is in progress,
        when two different selected test cases share a chat and turn, or when ``group_name`` is taken;
        422 for an invalid version name, ``status_filter`` or spreadsheet.
    """
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
def list_runs(store: EvalStore = Depends(get_store)) -> list[VersionSummary]:
    """List the saved runs that are not archived, oldest first.

    A run is saved when it finishes or is stopped, so one still in progress (or one that failed outright)
    is not listed. ``GET /api/versions`` lists every saved run, archived ones included.
    """
    return store.list_runs(include_archived=False)


@router.get("/{run_id}/issues")
def get_run_issues(run_id: str, manager: RunManager = Depends(get_run_manager)) -> RunIssues:
    """What went wrong during this run so far, in plain language, each with its technical detail.

    ``run_id`` is the id returned when the run was started. Only runs started since the server came up are
    known; any other id answers 404.
    """
    return run_issues(manager, run_id)


@router.post("/{run_id}/stop", status_code=202)
def stop_run(run_id: str, manager: RunManager = Depends(get_run_manager)) -> StopRequested:
    """Request an early stop for a running eval. Partial results are saved.

    The run finishes the question it is on and is then saved as a stopped version, which is never
    compared or recommended as a finished run. Answers 202 once the request is noted, 404 for an unknown
    ``run_id`` and 409 when the run is no longer running.
    """
    return request_stop(manager, run_id)


@router.delete("/{run_id}", status_code=200)
def delete_run(run_id: str, store: EvalStore = Depends(get_store)) -> RunDeleted:
    """Delete a saved run and its per-question results.

    Here ``run_id`` is the version name (for example ``v1``), not the id returned by ``POST /api/runs``.
    Answers 404 when no such saved run exists.
    """
    ensure_found(store.delete_run(run_id), "Run not found")
    return {"run_id": run_id, "deleted": True}


@router.patch("/{run_id}/archive", status_code=200)
def archive_run(run_id: str, store: EvalStore = Depends(get_store)) -> RunArchiveState:
    """Archive a run so it is hidden from the default dashboard listing.

    An archived run is left out of ``GET /api/runs``, of recommendations and of group history, but stays in
    ``GET /api/versions`` and can be restored. ``run_id`` is the version name. Answers 404 for an unknown run.
    """
    ensure_found(store.archive_run(run_id), "Run not found")
    return {"run_id": run_id, "archived": True}


@router.patch("/{run_id}/unarchive", status_code=200)
def unarchive_run(run_id: str, store: EvalStore = Depends(get_store)) -> RunArchiveState:
    """Restore an archived run to the default dashboard listing.

    ``run_id`` is the version name. Answers 404 for an unknown run.
    """
    ensure_found(store.unarchive_run(run_id), "Run not found")
    return {"run_id": run_id, "archived": False}


@router.get("/{run_id}/stream")
async def stream_run(
    run_id: str, request: Request, manager: RunManager = Depends(get_run_manager),
) -> StreamingResponse:
    """Follow a run's progress live, as server-sent events, until it ends.

    Each event is a JSON object with a ``type`` (``started``, ``progress``, ``done``, ``stopped`` or
    ``error``) and the run's current snapshot (see ``POST /api/runs``). A ``progress`` event also carries the
    question just finished as ``row``, and ``done`` carries the saved ``summary``. Events already sent are
    replayed first, so connecting late loses nothing. The stream closes when the run is over or the client
    disconnects. ``run_id`` is the id returned when the run was started; an unknown one answers 404.
    """
    run = get_run(manager, run_id)

    async def events() -> AsyncIterator[str]:
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
