"""Groups: labels put on test cases."""
from fastapi import APIRouter, Depends, File, UploadFile

from ragevalkit.api.dependencies import get_config, get_store, require_user
from ragevalkit.api.schemas import GroupName, TestCaseIds
from ragevalkit.api.services.groups import get_group, import_file_into_group
from ragevalkit.api.services.lookups import ensure_found
from ragevalkit.api.services.recommendations import groups_with_history, history_of_group
from ragevalkit.config import Config
from ragevalkit.storage.store import EvalStore

router = APIRouter(prefix="/api/groups", tags=["groups"], dependencies=[Depends(require_user)])


@router.get("")
def list_groups(include_deleted: bool = False, cfg: Config = Depends(get_config), store: EvalStore = Depends(get_store)) -> list[dict]:
    """List groups, each with its test case count and how it has done: last run and best version so far.
    Deleted groups are only included on request (``include_deleted=true``) and carry ``deleted_at``."""
    return groups_with_history(cfg, store, include_deleted)


@router.post("", status_code=201)
def create_group(body: GroupName, store: EvalStore = Depends(get_store)) -> dict:
    return get_group(store, store.create_group(body.name))


@router.get("/{group_id}/runs")
def group_runs(group_id: str, cfg: Config = Depends(get_config), store: EvalStore = Depends(get_store)) -> dict:
    """One group's history across non-archived runs (newest first), its last run and its best version."""
    return history_of_group(cfg, store, group_id)


@router.patch("/{group_id}")
def rename_group(group_id: str, body: GroupName, store: EvalStore = Depends(get_store)) -> dict:
    ensure_found(store.rename_group(group_id, body.name), "Group not found")
    return get_group(store, group_id)


@router.post("/{group_id}/members", status_code=200)
def add_many_to_group(group_id: str, body: TestCaseIds, store: EvalStore = Depends(get_store)) -> dict:
    """Label several test cases with this group."""
    return {"group_id": group_id, "added": store.add_tcs_to_group(group_id, body.tc_ids)}


@router.post("/{group_id}/members/remove", status_code=200)
def remove_many_from_group(group_id: str, body: TestCaseIds, store: EvalStore = Depends(get_store)) -> dict:
    """Remove this group's label from several test cases."""
    return {"group_id": group_id, "removed": store.remove_tcs_from_group(group_id, body.tc_ids)}


@router.post("/{group_id}/members/{tc_id}", status_code=201)
def add_to_group(group_id: str, tc_id: str, store: EvalStore = Depends(get_store)) -> dict:
    return {"group_id": group_id, "tc_id": tc_id, "added": store.add_tc_to_group(group_id, tc_id)}


@router.delete("/{group_id}/members/{tc_id}", status_code=200)
def remove_from_group(group_id: str, tc_id: str, store: EvalStore = Depends(get_store)) -> dict:
    ensure_found(store.remove_tc_from_group(group_id, tc_id), "Member not found")
    return {"group_id": group_id, "tc_id": tc_id}


@router.post("/{group_id}/import", status_code=201)
async def import_into_group(
    group_id: str, file: UploadFile = File(...), cfg: Config = Depends(get_config), store: EvalStore = Depends(get_store),
) -> dict:
    return import_file_into_group(cfg, store, group_id, await file.read())


@router.get("/{group_id}/test-cases")
def group_test_cases(group_id: str, status: str | None = None, store: EvalStore = Depends(get_store)) -> list[dict]:
    return store.get_group_test_cases(group_id, status=status)


@router.delete("/{group_id}", status_code=200)
def delete_group(group_id: str, store: EvalStore = Depends(get_store)) -> dict:
    """Delete a group. It is hidden but kept (with its labels), so past runs stay readable and it can be
    restored. Test cases are not touched."""
    ensure_found(store.delete_group(group_id), "Group not found")
    return {"group_id": group_id, "deleted": True}


@router.post("/{group_id}/restore", status_code=200)
def restore_group(group_id: str, store: EvalStore = Depends(get_store)) -> dict:
    """Bring a deleted group back with its labels."""
    ensure_found(store.restore_group(group_id), "Deleted group not found")
    return {"group_id": group_id, "restored": True}


@router.post("/{group_id}/purge", status_code=200)
def purge_group(group_id: str, store: EvalStore = Depends(get_store)) -> dict:
    """Permanently remove a group that is already deleted. Past runs keep its name and scores."""
    ensure_found(store.purge_group(group_id), "Deleted group not found")
    return {"group_id": group_id, "purged": True}
