"""What the run, version and recommendation endpoints receive and return."""

from ragevalkit.schemas.evaluation.requests import SelectionBody
from ragevalkit.schemas.evaluation.responses import (
    Recommendation,
    RunArchiveState,
    RunDeleted,
    RunIssues,
    RunPreview,
    RunSnapshot,
    StopRequested,
    VersionDetail,
    VersionSummary,
)

__all__ = [
    "Recommendation", "RunArchiveState", "RunDeleted", "RunIssues", "RunPreview", "RunSnapshot",
    "SelectionBody", "StopRequested", "VersionDetail", "VersionSummary"
]
