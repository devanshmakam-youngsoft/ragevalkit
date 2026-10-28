"""Comparing versions on the test cases they all ran."""
from __future__ import annotations

import math

from ragevalkit.recommendation.constants import MIN_SHARED_SHARE
from ragevalkit.recommendation.ranking import choose_best, empty_result, mean_of_present


def shared_case_keys(views: list[dict]) -> set[str]:
    sets = [set(v["cases"]) for v in views]
    return set.intersection(*sets) if sets else set()


def recommend_on_shared_cases(active: list[dict], *, group, answer_weight, material_weight, tolerance, max_time, min_quality: float = 0.0) -> dict:
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
    result = empty_result(answer_weight, material_weight, tolerance, max_time, len(views), min_quality)
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
        if len(shared_case_keys(pool)) >= need:
            break
        drop = max(pool, key=lambda v: (len(shared_case_keys([x for x in pool if x is not v])), -v["ran"], -v["idx"]))
        pool.remove(drop)
        dropped.append(drop)

    shared = shared_case_keys(pool) if len(pool) > 1 else (set(pool[0]["cases"]) if pool else set())
    for v in dropped:
        overlap = len(set(v["cases"]) & shared)
        result["not_comparable"].append(v["version"])
        entries = list(v["cases"].values())
        result["not_comparable_scores"][v["version"]] = {      # what it scored on its own cases, so a good one is not hidden
            "answer": mean_of_present(e.get("a") for e in entries), "material": mean_of_present(e.get("m") for e in entries),
            "time": mean_of_present(e.get("t") for e in entries), "cases": v["ran"],
        }
        result["not_comparable_detail"][v["version"]] = (
            f"ran {v['ran']} test cases but shares only {overlap} with the versions it was compared against"
        )

    # Score every remaining version on the shared cases only.
    for v in pool:
        entries = [v["cases"][k] for k in shared]
        v["answer"] = mean_of_present(e.get("a") for e in entries)
        v["material"] = mean_of_present(e.get("m") for e in entries)
        v["time"] = mean_of_present(e.get("t") for e in entries)
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
    return choose_best(
        complete, result, answer_weight=answer_weight, material_weight=material_weight,
        tolerance=tolerance, max_time=max_time, latest=latest, min_quality=min_quality,
    )
