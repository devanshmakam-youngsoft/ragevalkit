"""Test cases in the library: list, create, edit, activate, delete, and which groups they carry."""
from fastapi import APIRouter, Depends

from ragevalkit.core.exceptions import InvalidInput
from ragevalkit.routers.dependencies import get_store, require_user
from ragevalkit.schemas.testcase_library import (
    BulkStatusUpdate,
    CreateTestCase,
    DeletedTestCases,
    GroupsOfTestCase,
    LibraryTestCase,
    StatusesUpdated,
    StatusOfTestCase,
    TestCaseGroups,
    TestCaseIds,
    TestCaseStatusUpdate,
    TestCaseUpdate,
)
from ragevalkit.services.db_services import EvalStore
from ragevalkit.services.testcase_library import create_test_case as create_library_test_case
from ragevalkit.services.testcase_library import find_test_case
from ragevalkit.utils import ensure_found

router = APIRouter(prefix="/api/test-cases", tags=["test cases"], dependencies=[Depends(require_user)])

ACTIVE_STATUSES = ("active", "inactive")


@router.get("")
def list_test_cases(
    group_id: str | None = None,
    dataset_id: str | None = None,
    status: str | None = None,
    store: EvalStore = Depends(get_store),
) -> list[LibraryTestCase]:
    """List test cases, the latest version of each with the groups it carries.

    Optionally filter by ``group_id`` (``dataset_id`` is the older name for the same filter) or by ``status``
    (``active`` or ``inactive``).
    """
    return store.list_test_cases(group_id=group_id, dataset_id=dataset_id, status=status)


@router.post("", status_code=201)
def create_test_case(body: CreateTestCase, store: EvalStore = Depends(get_store)) -> LibraryTestCase:
    """Create a single test case directly in the library (no xlsx upload needed).

    The case starts ``active``. Its id comes from the chat, turn and question, so creating the same one again
    saves a new version instead of a duplicate. ``group_id`` (or the older ``dataset_id``) also puts it in
    that group. Answers 404 when that group does not exist.
    """
    return create_library_test_case(store, body)


@router.post("/status")
def set_test_cases_status(body: BulkStatusUpdate, store: EvalStore = Depends(get_store)) -> StatusesUpdated:
    """Activate or deactivate several test cases at once (inactive cases do not run).

    To remove them use ``POST /api/test-cases/delete``. ``updated`` counts the test cases found; unknown ids
    are skipped. Answers 422 when ``status`` is not ``active`` or ``inactive``.
    """
    if body.status not in ACTIVE_STATUSES:
        raise InvalidInput(f"Invalid status '{body.status}'")
    return {"updated": store.update_status_bulk(body.tc_ids, body.status), "status": body.status}


@router.post("/delete")
def delete_test_cases(body: TestCaseIds, store: EvalStore = Depends(get_store)) -> DeletedTestCases:
    """Permanently delete test cases: every version and their group labels. Past run results keep their own
    copy of the question and answer, and show that the test case has since been deleted.

    This cannot be undone. ``deleted`` counts the test cases that existed; unknown ids are skipped.
    """
    return {"deleted": store.delete_test_cases(body.tc_ids)}


@router.get("/{tc_id}")
def get_test_case(tc_id: str, store: EvalStore = Depends(get_store)) -> LibraryTestCase:
    """Get the latest version of a test case. Answers 404 when it does not exist."""
    return find_test_case(store, tc_id)


@router.get("/{tc_id}/history")
def get_test_case_history(tc_id: str, store: EvalStore = Depends(get_store)) -> list[LibraryTestCase]:
    """Return all version records for a test case, oldest first. Answers 404 when it does not exist."""
    return ensure_found(store.get_test_case_history(tc_id), "Test case not found")


@router.patch("/{tc_id}")
def update_test_case(tc_id: str, body: TestCaseUpdate, store: EvalStore = Depends(get_store)) -> LibraryTestCase:
    """Edit a test case: creates a new version record. Old versions are preserved.

    Send only the fields to change (``chat_id``, ``turn_no``, ``question``, ``expected_answer``,
    ``expected_sources``, ``type``); the rest keep their values. The test case keeps its id, groups and status.
    Answers 404 when it does not exist or no field was sent, and 422 for an empty ``chat_id`` or ``question``
    or a ``turn_no`` below 1.
    """
    return ensure_found(store.edit_test_case(tc_id, body.model_dump(exclude_none=True)), "Test case not found or no valid fields provided")


@router.put("/{tc_id}/groups")
def set_test_case_groups(tc_id: str, body: TestCaseGroups, store: EvalStore = Depends(get_store)) -> GroupsOfTestCase:
    """Replace the group labels on one test case with exactly the groups listed.

    Answers 404 when the test case or a listed group does not exist.
    """
    ensure_found(store.set_test_case_groups(tc_id, body.group_ids), "Test case not found")
    return {"tc_id": tc_id, "group_ids": body.group_ids}


@router.patch("/{tc_id}/status")
def set_test_case_status(tc_id: str, body: TestCaseStatusUpdate, store: EvalStore = Depends(get_store)) -> StatusOfTestCase:
    """Activate or deactivate a test case (inactive cases do not run).

    Answers 404 when the test case does not exist, and also when ``status`` is not ``active`` or ``inactive``.
    """
    ensure_found(store.update_test_case_status(tc_id, body.status), f"Test case not found or invalid status '{body.status}'")
    return {"tc_id": tc_id, "status": body.status}
