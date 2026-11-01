"""What the test case, group, import and dataset endpoints return."""
from typing import Any

from ragevalkit.schemas.base import ApiResponse


class GroupRef(ApiResponse):
    group_id: str
    name: str


class LibraryTestCase(ApiResponse):
    """One test case (its latest version) with the groups it carries."""

    tc_id: str
    version: int | None = None
    chat_id: str | None = None
    turn_no: int | None = None
    question: str
    expected_answer: str | None = None
    expected_sources: str | None = None
    type: str | None = None
    status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    groups: list[GroupRef] | None = None


class StatusesUpdated(ApiResponse):
    updated: int
    status: str


class DeletedTestCases(ApiResponse):
    deleted: int


class GroupsOfTestCase(ApiResponse):
    tc_id: str
    group_ids: list[str]


class StatusOfTestCase(ApiResponse):
    tc_id: str
    status: str


class Group(ApiResponse):
    group_id: str
    name: str
    created_at: str | None = None
    member_count: int | None = None
    deleted_at: str | None = None


class GroupWithHistory(Group):
    """A group with how it has done: its last run and its best version so far."""

    run_count: int = 0
    last_run: dict[str, Any] | None = None
    best_run: dict[str, Any] | None = None


class GroupHistory(ApiResponse):
    group: Group
    run_count: int
    last: dict[str, Any] | None = None
    best: dict[str, Any] | None = None
    reason: str = ""
    basis_note: str = ""
    compared_cases: int | None = None
    runs: list[dict[str, Any]]


class MembersAdded(ApiResponse):
    group_id: str
    added: int


class MembersRemoved(ApiResponse):
    group_id: str
    removed: int


class MemberAdded(ApiResponse):
    group_id: str
    tc_id: str
    added: bool


class MemberRemoved(ApiResponse):
    group_id: str
    tc_id: str


class GroupImported(ApiResponse):
    group_id: str
    linked: int


class GroupDeleted(ApiResponse):
    group_id: str
    deleted: bool


class GroupRestored(ApiResponse):
    group_id: str
    restored: bool


class GroupPurged(ApiResponse):
    group_id: str
    purged: bool


class ImportCounts(ApiResponse):
    new: int
    update: int
    unchanged: int
    problem: int


class ImportPreview(ApiResponse):
    """What importing a file would do, without saving anything."""

    filename: str | None = None
    sheets: list[str] = []
    sheet: str | None = None
    columns: list[str] = []
    mapping: dict[str, str | None] = {}
    total_rows: int = 0
    counts: ImportCounts
    slot_conflicts: int = 0
    sample: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    group_names_in_file: list[str] = []
    new_group_names: list[str] = []


class ImportResult(ApiResponse):
    new: int
    updated: int
    unchanged: int
    slot_conflicts: int = 0
    labelled: int = 0
    groups_created: list[str] = []
    problems: int = 0
    problem_rows: list[dict[str, Any]] = []
    columns: list[str] = []


class DatasetInfo(ApiResponse):
    name: str | None = None
    rows: int
    chats: int
    required_columns: list[str] | None = None
    fingerprint: str | None = None


class DatasetUploaded(ApiResponse):
    dataset_id: str
    rows: int
