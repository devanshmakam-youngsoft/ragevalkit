"""The older whole-run comparison, for runs saved before per-case scores existed."""
from __future__ import annotations

from collections import Counter

from ragevalkit.services.evaluation.version_recommender.ranking import (
    choose_best,
    empty_result,
    version_view,
)


def _reference_rows(views: list[dict]) -> int:
    """The most common question-set size; ties go to the most recent run."""
    counts = Counter(v["rows"] for v in views)
    best_rows, best_count = views[-1]["rows"], counts[views[-1]["rows"]]
    for rows, count in counts.items():
        if count > best_count:
            best_rows, best_count = rows, count
    return best_rows


def recommend_on_totals(active: list[dict], *, group, answer_weight, material_weight, tolerance, max_time, min_quality: float = 0.0) -> dict:
    """Recommend a version by comparing whole-run averages, for runs saved without per-case scores.

    Only runs that covered the most common number of test cases are compared, and runs that were stopped early,
    had failed rows or have no answer score are excluded. This is weaker than ``recommend_on_shared_cases``
    because the runs may not have used the same questions.

    Args:
        active: Run summaries, oldest first.
        group: Name of a group to compare on only that group's statistics, or None for the whole run.
        answer_weight: Weight of the answer score in the overall score.
        material_weight: Weight of the context score in the overall score.
        tolerance: Overall-score points within which versions tie; speed then breaks the tie.
        max_time: Response-time ceiling in seconds, or None for no ceiling.
        min_quality: Overall score a version needs to be recommended at all.

    Returns:
        The recommendation result; see ``recommend``.
    """
    views = []
    for idx, summary in enumerate(active):
        view = version_view(summary, group)
        if view is None:
            continue
        views.append({**view, "version": str(summary["version"]), "date": summary.get("date"),
                      "stopped": bool(summary.get("stopped")), "idx": idx})
    result = empty_result(answer_weight, material_weight, tolerance, max_time, len(views), min_quality)
    if not views:
        return result

    rows = _reference_rows(views)
    complete = lambda x: x["rows"] == rows and x["failed"] == 0 and not x["stopped"] and x["answer"] is not None
    result["not_comparable"] = [x["version"] for x in views if x["rows"] != rows]
    for v in result["not_comparable"]:
        result["not_comparable_detail"][v] = "ran a different number of test cases"
        own = next(x for x in views if x["version"] == v)
        result["not_comparable_scores"][v] = {"answer": own["answer"], "material": own["material"], "time": own["time"], "cases": own["rows"]}
    result["excluded"] = [x["version"] for x in views if x["rows"] == rows and not complete(x)]
    eligible = [x for x in views if complete(x)]
    result["_all"] = views
    result["_views"] = views
    return choose_best(
        eligible, result, answer_weight=answer_weight, material_weight=material_weight,
        tolerance=tolerance, max_time=max_time, latest=views[-1], min_quality=min_quality,
    )
