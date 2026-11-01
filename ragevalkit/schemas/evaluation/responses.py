"""What the run, version and recommendation endpoints return."""
from typing import Any

from ragevalkit.schemas.base import ApiResponse


class RunSnapshot(ApiResponse):
    """A run in progress (or just ended), as the dashboard shows it."""

    run_id: str                       # identifies the run while it is going on; used to stream, stop or read issues
    version: str
    status: str                       # "running", "completed", "stopped" or "failed"
    total: int                        # questions the run will ask
    done: int                         # questions finished so far
    current_question: str = ""        # the question being asked now (cut to 120 characters); empty when idle
    date: str                         # when the run started, ISO 8601 UTC
    dataset: str                      # where the questions came from: group names joined by " + ", or the file name
    error: str | None = None          # plain-language reason the run failed; null otherwise
    error_detail: str = ""            # the technical version of ``error``
    issue_count: int = 0              # distinct problems met so far; see GET /api/runs/{run_id}/issues


class RunPreview(ApiResponse):
    """What a run with this selection would execute: the counts shown before a run is started."""

    selected: int                     # distinct test cases asked for, through groups and/or ids
    context: int                      # earlier turns added so multi-turn chats keep their history
    total: int                        # questions the run would ask: selected plus context
    missing: int                      # requested test case ids that do not exist
    group_names: list[str]            # the selected groups that contributed at least one test case
    collisions: list[dict[str, Any]]  # {chat_id, turn_no, tc_ids}: different cases sharing a chat and turn block a run


class StopRequested(ApiResponse):
    """Confirmation that a running evaluation was asked to stop."""

    run_id: str
    message: str                      # what happens next, in plain words


class RunDeleted(ApiResponse):
    """Confirmation that a saved run was deleted."""

    run_id: str                       # the version name that was deleted
    deleted: bool


class RunArchiveState(ApiResponse):
    """A saved run after it was archived or restored."""

    run_id: str                       # the version name
    archived: bool                    # true when the run is now hidden from the default listing


class IssueOut(ApiResponse):
    """A problem met during a run: a plain message, with the technical text kept apart."""

    stage: str                        # which part of the run: "answer", "grading", "summary", ...
    where: str = ""                   # which question or file, in words
    message: str                      # plain language, safe to show anyone
    technical: str = ""               # the error and the end of its traceback, secrets hidden
    severity: str                     # "error": something is missing or wrong; "warning": it carried on with a fallback
    at: str                           # when it first happened, ISO 8601 UTC
    count: int = 1                    # how many times this same problem happened


class RunIssues(ApiResponse):
    """The problems a run has met so far, and why the run failed if it did."""

    issues: list[IssueOut]            # only the first problems are kept; the run's log file has all of them
    issue_total: int                  # every distinct problem, which can be more than ``issues`` lists
    error: str | None = None          # plain-language reason the whole run failed; null otherwise
    error_detail: str = ""            # the technical version of ``error``


class VersionSummary(ApiResponse):
    """One finished run: its averages, findings and problems."""

    version: str
    date: str | None = None           # when the run started, ISO 8601 UTC
    dataset: str | None = None        # where the questions came from: group names joined by " + ", or the file name
    total_rows: int | None = None     # questions asked
    failed_rows: int | None = None    # questions that could not be answered or graded
    avg_answer_marks: float | None = None    # mean answer score, 0 to 10
    avg_material_marks: float | None = None  # mean score of the retrieved context, 0 to 10; null when none was graded
    avg_total_time: float | None = None      # mean response time per question, in seconds
    archived: bool | None = None      # true when hidden from the default listing
    stopped: bool | None = None       # true when stopped early; such a run is never recommended or compared
    notes: str | None = None          # free text given when the run was started
    group_names: list[str] | None = None     # the groups the run covered
    comment: str | None = None        # the findings as plain text
    insights: dict[str, Any] | None = None   # the findings as ``items``, each a watch-out with a suggestion
    issues: list[IssueOut] | None = None
    issue_total: int | None = None    # every distinct problem, which can be more than ``issues`` lists
    log_file: str | None = None       # name of the technical log file; see GET /api/versions/{version}/log
    run_id: str | None = None         # the version name again; the id of the live run is in RunSnapshot
    nodes: list[dict[str, Any]] | None = None  # {name, avg}: mean seconds spent in each recorded step of the pipeline
    scores: dict[str, Any] | None = None       # detailed scores: score tiers, per question type, response-time spread
    group_stats: dict[str, Any] | None = None  # the same averages for each group's own cases, keyed by group name


