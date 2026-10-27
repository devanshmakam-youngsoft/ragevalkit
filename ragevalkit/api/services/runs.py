"""Looking up and controlling runs that are going on."""
from ragevalkit.evaluation.exceptions import RunBusy
from ragevalkit.evaluation.run import Run
from ragevalkit.evaluation.runner import RunManager
from ragevalkit.exceptions import NotFoundError


def get_run(manager: RunManager, run_id: str) -> Run:
    run = manager.runs.get(run_id)
    if run is None:
        raise NotFoundError("Run not found")
    return run


def run_issues(manager: RunManager, run_id: str) -> dict:
    """The problems a run has met so far, in plain language. Each carries its technical detail for whoever asks."""
    run = get_run(manager, run_id)
    return {
        "issues": run.log.issue_dicts() if run.log else [],
        "issue_total": run.log.issue_total if run.log else 0,
        "error": run.error,
        "error_detail": run.error_detail,
    }


def request_stop(manager: RunManager, run_id: str) -> dict:
    """Ask a running evaluation to stop after the question it is on; partial results are saved."""
    run = get_run(manager, run_id)
    if run.status != "running":
        raise RunBusy(f"Run is not running (status: {run.status})")
    run.stop_requested = True
    return {"run_id": run_id, "message": "Stop requested — run will finish current row and save partial results."}
