"""Groups: labels put on test cases."""
from fastapi import APIRouter, Depends, File, UploadFile

from ragevalkit.core.config import Config
from ragevalkit.routers.dependencies import get_config, get_store, require_user
from ragevalkit.schemas.testcase_library import (
    Group,
    GroupDeleted,
    GroupHistory,
    GroupImported,
    GroupName,
    GroupPurged,
    GroupRestored,
    GroupWithHistory,
    LibraryTestCase,
    MemberAdded,
    MemberRemoved,
    MembersAdded,
    MembersRemoved,
    TestCaseIds,
)
from ragevalkit.services.db_services import EvalStore
from ragevalkit.services.evaluation.version_recommender import groups_with_history, history_of_group
from ragevalkit.services.testcases.testcase_library import get_group, import_file_into_group
from ragevalkit.utils import ensure_found

router = APIRouter(prefix="/api/groups", tags=["groups"], dependencies=[Depends(require_user)])


@router.get("")
def list_groups(include_deleted: bool = False, cfg: Config = Depends(get_config), store: EvalStore = Depends(get_store)) -> list[GroupWithHistory]:
    """List groups, each with its test case count and how it has done: last run and best version so far.
    Deleted groups are only included on request (``include_deleted=true``) and carry ``deleted_at``."""
    return groups_with_history(cfg, store, include_deleted)


@router.post("", status_code=201)
def create_group(body: GroupName, store: EvalStore = Depends(get_store)) -> Group:
    """Create an empty group to label test cases with.

    Answers 409 when another group already has the name (capitals and surrounding spaces do not count) and
    422 when the name is empty.
    """
    return get_group(store, store.create_group(body.name))


@router.get("/{group_id}/runs")
def group_runs(group_id: str, cfg: Config = Depends(get_config), store: EvalStore = Depends(get_store)) -> GroupHistory:
    """One group's history across non-archived runs (newest first), its last run and its best version.

    Answers 404 when the group does not exist.
    """
    return history_of_group(cfg, store, group_id)


@router.patch("/{group_id}")
def rename_group(group_id: str, body: GroupName, store: EvalStore = Depends(get_store)) -> Group:
    """Rename a group; past runs follow the new name, so group history and filters keep working.

    Answers 404 when the group does not exist, 409 when another group already has the name and 422 when
    the name is empty.
    """
    ensure_found(store.rename_group(group_id, body.name), "Group not found")
    return get_group(store, group_id)


@router.post("/{group_id}/members", status_code=200)
def add_many_to_group(group_id: str, body: TestCaseIds, store: EvalStore = Depends(get_store)) -> MembersAdded:
    """Label several test cases with this group.

    ``added`` counts only the labels that are new: unknown test case ids and ones already in the group are
    skipped. Answers 404 when the group does not exist.
    """
    return {"group_id": group_id, "added": store.add_tcs_to_group(group_id, body.tc_ids)}


@router.post("/{group_id}/members/remove", status_code=200)
def remove_many_from_group(group_id: str, body: TestCaseIds, store: EvalStore = Depends(get_store)) -> MembersRemoved:
    """Remove this group's label from several test cases.

    ``removed`` counts the labels actually removed; test cases that did not carry the label are skipped.
    The test cases themselves are kept.
    """
    return {"group_id": group_id, "removed": store.remove_tcs_from_group(group_id, body.tc_ids)}


@router.post("/{group_id}/members/{tc_id}", status_code=201)
def add_to_group(group_id: str, tc_id: str, store: EvalStore = Depends(get_store)) -> MemberAdded:
    """Label one test case with this group.

    ``added`` is false when the test case is unknown or already in the group. Answers 404 when the group
    does not exist.
    """
    return {"group_id": group_id, "tc_id": tc_id, "added": store.add_tc_to_group(group_id, tc_id)}


@router.delete("/{group_id}/members/{tc_id}", status_code=200)
def remove_from_group(group_id: str, tc_id: str, store: EvalStore = Depends(get_store)) -> MemberRemoved:
    """Remove this group's label from one test case, which is kept.

    Answers 404 when the test case does not carry the label.
    """
    ensure_found(store.remove_tc_from_group(group_id, tc_id), "Member not found")
    return {"group_id": group_id, "tc_id": tc_id}


@router.post("/{group_id}/import", status_code=201)
async def import_into_group(
    group_id: str, file: UploadFile = File(...), cfg: Config = Depends(get_config), store: EvalStore = Depends(get_store),
) -> GroupImported:
    """Add the test cases of an uploaded spreadsheet to this group.

    Rows are created or updated in the library as with a bulk import, and labelled with the group;
    ``linked`` is the number of labels added. Answers 404 when the group does not exist and 422 when the
    file cannot be read or is missing required columns.
    """
    return import_file_into_group(cfg, store, group_id, await file.read())


@router.get("/{group_id}/test-cases")
def group_test_cases(group_id: str, status: str | None = None, store: EvalStore = Depends(get_store)) -> list[LibraryTestCase]:
    """List the test cases carrying this group's label, newest version of each.

    ``status`` (``active`` or ``inactive``) keeps only cases in that state. An unknown group, or one with no
    test cases, gives an empty list.
    """
    return store.get_group_test_cases(group_id, status=status)


@router.delete("/{group_id}", status_code=200)
def delete_group(group_id: str, store: EvalStore = Depends(get_store)) -> GroupDeleted:
    """Delete a group. It is hidden but kept (with its labels), so past runs stay readable and it can be
    restored. Test cases are not touched.

    Answers 404 when the group does not exist or is already deleted.
    """
    ensure_found(store.delete_group(group_id), "Group not found")
    return {"group_id": group_id, "deleted": True}


@router.post("/{group_id}/restore", status_code=200)
def restore_group(group_id: str, store: EvalStore = Depends(get_store)) -> GroupRestored:
    """Bring a deleted group back with its labels.

    Answers 404 when there is no such deleted group and 409 when another group has taken its name since;
    rename that one first.
    """
    ensure_found(store.restore_group(group_id), "Deleted group not found")
    return {"group_id": group_id, "restored": True}


@router.post("/{group_id}/purge", status_code=200)
def purge_group(group_id: str, store: EvalStore = Depends(get_store)) -> GroupPurged:
    """Permanently remove a group that is already deleted. Past runs keep its name and scores.

    This cannot be undone. Answers 404 when there is no such deleted group.
    """
    ensure_found(store.purge_group(group_id), "Deleted group not found")
    return {"group_id": group_id, "purged": True}
