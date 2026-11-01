"""What the test case generation endpoints return."""
from typing import Any

from ragevalkit.schemas.base import ApiResponse


class GenerationCategory(ApiResponse):
    key: str
    label: str


class GenerationLimits(ApiResponse):
    """What the dialog states up front: file limits, the categories, which model gets the text."""

    max_files: int
    max_file_mb: int
    per_category_max: int
    per_category_default: int
    turns_default: int
    categories: list[GenerationCategory]
    model: str
    ttl_hours: int
    formats: list[str]


class BatchSummary(ApiResponse):
    """Generated test cases waiting for review, without the (bulky) items."""

    batch_id: str
    status: str
    created_at: str | None = None
    expires_at: str | None = None
    options: dict[str, Any] | None = None
    model: str | None = None
    files: list[dict[str, Any]] = []
    total_tasks: int = 0
    done_tasks: int = 0
    errors: list[dict[str, Any]] = []
    error: str = ""
    error_detail: str | None = None
    log_file: str | None = None
    item_count: int = 0
    case_count: int = 0
    by_category: dict[str, int] = {}


class GeneratedItem(ApiResponse):
    item_id: str
    category: str
    file: str | None = None
    number: int | None = None
    turns: list[dict[str, Any]]


class BatchDetail(ApiResponse):
    batch_id: str
    status: str
    created_at: str | None = None
    expires_at: str | None = None
    options: dict[str, Any] | None = None
    model: str | None = None
    files: list[dict[str, Any]] = []
    total_tasks: int = 0
    done_tasks: int = 0
    errors: list[dict[str, Any]] = []
    error: str = ""
    error_detail: str | None = None
    log_file: str | None = None
    items: list[GeneratedItem] = []


class ItemRemoved(ApiResponse):
    item_id: str
    removed: bool


class ApproveResult(ApiResponse):
    cases: int
    items: int
    discarded: int
    groups: list[str]
    groups_created: list[str]


class BatchCancelling(ApiResponse):
    batch_id: str
    cancelling: bool


class BatchDiscarded(ApiResponse):
    batch_id: str
    discarded: bool
