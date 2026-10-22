"""Which version should ship, and how has a group done over time?

Everything here is computed from the scores stored on each run's summary, on every request, over
the runs that are *not archived* — so archiving or deleting a version changes the answer straight
away, and nothing about a recommendation is ever saved that could go stale.

Quality is a weighted mix of the answer and material marks (weights come from ``serve()``).
Versions are only compared when they ran the same number of questions, finished without failed
rows, and were not stopped early. Material marks are only used when *every* compared version has
them: mixing "answer only" with "answer + material" would let a run whose material was never
graded beat one that was — so in that case all versions are compared on answer marks alone and
the result says so.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

DEFAULT_ANSWER_WEIGHT = 0.6
DEFAULT_MATERIAL_WEIGHT = 0.4
DEFAULT_TOLERANCE = 0.25


def _view(summary: dict, group: str | None) -> dict | None:
    """The scores of one run, overall or for one group. None if the run did not cover the group."""
    if group is None:
        return {
            "rows": summary.get("total_rows", 0),
            "failed": summary.get("failed_rows", 0),
            "answer": summary.get("avg_answer_marks"),
            "material": summary.get("avg_material_marks"),
            "time": summary.get("avg_total_time"),
        }
    stats = (summary.get("group_stats") or {}).get(group)
    if not stats:
        return None
    time = stats.get("avg_total_time")
    return {
        "rows": stats.get("total_rows", 0),
        "failed": stats.get("failed_rows", summary.get("failed_rows", 0)),
        "answer": stats.get("avg_answer_marks"),
        "material": stats.get("avg_material_marks"),
        "time": time if time is not None else summary.get("avg_total_time"),
    }


def _quality(view: dict, answer_weight: float, material_weight: float, use_material: bool) -> float | None:
    answer, material = view["answer"], view["material"]
    if answer is None:
        return None
    total = answer_weight + material_weight
    if not use_material or material is None or total <= 0:
        return answer
    return (answer_weight * answer + material_weight * material) / total


def _reference_rows(views: list[dict]) -> int:
    """The most common question-set size; ties go to the most recent run."""
    counts = Counter(v["rows"] for v in views)
    best_rows, best_count = views[-1]["rows"], counts[views[-1]["rows"]]
    for rows, count in counts.items():
        if count > best_count:
            best_rows, best_count = rows, count
    return best_rows


def _views(versions: Iterable[dict], group: str | None) -> list[dict]:
    """Non-archived runs, oldest first, each reduced to the numbers that matter."""
    active = sorted((v for v in versions if not v.get("archived")), key=lambda v: str(v.get("date", "")))
    out = []
    for idx, summary in enumerate(active):
        view = _view(summary, group)
        if view is None:
            continue
        out.append({
            **view,
            "version": str(summary["version"]),
            "date": summary.get("date"),
            "stopped": bool(summary.get("stopped")),
            "idx": idx,
        })
    return out


def recommend(
    versions: Iterable[dict],
    *,
    answer_weight: float = DEFAULT_ANSWER_WEIGHT,
    material_weight: float = DEFAULT_MATERIAL_WEIGHT,
    tolerance: float = DEFAULT_TOLERANCE,
    max_time: float | None = None,
    group: str | None = None,
) -> dict:
    """Pick the version to recommend from run summaries.

    ``group`` limits the comparison to one group's scores (runs that did not cover it are ignored).
    ``tolerance``: versions within this many quality points of the best count as tied; speed then
    breaks the tie. ``max_time``: optional response-time ceiling in seconds.
    """
    views = _views(versions, group)
    result: dict = {
        "best": None, "reason": "", "fastest": None, "runner_up": None, "latest_gap": None,
        "not_comparable": [], "excluded": [], "budget_miss": False,
        "basis": "weighted", "basis_note": "",
        "weights": {"answer": answer_weight, "material": material_weight},
        "tolerance": tolerance, "max_time": max_time, "qualities": {}, "considered": len(views),
    }
    if not views:
        return result

    rows = _reference_rows(views)
    complete = lambda x: x["rows"] == rows and x["failed"] == 0 and not x["stopped"] and x["answer"] is not None
    result["not_comparable"] = [x["version"] for x in views if x["rows"] != rows]
    result["excluded"] = [x["version"] for x in views if x["rows"] == rows and not complete(x)]
    eligible = [x for x in views if complete(x)]

    # Material marks only count when every compared version has them (see module docstring).
    have_material = [x for x in eligible if x["material"] is not None]
    use_material = bool(eligible) and len(have_material) == len(eligible) and material_weight > 0
    if not use_material:
        result["basis"] = "answer_only"
        result["weights"] = {"answer": 1.0, "material": 0.0}
        if have_material and len(have_material) != len(eligible) and material_weight > 0:
            missing = ", ".join(f"v{x['version']}" for x in eligible if x["material"] is None)
            result["basis_note"] = (
                f"Material marks were not graded for {missing}, so versions are compared on answer marks only."
            )
    else:
        total = answer_weight + material_weight
        result["weights"] = {"answer": answer_weight / total, "material": material_weight / total}

    for x in views:
        x["q"] = _quality(x, answer_weight, material_weight, use_material)
    result["qualities"] = {x["version"]: (round(x["q"], 3) if x["q"] is not None else None) for x in views}
    if not eligible:
        return result

    speed = lambda x: x["time"] if x["time"] is not None else float("inf")
    fits = eligible if max_time is None else [x for x in eligible if speed(x) <= max_time]
    if not fits:
        result["fastest"] = min(eligible, key=speed)["version"]
        result["budget_miss"] = True
        return result

    top = max(x["q"] for x in fits)
    tied = [x for x in fits if x["q"] >= top - tolerance]
    # fastest of the tied versions; then higher quality; then the newer run
    best = min(tied, key=lambda x: (speed(x), -x["q"], -x["idx"]))

    if len(fits) == 1:
        reason = "Only version run on this question set."
    elif len(tied) == 1:
        reason = f"Highest quality of {len(fits)} comparable versions."
    else:
        others = ", ".join(f"v{x['version']}" for x in tied if x is not best)
        reason = f"Quality is within {tolerance:g} of the top (also {others}) and it is the fastest of those."

    fastest = min(fits, key=speed)
    rest = [x for x in fits if x is not best]
    runner_up = min(rest, key=lambda x: (-x["q"], speed(x))) if rest else None
    latest = views[-1]
    gap = best["q"] - latest["q"] if latest in fits and latest is not best else 0

    result.update(
        best=best["version"], reason=reason,
        fastest=fastest["version"] if fastest is not best else None,
        runner_up=runner_up["version"] if runner_up else None,
        latest_gap={"version": latest["version"], "gap": round(gap, 3)} if gap > tolerance else None,
    )
    return result


def group_overview(
    versions: Iterable[dict],
    group: str,
    *,
    answer_weight: float = DEFAULT_ANSWER_WEIGHT,
    material_weight: float = DEFAULT_MATERIAL_WEIGHT,
    tolerance: float = DEFAULT_TOLERANCE,
    max_time: float | None = None,
) -> dict:
    """How one group has done across non-archived runs: its history, last run and best version so far."""
    versions = list(versions)
    reco = recommend(
        versions, answer_weight=answer_weight, material_weight=material_weight,
        tolerance=tolerance, max_time=max_time, group=group,
    )
    qualities = reco["qualities"]
    history = []
    for x in reversed(_views(versions, group)):  # newest first
        history.append({
            "version": x["version"], "date": x["date"], "total_rows": x["rows"], "failed_rows": x["failed"],
            "avg_answer_marks": x["answer"], "avg_material_marks": x["material"], "avg_total_time": x["time"],
            "quality": qualities.get(x["version"]), "stopped": x["stopped"],
        })
    by_version = {h["version"]: h for h in history}
    return {
        "run_count": len(history),
        "last": history[0] if history else None,
        "best": by_version.get(reco["best"]) if reco["best"] else None,
        "reason": reco["reason"],
        "basis_note": reco["basis_note"],
        "runs": history,
    }
