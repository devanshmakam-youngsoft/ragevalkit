"""What the test case generation endpoints receive and return."""

from ragevalkit.schemas.testcase_generator.requests import Approval, ItemEdit
from ragevalkit.schemas.testcase_generator.responses import (
    ApproveResult,
    BatchCancelling,
    BatchDetail,
    BatchDiscarded,
    BatchSummary,
    GeneratedItem,
    GenerationLimits,
    ItemRemoved,
)

__all__ = [
    "Approval", "ApproveResult", "BatchCancelling", "BatchDetail", "BatchDiscarded", "BatchSummary",
    "GeneratedItem", "GenerationLimits", "ItemEdit", "ItemRemoved"
]
