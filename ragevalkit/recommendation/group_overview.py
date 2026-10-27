"""How a group has done across versions."""
from __future__ import annotations

from typing import Iterable

from ragevalkit.recommendation.constants import (
    DEFAULT_ANSWER_WEIGHT,
    DEFAULT_MATERIAL_WEIGHT,
    DEFAULT_TOLERANCE,
)
from ragevalkit.recommendation.engine import recommend
from ragevalkit.recommendation.ranking import mean_of_present, version_view


def _own_stats(summary: dict, group: str) -> dict | None:
    """What a group scored in one run (all of its cases in that run), or None if the run did not cover it."""
    if summary.get("case_scores") is not None:
        entries = [e for e in summary["case_scores"] if group in (e.get("g") or [])]
        if not entries:
            return None
        return {
            "rows": len(entries), "failed": sum(1 for e in entries if not e.get("ok")),
            "answer": mean_of_present(e.get("a") for e in entries), "material": mean_of_present(e.get("m") for e in entries),
            "time": mean_of_present(e.get("t") for e in entries),
        }
    return version_view(summary, group)


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