class ResultRow(ApiResponse):
    """One question of a version: the answer, the scores and what happened inside."""

    chat_id: str | None = None          # rows saved by older versions may lack some of these
    turn_no: int | None = None
    question: str | None = None
    status: str | None = None           # "ok", "generation_failed" (no answer) or "grading_failed"
    type: str | None = None             # the kind of test case, for example "rag"
    expected_answer: str | None = None
    generated_answer: str | None = None
    material: str | None = None         # the retrieved context the answer was judged against
    sources: list[str] | None = None    # the sources the pipeline reported using
    total_time_taken: float | None = None  # seconds
    node_timings: dict[str, float] | None = None  # seconds spent in each recorded step
    answer_marks: int | None = None     # 0 to 10
    answer_remarks: str | None = None
    material_marks: int | None = None   # 0 to 10; null when no retrieval was expected or it was not graded
    material_remarks: str | None = None
    groups: list[str] | None = None     # the groups the test case belonged to when the run happened
    case_deleted: bool | None = None    # true when the test case has been deleted since
    error_message: str | None = None    # plain-language reason for a failed question
    error_detail: str | None = None     # the technical version of ``error_message``


class VersionDetail(ApiResponse):
    """One version in full: its summary and the result of every question."""

    summary: VersionSummary
    rows: list[ResultRow]


class LatestVersusBest(ApiResponse):
    """How the newest run differs from the recommended version: each figure is newest minus recommended."""

    version: str                      # the newest run
    answer: float | None = None       # negative means the newest run scored lower
    material: float | None = None
    time: float | None = None         # seconds; positive means the newest run was slower
    quality: float | None = None


class BestSoFar(ApiResponse):
    """The leading version when none reaches the minimum score to be recommended."""

    version: str
    quality: float                    # overall score, 0 to 10


class Recommendation(ApiResponse):
    """Which version to ship, computed from the saved scores of every non-archived run."""

    best: str | None                  # the recommended version; null when none qualifies
    reason: str
    fastest: str | None = None        # the fastest version when it is not ``best``; the only one named on a budget miss
    runner_up: str | None = None
    latest_gap: dict[str, Any] | None = None  # {version, gap} when the newest run trails ``best`` by over the tolerance
    latest_vs_best: LatestVersusBest | None = None
    previous_best: str | None = None  # what was recommended before the newest run
    min_quality: float                # overall score (0 to 10) a version needs to be recommended
    below_minimum: bool               # true when no version reached ``min_quality``
    best_so_far: BestSoFar | None = None
    not_comparable: list[str]         # versions that share too few test cases with the others to be compared
    not_comparable_detail: dict[str, str]    # why, per version
    not_comparable_scores: dict[str, dict[str, Any]]  # what each scored on its own test cases
    excluded: list[str]               # versions left out: stopped early, failed questions, or no answer scores
    excluded_detail: dict[str, str]   # why, per version
    budget_miss: bool                 # true when no version answered within ``max_time``
    basis: str                        # "weighted" (answer and context) or "answer_only"
    basis_note: str                   # why the basis is answer-only, when it is
    weights: dict[str, float]         # {answer, material}, as used (scaled to add up to 1)
    tolerance: float                  # versions within this many points (0 to 10) of the top count as tied
    max_time: float | None = None     # response-time ceiling in seconds; null for none
    qualities: dict[str, float | None]  # overall score (0 to 10) per version; null without answer scores
    considered: int                   # versions looked at
    compared_cases: int | None = None  # test cases compared; null when runs were compared on whole-run totals
    partial: list[dict[str, Any]]     # {version, ran, compared}: versions that ran more cases than were compared
    scores: dict[str, dict[str, Any]]  # per version on the compared cases: answer, material, time, cases, quality
