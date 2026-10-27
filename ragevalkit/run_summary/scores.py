"""The detailed scores of one run."""
import math

from ragevalkit.run_summary.averages import column_of, is_nan, mean_of


def build_scores(rows: list[dict]) -> dict:
    """The detailed scores of one run, saved on its summary so every later comparison reads them
    instead of recomputing from receipts: overall averages, score tiers, per-question-type
    averages, response-time spread and source-check results."""
    graded = [r for r in rows if r.get("answer_marks") is not None]
    marks = [r["answer_marks"] for r in graded]
    times = sorted(t for t in column_of(rows, "total_time_taken") if t is not None and not is_nan(t))
    by_type: dict[str, list[dict]] = {}
    for r in graded:
        by_type.setdefault(str(r.get("type") or "unknown"), []).append(r)
    checked = [r for r in rows if r.get("source_match") is not None]
    return {
        "graded_rows": len(graded),
        "answer_marks": mean_of(marks),
        "material_marks": mean_of(column_of(rows, "material_marks")),
        "lexical": {
            "keyword_recall": mean_of(column_of(rows, "keyword_recall"), 3),
            "bm25_score": mean_of(column_of(rows, "bm25_score"), 3),
            "semantic_similarity": mean_of(column_of(rows, "semantic_similarity"), 3),
        },
        "tiers": {
            "high": sum(1 for m in marks if m >= 8),
            "mid": sum(1 for m in marks if 5 <= m < 8),
            "low": sum(1 for m in marks if m < 5),
        },
        "by_type": {
            t: {
                "rows": len(rs),
                "answer_marks": mean_of(column_of(rs, "answer_marks")),
                "material_marks": mean_of(column_of(rs, "material_marks")),
            }
            for t, rs in by_type.items()
        },
        "time": {
            "avg": mean_of(times, 3),
            "p95": round(times[max(0, math.ceil(0.95 * len(times)) - 1)], 3) if times else None,
        },
        "sources": {"checked": len(checked), "matched": sum(1 for r in checked if r["source_match"])},
    }
