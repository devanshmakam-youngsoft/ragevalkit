"""Which version should ship."""
from __future__ import annotations

from typing import Iterable

from ragevalkit.recommendation.constants import (
    DEFAULT_ANSWER_WEIGHT,
    DEFAULT_MATERIAL_WEIGHT,
    DEFAULT_MIN_QUALITY,
    DEFAULT_TOLERANCE,
)
from ragevalkit.recommendation.shared_cases import recommend_on_shared_cases
from ragevalkit.recommendation.totals_fallback import recommend_on_totals


def _recommend_active(active: list[dict], **settings) -> dict:
    if active and all(v.get("case_scores") is not None for v in active):
        return recommend_on_shared_cases(active, **settings)
    return recommend_on_totals(active, **settings)


def recommend(
    versions: Iterable[dict],
    *,
    answer_weight: float = DEFAULT_ANSWER_WEIGHT,
    material_weight: float = DEFAULT_MATERIAL_WEIGHT,
    tolerance: float = DEFAULT_TOLERANCE,
    max_time: float | None = None,
    min_quality: float = DEFAULT_MIN_QUALITY,
    group: str | None = None,
) -> dict:
    """Pick the version to recommend from run summaries (see the module docstring for the rules).

    ``group`` limits the comparison to one group's test cases (runs that did not cover it are ignored).
    ``tolerance``: versions within this many overall-score points of the best count as tied; speed then
    breaks the tie. ``max_time``: optional response-time ceiling in seconds. ``min_quality``: the overall score
    a version needs to be recommended at all.

    The result also says what was recommended *before* the newest run (``previous_best``), so the dashboard can show
    whether the latest run changed the answer.
    """
    active = sorted((v for v in versions if not v.get("archived")), key=lambda v: str(v.get("date", "")))
    settings = dict(group=group, answer_weight=answer_weight, material_weight=material_weight,
                    tolerance=tolerance, max_time=max_time, min_quality=min_quality)
    result = _recommend_active(active, **settings)
    if len(active) > 1:
        result["previous_best"] = _recommend_active(active[:-1], **settings)["best"]
    return result
