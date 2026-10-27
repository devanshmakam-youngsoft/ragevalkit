"""The older whole-run comparison, for runs saved before per-case scores existed."""
from __future__ import annotations

from collections import Counter

from ragevalkit.recommendation.ranking import choose_best, empty_result, version_view


def _reference_rows(views: list[dict]) -> int:
    """The most common question-set size; ties go to the most recent run."""
    counts = Counter(v["rows"] for v in views)
    best_rows, best_count = views[-1]["rows"], counts[views[-1]["rows"]]
    for rows, count in counts.items():
        if count > best_count:
            best_rows, best_count = rows, count
    return best_rows


def recommend_on_totals(active: list[dict], *, group, answer_weight, material_weight, tolerance, max_time) -> dict:
    views = []
    for idx, summary in enumerate(active):
        view = version_view(summary, group)
        if view is None:
            continue
        views.append({**view, "version": str(summary["version"]), "date": summary.get("date"),
                      "stopped": bool(summary.get("stopped")), "idx": idx})
    result = empty_result(answer_weight, material_weight, tolerance, max_time, len(views))
    if not views:
        return result

    rows = _reference_rows(views)
    complete = lambda x: x["rows"] == rows and x["failed"] == 0 and not x["stopped"] and x["answer"] is not None
    result["not_comparable"] = [x["version"] for x in views if x["rows"] != rows]
    for v in result["not_comparable"]:
        result["not_comparable_detail"][v] = "ran a different number of test cases"
    result["excluded"] = [x["version"] for x in views if x["rows"] == rows and not complete(x)]
    eligible = [x for x in views if complete(x)]
    result["_all"] = views
    result["_views"] = views
    return choose_best(
        eligible, result, answer_weight=answer_weight, material_weight=material_weight,
        tolerance=tolerance, max_time=max_time, latest=views[-1],
    )
