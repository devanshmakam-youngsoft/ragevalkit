"""Test cases in the library: list, create, edit, activate, delete, and which groups they carry."""
from fastapi import APIRouter, Depends

from ragevalkit.api.dependencies import get_store, require_user
from ragevalkit.api.schemas import (
    BulkStatusUpdate,
    CreateTestCase,
    TestCaseGroups,
    TestCaseIds,
    TestCaseStatusUpdate,
    TestCaseUpdate,
)
from ragevalkit.api.services.lookups import ensure_found
from ragevalkit.api.services.test_case_library import create_test_case as create_library_test_case
from ragevalkit.api.services.test_case_library import find_test_case
from ragevalkit.exceptions import InvalidInput
from ragevalkit.storage.store import EvalStore

router = APIRouter(prefix="/api/test-cases", tags=["test cases"], dependencies=[Depends(require_user)])

ACTIVE_STATUSES = ("active", "inactive")


@router.get("")
def list_test_cases(
    group_id: str | None = None,
    dataset_id: str | None = None,
    status: str | None = None,
    store: EvalStore = Depends(get_store),
) -> list[dict]:
    """List test cases. Optionally filter by group_id/dataset_id or status (active/inactive)."""
    return store.list_test_cases(group_id=group_id, dataset_id=dataset_id, status=status)


@router.post("", status_code=201)
def create_test_case(body: CreateTestCase, store: EvalStore = Depends(get_store)) -> dict:
    """Create a single test case directly in the library (no xlsx upload needed)."""
    return create_library_test_case(store, body)


@router.post("/status")
def set_test_cases_status(body: BulkStatusUpdate, store: EvalStore = Depends(get_store)) -> dict:
    """Activate or deactivate several test cases at once (inactive cases do not run). To remove them use /test-cases/delete."""
    if body.status not in ACTIVE_STATUSES:
        raise InvalidInput(f"Invalid status '{body.status}'")
    return {"updated": store.update_status_bulk(body.tc_ids, body.status), "status": body.status}


@router.post("/delete")
def delete_test_cases(body: TestCaseIds, store: EvalStore = Depends(get_store)) -> dict:
    """Permanently delete test cases: every version and their group labels. Past run results keep their own
    copy of the question and answer, and show that the test case has since been deleted."""
    return {"deleted": store.delete_test_cases(body.tc_ids)}


@router.get("/{tc_id}")
def get_test_case(tc_id: str, store: EvalStore = Depends(get_store)) -> dict:
    """Get the latest version of a test case."""
    return find_test_case(store, tc_id)


@router.get("/{tc_id}/history")
def get_test_case_history(tc_id: str, store: EvalStore = Depends(get_store)) -> list[dict]:
    """Return all version records for a test case, oldest first."""
    return ensure_found(store.get_test_case_history(tc_id), "Test case not found")


@router.patch("/{tc_id}")
def update_test_case(tc_id: str, body: TestCaseUpdate, store: EvalStore = Depends(get_store)) -> dict:
    """Edit a test case: creates a new version record. Old versions are preserved."""
    return ensure_found(store.edit_test_case(tc_id, body.model_dump(exclude_none=True)), "Test case not found or no valid fields provided")


@router.put("/{tc_id}/groups")
def set_test_case_groups(tc_id: str, body: TestCaseGroups, store: EvalStore = Depends(get_store)) -> dict:
    """Replace the group labels on one test case."""
    ensure_found(store.set_test_case_groups(tc_id, body.group_ids), "Test case not found")
    return {"tc_id": tc_id, "group_ids": body.group_ids}


@router.patch("/{tc_id}/status")
def set_test_case_status(tc_id: str, body: TestCaseStatusUpdate, store: EvalStore = Depends(get_store)) -> dict:
    """Activate or deactivate a test case."""
    ensure_found(store.update_test_case_status(tc_id, body.status), f"Test case not found or invalid status '{body.status}'")
    return {"tc_id": tc_id, "status": body.status}
