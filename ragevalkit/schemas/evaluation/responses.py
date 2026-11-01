"""What the run, version and recommendation endpoints return."""
from typing import Any

from ragevalkit.schemas.base import ApiResponse


class RunSnapshot(ApiResponse):
    """A run in progress (or just ended), as the dashboard shows it."""

    run_id: str
    version: str
    status: str
    total: int
    done: int
    current_question: str = ""
    date: str
    dataset: str
    error: str | None = None
    error_detail: str = ""
    issue_count: int = 0


class RunPreview(ApiResponse):
    """What a run with this selection would execute."""

    selected: int
    context: int
    total: int
    missing: int
    group_names: list[str]
    collisions: list[dict[str, Any]]


class StopRequested(ApiResponse):
    run_id: str
    message: str


class RunDeleted(ApiResponse):
    run_id: str
    deleted: bool


class RunArchiveState(ApiResponse):
    run_id: str
    archived: bool


class IssueOut(ApiResponse):
    """A problem met during a run: a plain message, with the technical text kept apart."""

    stage: str
    where: str = ""
    message: str
    technical: str = ""
    severity: str
    at: str
    count: int = 1


class RunIssues(ApiResponse):
    issues: list[IssueOut]
    issue_total: int
    error: str | None = None
    error_detail: str = ""


class VersionSummary(ApiResponse):
    """One finished run: its averages, findings and problems."""

    version: str
    date: str | None = None
    dataset: str | None = None
    total_rows: int | None = None
    failed_rows: int | None = None
    avg_answer_marks: float | None = None
    avg_material_marks: float | None = None
    avg_total_time: float | None = None
    archived: bool | None = None
    stopped: bool | None = None
    notes: str | None = None
    group_names: list[str] | None = None
    comment: str | None = None
    insights: dict[str, Any] | None = None
    issues: list[IssueOut] | None = None
    issue_total: int | None = None
    log_file: str | None = None
    run_id: str | None = None
    nodes: list[dict[str, Any]] | None = None
    scores: dict[str, Any] | None = None
    group_stats: dict[str, Any] | None = None


class ResultRow(ApiResponse):
    """One question of a version: the answer, the scores and what happened inside."""

    chat_id: str | None = None          # rows saved by older versions may lack some of these
    turn_no: int | None = None
    question: str | None = None
    status: str | None = None
    type: str | None = None
    expected_answer: str | None = None
    generated_answer: str | None = None
    material: str | None = None
    sources: list[str] | None = None
    total_time_taken: float | None = None
    node_timings: dict[str, float] | None = None
    answer_marks: int | None = None
    answer_remarks: str | None = None
    material_marks: int | None = None
    material_remarks: str | None = None
    groups: list[str] | None = None
    case_deleted: bool | None = None
    error_message: str | None = None
    error_detail: str | None = None


class VersionDetail(ApiResponse):
    summary: VersionSummary
    rows: list[ResultRow]


class LatestVersusBest(ApiResponse):
    version: str
    answer: float | None = None
    material: float | None = None
    time: float | None = None
    quality: float | None = None


class BestSoFar(ApiResponse):
    version: str
    quality: float


class Recommendation(ApiResponse):
    """Which version to ship, computed from the saved scores of every non-archived run."""

    best: str | None
    reason: str
    fastest: str | None = None
    runner_up: str | None = None
    latest_gap: dict[str, Any] | None = None
    latest_vs_best: LatestVersusBest | None = None
    previous_best: str | None = None
    min_quality: float
    below_minimum: bool
    best_so_far: BestSoFar | None = None
    not_comparable: list[str]
    not_comparable_detail: dict[str, str]
    not_comparable_scores: dict[str, dict[str, Any]]
    excluded: list[str]
    excluded_detail: dict[str, str]
    budget_miss: bool
    basis: str
    basis_note: str
    weights: dict[str, float]
    tolerance: float
    max_time: float | None = None
    qualities: dict[str, float | None]
    considered: int
    compared_cases: int | None = None
    partial: list[dict[str, Any]]
    scores: dict[str, dict[str, Any]]
