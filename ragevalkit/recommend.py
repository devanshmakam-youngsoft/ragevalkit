"""Which version should ship, and how has a group done over time?

Everything here is computed on every request from the scores saved on each run, over the runs that
are *not archived* — so archiving or deleting a version changes the answer straight away, and nothing
about a recommendation is ever saved that could go stale.

HOW VERSIONS ARE COMPARED
-------------------------
Averages are only fair when versions answered the same questions. Each run saves its score for every
test case (``case_scores``), so versions are compared **on the test cases they share**:

1. Take the test cases every compared version ran (a case counts as the same only if its chat, turn,
   question and expected answer are unchanged). Adding a test case, or running an extra group, in a
   later version therefore no longer hides that version: it is judged on the cases the others also ran.
2. If the shared cases are only a thin slice (fewer than half of a typical version's cases — say a
   2-question smoke test next to 10-question runs), the version that shares least is left out and
   reported as not compared, instead of letting it shrink everyone's comparison.
3. Versions that were stopped early, or had a failure on a shared case, are left out.
4. Each remaining version is scored on the shared cases only: *overall score* = answer quality and
   context quality weighted by ``serve()`` (default 60/40). Context quality only counts when every
   compared version has it; otherwise all are compared on answer quality alone, and the result says so.
5. Versions within ``tolerance`` of the best overall score are tied; the fastest of them is recommended.

Runs saved before per-case scores existed are filled in from their saved results the first time they
are needed (see ``EvalStore.list_versions_for_comparison``). If a run has none at all, the older
whole-run comparison (same number of questions) is used instead.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Iterable

DEFAULT_ANSWER_WEIGHT = 0.6
DEFAULT_MATERIAL_WEIGHT = 0.4
DEFAULT_TOLERANCE = 0.25

# A comparison must rest on at least this share of a typical (median) version's test cases.
MIN_SHARED_SHARE = 0.5


def _mean(values: Iterable) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def _quality(view: dict, answer_weight: float, material_weight: float, use_material: bool) -> float | None:
    answer, material = view["answer"], view["material"]
    if answer is None:
        return None
    total = answer_weight + material_weight
    if not use_material or material is None or total <= 0:
        return answer
    return (answer_weight * answer + material_weight * material) / total


def _empty(answer_weight: float, material_weight: float, tolerance: float, max_time: float | None, considered: int) -> dict:
    return {
        "best": None, "reason": "", "fastest": None, "runner_up": None, "latest_gap": None,
        "not_comparable": [], "not_comparable_detail": {}, "excluded": [], "excluded_detail": {},
        "budget_miss": False, "basis": "weighted", "basis_note": "",
        "weights": {"answer": answer_weight, "material": material_weight},
        "tolerance": tolerance, "max_time": max_time, "qualities": {}, "considered": considered,
        # what the comparison was actually made on
        "compared_cases": None, "partial": [], "scores": {},
    }


def _choose(best_pool: list[dict], result: dict, *, answer_weight, material_weight, tolerance, max_time, latest) -> dict:
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
        x["q"] = _quality(x, answer_weight, material_weight, use_material)
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
    tied = [x for x in fits if x["q"] >= top - tolerance]
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

    result.update(
        best=best["version"], reason=reason,
        fastest=fastest["version"] if fastest is not best else None,
        runner_up=runner_up["version"] if runner_up else None,
        latest_gap={"version": latest["version"], "gap": round(gap, 3)} if gap > tolerance else None,
    )
    return result


# ---------------------------------------------------------------------------------------------
# Comparison on shared test cases
# ---------------------------------------------------------------------------------------------

def _intersection(views: list[dict]) -> set[str]:
    sets = [set(v["cases"]) for v in views]
    return set.intersection(*sets) if sets else set()


def _recommend_on_shared_cases(active: list[dict], *, group, answer_weight, material_weight, tolerance, max_time) -> dict:
    views = []
    for idx, summary in enumerate(active):
        entries = summary["case_scores"]
        if group is not None:
            entries = [e for e in entries if group in (e.get("g") or [])]
            if not entries:
                continue
        views.append({
            "version": str(summary["version"]), "idx": idx, "stopped": bool(summary.get("stopped")),
            "cases": {e["k"]: e for e in entries}, "ran": len(entries),
        })
    result = _empty(answer_weight, material_weight, tolerance, max_time, len(views))
    if not views:
        return result

    result["excluded"] = [v["version"] for v in views if v["stopped"]]
    for v in views:
        if v["stopped"]:
            result["excluded_detail"][v["version"]] = "stopped early"
    pool = [v for v in views if not v["stopped"]]

    # Drop the version that shares least until the rest overlap on a meaningful number of cases.
    dropped: list[dict] = []
    while len(pool) > 1:
        sizes = sorted(v["ran"] for v in pool)
        typical = sizes[(len(sizes) - 1) // 2]
        need = max(1, math.ceil(typical * MIN_SHARED_SHARE))
        if len(_intersection(pool)) >= need:
            break
        drop = max(pool, key=lambda v: (len(_intersection([x for x in pool if x is not v])), -v["ran"], -v["idx"]))
        pool.remove(drop)
        dropped.append(drop)

    shared = _intersection(pool) if len(pool) > 1 else (set(pool[0]["cases"]) if pool else set())
    for v in dropped:
        overlap = len(set(v["cases"]) & shared)
        result["not_comparable"].append(v["version"])
        result["not_comparable_detail"][v["version"]] = (
            f"ran {v['ran']} test cases but shares only {overlap} with the versions it was compared against"
        )

    # Score every remaining version on the shared cases only.
    for v in pool:
        entries = [v["cases"][k] for k in shared]
        v["answer"] = _mean(e.get("a") for e in entries)
        v["material"] = _mean(e.get("m") for e in entries)
        v["time"] = _mean(e.get("t") for e in entries)
        v["cases"] = len(entries)
        v["failed"] = sum(1 for e in entries if not e.get("ok"))
    # `cases` is now a count; keep the original sizes for the "judged on N of M" note
    complete = [v for v in pool if v["failed"] == 0 and v["answer"] is not None]
    for v in pool:
        if v not in complete:
            result["excluded"].append(v["version"])
            result["excluded_detail"][v["version"]] = (
                f"{v['failed']} of the {v['cases']} shared test cases failed" if v["failed"] else "no answer scores"
            )

    result["compared_cases"] = len(shared)
    result["partial"] = [
        {"version": v["version"], "ran": v["ran"], "compared": len(shared)} for v in pool if v["ran"] > len(shared)
    ]
    result["_all"] = pool
    result["_views"] = pool
    newest = views[-1]  # the latest run overall; only meaningful for 'latest is worse' if it was compared
    latest = newest if any(v is newest for v in pool) else None
    return _choose(
        complete, result, answer_weight=answer_weight, material_weight=material_weight,
        tolerance=tolerance, max_time=max_time, latest=latest,
    )


# ---------------------------------------------------------------------------------------------
# Older whole-run comparison (runs without per-case scores)
# ---------------------------------------------------------------------------------------------

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


def _reference_rows(views: list[dict]) -> int:
    """The most common question-set size; ties go to the most recent run."""
    counts = Counter(v["rows"] for v in views)
    best_rows, best_count = views[-1]["rows"], counts[views[-1]["rows"]]
    for rows, count in counts.items():
        if count > best_count:
            best_rows, best_count = rows, count
    return best_rows


def _recommend_on_totals(active: list[dict], *, group, answer_weight, material_weight, tolerance, max_time) -> dict:
    views = []
    for idx, summary in enumerate(active):
        view = _view(summary, group)
        if view is None:
            continue
        views.append({**view, "version": str(summary["version"]), "date": summary.get("date"),
                      "stopped": bool(summary.get("stopped")), "idx": idx})
    result = _empty(answer_weight, material_weight, tolerance, max_time, len(views))
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
    return _choose(
        eligible, result, answer_weight=answer_weight, material_weight=material_weight,
        tolerance=tolerance, max_time=max_time, latest=views[-1],
    )


def recommend(
    versions: Iterable[dict],
    *,
    answer_weight: float = DEFAULT_ANSWER_WEIGHT,
    material_weight: float = DEFAULT_MATERIAL_WEIGHT,
    tolerance: float = DEFAULT_TOLERANCE,
    max_time: float | None = None,
    group: str | None = None,
) -> dict:
    """Pick the version to recommend from run summaries (see the module docstring for the rules).

    ``group`` limits the comparison to one group's test cases (runs that did not cover it are ignored).
    ``tolerance``: versions within this many overall-score points of the best count as tied; speed then
    breaks the tie. ``max_time``: optional response-time ceiling in seconds.
    """
    active = sorted((v for v in versions if not v.get("archived")), key=lambda v: str(v.get("date", "")))
    kwargs = dict(group=group, answer_weight=answer_weight, material_weight=material_weight,
                  tolerance=tolerance, max_time=max_time)
    if active and all(v.get("case_scores") is not None for v in active):
        return _recommend_on_shared_cases(active, **kwargs)
    return _recommend_on_totals(active, **kwargs)


# ---------------------------------------------------------------------------------------------
# One group's history
# ---------------------------------------------------------------------------------------------

def _own_stats(summary: dict, group: str) -> dict | None:
    """What a group scored in one run (all of its cases in that run), or None if the run did not cover it."""
    if summary.get("case_scores") is not None:
        entries = [e for e in summary["case_scores"] if group in (e.get("g") or [])]
        if not entries:
            return None
        return {
            "rows": len(entries), "failed": sum(1 for e in entries if not e.get("ok")),
            "answer": _mean(e.get("a") for e in entries), "material": _mean(e.get("m") for e in entries),
            "time": _mean(e.get("t") for e in entries),
        }
    return _view(summary, group)


def group_overview(
    versions: Iterable[dict],
    group: str,
    *,
    answer_weight: float = DEFAULT_ANSWER_WEIGHT,
    material_weight: float = DEFAULT_MATERIAL_WEIGHT,
    tolerance: float = DEFAULT_TOLERANCE,
    max_time: float | None = None,
) -> dict:
    """How one group has done across non-archived runs: its history, last run and best version so far.

    Each history row shows what the group scored in that run; ``quality`` is its overall score on the
    cases the compared versions share (None for a version that could not be compared)."""
    versions = list(versions)
    reco = recommend(
        versions, answer_weight=answer_weight, material_weight=material_weight,
        tolerance=tolerance, max_time=max_time, group=group,
    )
    qualities = reco["qualities"]
    active = sorted((v for v in versions if not v.get("archived")), key=lambda v: str(v.get("date", "")))
    history = []
    for summary in reversed(active):  # newest first
        stats = _own_stats(summary, group)
        if stats is None:
            continue
        version = str(summary["version"])
        history.append({
            "version": version, "date": summary.get("date"), "total_rows": stats["rows"], "failed_rows": stats["failed"],
            "avg_answer_marks": stats["answer"], "avg_material_marks": stats["material"], "avg_total_time": stats["time"],
            "quality": qualities.get(version), "stopped": bool(summary.get("stopped")),
        })
    by_version = {h["version"]: h for h in history}
    return {
        "run_count": len(history),
        "last": history[0] if history else None,
        "best": by_version.get(reco["best"]) if reco["best"] else None,
        "reason": reco["reason"],
        "basis_note": reco["basis_note"],
        "compared_cases": reco["compared_cases"],
        "runs": history,
    }
