"""What the test case, group, import and dataset endpoints return."""
from typing import Any

from ragevalkit.schemas.base import ApiResponse


class GroupRef(ApiResponse):
    """A group a test case carries, by id and name."""

    group_id: str
    name: str


class LibraryTestCase(ApiResponse):
    """One test case (its latest version) with the groups it carries."""

    tc_id: str                        # stays the same through edits; made from the chat, turn and question when created
    version: int | None = None        # 1 when created, one higher with each edit
    chat_id: str | None = None        # the conversation the question belongs to
    turn_no: int | None = None        # position in the chat, starting at 1
    question: str
    expected_answer: str | None = None
    expected_sources: str | None = None  # files the answer should come from: "|" joins required files, "," alternatives
    type: str | None = None           # "rag" or "non-rag"
    status: str | None = None         # "active", or "inactive" (inactive cases do not run)
    created_at: str | None = None     # ISO 8601 UTC
    updated_at: str | None = None     # ISO 8601 UTC
    groups: list[GroupRef] | None = None  # absent from the records of a test case's history


class StatusesUpdated(ApiResponse):
    """The outcome of activating or deactivating several test cases."""

    updated: int                      # test cases found; unknown ids are skipped
    status: str


class DeletedTestCases(ApiResponse):
    """The outcome of deleting test cases."""

    deleted: int                      # test cases that existed; unknown ids are skipped


class GroupsOfTestCase(ApiResponse):
    """The groups one test case now carries."""

    tc_id: str
    group_ids: list[str]


class StatusOfTestCase(ApiResponse):
    """The status one test case now has."""

    tc_id: str
    status: str


class Group(ApiResponse):
    """A named label that can be put on test cases."""

    group_id: str
    name: str
    created_at: str | None = None     # ISO 8601 UTC
    member_count: int | None = None   # test cases carrying the label
    deleted_at: str | None = None     # set on a deleted group (it is kept so past runs stay readable); null otherwise


class GroupWithHistory(Group):
    """A group with how it has done: its last run and its best version so far."""

    run_count: int = 0                # non-archived runs that covered the group
    last_run: dict[str, Any] | None = None  # the newest of those runs: version, date, row counts, averages, quality
    best_run: dict[str, Any] | None = None  # the best version for this group, in the same shape; null if none qualifies


class GroupHistory(ApiResponse):
    """One group's history across runs: every run, the latest and the best."""

    group: Group
    run_count: int
    last: dict[str, Any] | None = None  # the newest run, as in ``runs``
    best: dict[str, Any] | None = None  # the recommended version for this group, as in ``runs``; null if none qualifies
    reason: str = ""                  # why ``best`` was chosen, or why there is none
    basis_note: str = ""              # why versions were compared on answer quality only, when they were
    compared_cases: int | None = None  # test cases the comparison rests on
    runs: list[dict[str, Any]]        # newest first: version, date, row counts, averages and quality for this group


class MembersAdded(ApiResponse):
    """The outcome of labelling several test cases with a group."""

    group_id: str
    added: int                        # labels newly added; unknown ids and cases already in the group are skipped


class MembersRemoved(ApiResponse):
    """The outcome of removing a group's label from several test cases."""

    group_id: str
    removed: int                      # labels actually removed


class MemberAdded(ApiResponse):
    """The outcome of labelling one test case with a group."""

    group_id: str
    tc_id: str
    added: bool                       # false when the test case is unknown or already in the group


class MemberRemoved(ApiResponse):
    """Confirmation that a group's label was removed from one test case."""

    group_id: str
    tc_id: str


class GroupImported(ApiResponse):
    """The outcome of importing a spreadsheet into a group."""

    group_id: str
    linked: int                       # labels added to test cases


class GroupDeleted(ApiResponse):
    """Confirmation that a group was deleted (hidden, and still restorable)."""

    group_id: str
    deleted: bool


class GroupRestored(ApiResponse):
    """Confirmation that a deleted group was brought back."""

    group_id: str
    restored: bool


class GroupPurged(ApiResponse):
    """Confirmation that a deleted group was permanently removed."""

    group_id: str
    purged: bool


class ImportCounts(ApiResponse):
    """How many rows of an import fall into each outcome."""

    new: int                          # rows that would add a test case
    update: int                       # rows that would save a new version of an existing test case
    unchanged: int                    # rows identical to an existing test case
    problem: int                      # rows that cannot be used


class ImportPreview(ApiResponse):
    """What importing a file would do, without saving anything."""

    filename: str | None = None
    sheets: list[str] = []            # worksheet names of a workbook; empty for a text file
    sheet: str | None = None          # the worksheet that was read
    columns: list[str] = []           # the column headers found in the file
    mapping: dict[str, str | None] = {}  # which file column holds each field; null when none was found
    field_labels: dict[str, str] = {}  # the plain-language label of each field
    fields: list[str] = []            # the fields the import understands, in display order
    ignored_columns: list[str] = []   # file columns that matched no field
    question_missing: bool = False    # no column holds the questions: nothing can be imported yet
    auto_chat: bool = False           # there is no chat column, so every question becomes its own chat
    auto_turn: bool = False           # there is no turn column, so turns are numbered in file order
    total_rows: int = 0               # rows read, usable or not
    counts: ImportCounts
    slot_conflicts: int = 0           # rows whose chat and turn match an existing case with a different question
    sample: list[dict[str, Any]] = []  # the first few rows, each with what would happen to it
    problems: list[dict[str, Any]] = []  # the first unusable rows, with the reason
    group_names_in_file: list[str] = []  # groups named in the file's own groups column
    new_group_names: list[str] = []   # those groups that do not exist yet and would be created


class ImportResult(ApiResponse):
    """What an import did, and the rows that could not be used."""

    new: int                          # test cases added
    updated: int                      # test cases that got a new version
    unchanged: int                    # rows identical to an existing test case
    slot_conflicts: int = 0           # rows whose chat and turn match an existing case with a different question
    labelled: int = 0                 # group labels added
    groups_created: list[str] = []    # names of the groups the import created
    problems: int = 0                 # rows that could not be used
    problem_rows: list[dict[str, Any]] = []  # those rows with the reason, so they can be fixed and imported again
    columns: list[str] = []           # the column headers found in the file


class DatasetInfo(ApiResponse):
    """What a dataset spreadsheet holds, from the older dataset endpoints."""

    name: str | None = None           # the file name
    rows: int                         # questions in the file
    chats: int                        # distinct chats among them
    required_columns: list[str] | None = None  # given only for the default dataset
    fingerprint: str | None = None    # identifies the exact set of questions; identical files give the same value


class DatasetUploaded(ApiResponse):
    """The outcome of uploading a dataset spreadsheet into the library."""

    dataset_id: str                   # the id of the group the rows were added to
    rows: int                         # rows in the uploaded file
