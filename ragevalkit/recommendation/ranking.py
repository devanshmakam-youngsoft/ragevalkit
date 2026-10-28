"""Scoring and choosing among versions that have already been put on the same footing."""
from __future__ import annotations

from typing import Iterable


def mean_of_present(values: Iterable) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def overall_quality(view: dict, answer_weight: float, material_weight: float, use_material: bool) -> float | None:
    answer, material = view["answer"], view["material"]
    if answer is None:
        return None
    total = answer_weight + material_weight
    if not use_material or material is None or total <= 0:
        return answer
    return (answer_weight * answer + material_weight * material) / total


def empty_result(
    answer_weight: float, material_weight: float, tolerance: float, max_time: float | None, considered: int,
    min_quality: float = 0.0,
) -> dict:
    return {
        "best": None, "reason": "", "fastest": None, "runner_up": None, "latest_gap": None,
        # the newest run against the recommended one, when both were compared; and what was recommended before it ran
        "latest_vs_best": None, "previous_best": None,
        # nothing reached min_quality: no recommendation, but the best so far is named
        "min_quality": min_quality, "below_minimum": False, "best_so_far": None,
        "not_comparable": [], "not_comparable_detail": {}, "not_comparable_scores": {}, "excluded": [], "excluded_detail": {},
        "budget_miss": False, "basis": "weighted", "basis_note": "",
        "weights": {"answer": answer_weight, "material": material_weight},
        "tolerance": tolerance, "max_time": max_time, "qualities": {}, "considered": considered,
        # what the comparison was actually made on
        "compared_cases": None, "partial": [], "scores": {},
    }


def _delta(latest: float | None, best: float | None) -> float | None:
    return None if latest is None or best is None else round(latest - best, 3)


def choose_best(
    best_pool: list[dict], result: dict, *, answer_weight, material_weight, tolerance, max_time, latest, min_quality: float = 0.0,
) -> dict:
    """Shared by both comparison paths: from versions with ``answer``/``material``/``time``/``idx`` pick the winner."""
    eligible = best_pool
    have_material = [x for x in eligible if x["material"] is not None]
    use_material = bool(eligible) and len(have_material) == len(eligible) and material_weight > 0
    if not use_material:
        result["basis"] = "answer_only"
        result["weights"] = {"answer": 1.0, "material": 0.0}
        if have_material and len(have_material) != len(eligible) and material_weight > 0:
            missing = ", ".join(f"v{x['version']}" for x in eligible if x["material"] is None)
            result["basis_note"] = (
                f"Context quality was not graded for {missing}, so versions are compared on answer quality only."
            )
    else:
        total = answer_weight + material_weight
        result["weights"] = {"answer": answer_weight / total, "material": material_weight / total}

    for x in result.pop("_all"):
        x["q"] = overall_quality(x, answer_weight, material_weight, use_material)
    result["qualities"] = {x["version"]: (round(x["q"], 3) if x["q"] is not None else None) for x in result["_views"]}
    result["scores"] = {
        x["version"]: {
            "answer": x["answer"], "material": x["material"], "time": x["time"], "cases": x.get("cases"),
            "quality": round(x["q"], 3) if x["q"] is not None else None,
        }
        for x in result["_views"] if x["answer"] is not None
    } if result["compared_cases"] is not None else {}
    result.pop("_views")
    if not eligible:
        return result

    speed = lambda x: x["time"] if x["time"] is not None else float("inf")
    fits = eligible if max_time is None else [x for x in eligible if speed(x) <= max_time]
    if not fits:
        result["fastest"] = min(eligible, key=speed)["version"]
        result["budget_miss"] = True
        return result

    top = max(x["q"] for x in fits)
    if top < min_quality:
        leader = max(fits, key=lambda x: (x["q"], -speed(x), x["idx"]))
        result.update(
            below_minimum=True, best_so_far={"version": leader["version"], "quality": round(leader["q"], 3)},
            reason=f"No version scores {min_quality:g} or more yet; v{leader['version']} is the best so far ({leader['q']:.1f}).",
        )
        return result
    tied = [x for x in fits if x["q"] >= top - tolerance and x["q"] >= min_quality]
    # fastest of the tied versions; then higher quality; then the newer run
    best = min(tied, key=lambda x: (speed(x), -x["q"], -x["idx"]))

    if len(fits) == 1:
        reason = "Only version run on this question set."
    elif len(tied) == 1:
        reason = f"Highest overall score of {len(fits)} comparable versions."
    else:
        others = ", ".join(f"v{x['version']}" for x in tied if x is not best)
        reason = f"Overall score is within {tolerance:g} of the top (also {others}) and it is the fastest of those."

    fastest = min(fits, key=speed)
    rest = [x for x in fits if x is not best]
    runner_up = min(rest, key=lambda x: (-x["q"], speed(x))) if rest else None
    gap = best["q"] - latest["q"] if latest in fits and latest is not best else 0

    versus = None
    if latest in fits and latest is not best:
        versus = {
            "version": latest["version"], "answer": _delta(latest["answer"], best["answer"]),
            "material": _delta(latest["material"], best["material"]) if use_material else None,
            "time": _delta(latest["time"], best["time"]), "quality": _delta(latest["q"], best["q"]),
        }
    result.update(
        latest_vs_best=versus,
        best=best["version"], reason=reason,
        fastest=fastest["version"] if fastest is not best else None,
        runner_up=runner_up["version"] if runner_up else None,
        latest_gap={"version": latest["version"], "gap": round(gap, 3)} if gap > tolerance else None,
    )
    return result


def version_view(summary: dict, group: str | None) -> dict | None:
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
