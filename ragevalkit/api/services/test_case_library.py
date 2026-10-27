"""Single test cases in the library."""
from ragevalkit.api.schemas.test_cases import CreateTestCase
from ragevalkit.exceptions import NotFoundError
from ragevalkit.storage.store import EvalStore


def find_test_case(store: EvalStore, tc_id: str) -> dict:
    match = next((c for c in store.list_test_cases() if c["tc_id"] == tc_id), None)
    if match is None:
        raise NotFoundError("Test case not found")
    return match


def create_test_case(store: EvalStore, body: CreateTestCase) -> dict:
    """Add one test case straight to the library, and to a group if one is named."""
    group_id = body.group_id or body.dataset_id
    if group_id and not any(g["group_id"] == group_id for g in store.list_groups()):
        raise NotFoundError(f"Group {group_id!r} not found in library")
    return store.create_test_case(
        chat_id=body.chat_id, turn_no=body.turn_no, question=body.question, expected_answer=body.expected_answer,
        type=body.type, expected_sources=body.expected_sources, group_id=group_id,
    )
