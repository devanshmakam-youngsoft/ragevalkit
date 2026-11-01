"""What the test case generation endpoints return."""
from typing import Any

from ragevalkit.schemas.base import ApiResponse


class GenerationCategory(ApiResponse):
    """One kind of question that can be written."""

    key: str                          # "direct", "indirect", "multipart" or "multiturn"; used when starting a batch
    label: str                        # the name shown to people, also the group the approved cases are added to


class GenerationLimits(ApiResponse):
    """What the dialog states up front: file limits, the categories, which model gets the text."""

    max_files: int                    # documents allowed in one upload
    max_file_mb: int                  # size limit per document, in megabytes
    per_category_max: int             # most questions that can be asked for in each category
    per_category_default: int
    turns_default: int                # default number of turns in a multi-turn conversation
    categories: list[GenerationCategory]
    model: str                        # the model that receives the document text
    ttl_hours: int                    # how long a batch waits for review before it is removed
    formats: list[str]                # accepted file types, as extensions without the dot


class BatchSummary(ApiResponse):
    """Generated test cases waiting for review, without the (bulky) items."""

    batch_id: str
    status: str                       # "running", "ready", "failed", "cancelled" or "interrupted" (server restarted)
    created_at: str | None = None     # ISO 8601 UTC
    expires_at: str | None = None     # when an unapproved batch is removed, ISO 8601 UTC
    options: dict[str, Any] | None = None  # {per_category, categories, turns} as they were requested
    model: str | None = None          # the model that wrote the questions
    files: list[dict[str, Any]] = []  # {name, pages, passages, error} per document; error is set if unreadable
    total_tasks: int = 0              # questions to write
    done_tasks: int = 0               # questions finished, written or not
    errors: list[dict[str, Any]] = []  # {category, file, reason, detail} per question that could not be written
    error: str = ""                   # plain-language reason the whole batch failed; empty otherwise
    error_detail: str | None = None   # the technical version of ``error``
    log_file: str | None = None       # name of the technical log file
    item_count: int = 0               # generated items so far (a conversation is one item)
    case_count: int = 0               # test cases the items would become: one per turn
    by_category: dict[str, int] = {}  # items per category key


class GeneratedItem(ApiResponse):
    """One generated question or conversation, waiting for review."""

    item_id: str
    category: str                     # a category key such as "direct"
    file: str | None = None           # the document it was written from
    number: int | None = None         # 1-based position within its category
    turns: list[dict[str, Any]]       # {question, expected_answer, evidence} per turn; evidence quotes the document


class BatchDetail(ApiResponse):
    """A review batch in full: its progress and every generated item."""

    batch_id: str
    status: str                       # "running", "ready", "failed", "cancelled" or "interrupted" (server restarted)
    created_at: str | None = None     # ISO 8601 UTC
    expires_at: str | None = None     # when an unapproved batch is removed, ISO 8601 UTC
    options: dict[str, Any] | None = None  # {per_category, categories, turns} as they were requested
    model: str | None = None          # the model that wrote the questions
    files: list[dict[str, Any]] = []  # {name, pages, passages, error} per document; error is set if unreadable
    total_tasks: int = 0              # questions to write
    done_tasks: int = 0               # questions finished, written or not
    errors: list[dict[str, Any]] = []  # {category, file, reason, detail} per question that could not be written
    error: str = ""                   # plain-language reason the whole batch failed; empty otherwise
    error_detail: str | None = None   # the technical version of ``error``
    log_file: str | None = None       # name of the technical log file
    items: list[GeneratedItem] = []


class ItemRemoved(ApiResponse):
    """Confirmation that an item was dropped from a batch."""

    item_id: str
    removed: bool


class ApproveResult(ApiResponse):
    """What approving a batch added to the library."""

    cases: int                        # test cases added: one per turn
    items: int                        # items approved
    discarded: int                    # items left out of the approval, which are deleted with the batch
    groups: list[str]                 # names of the groups the new cases were labelled with
    groups_created: list[str]         # those groups that did not exist before


class BatchCancelling(ApiResponse):
    """Confirmation that a batch was asked to stop writing."""

    batch_id: str
    cancelling: bool


class BatchDiscarded(ApiResponse):
    """Confirmation that a batch was deleted."""

    batch_id: str
    discarded: bool
