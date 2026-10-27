"""The summary saved with every run."""
from datetime import datetime, timezone

from ragevalkit.run_summary.averages import column_of, mean_of
from ragevalkit.run_summary.case_scores import build_case_scores
from ragevalkit.run_summary.nodes import node_order
from ragevalkit.run_summary.scores import build_scores


def build_summary(
    version: str,
    rows: list[dict],
    started: datetime,
    dataset_name: str,
    *,
    judge_model: str = "",
    question_fingerprint: str = "",
    dataset_id: str = "",
) -> dict:
    finished = datetime.now(timezone.utc)
    summary = {
        "version": version,
        "date": started.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 1),
        "dataset": dataset_name,
        "dataset_id": dataset_id,
        "total_rows": len(rows),
        "failed_rows": sum(1 for r in rows if r["status"] != "ok"),
        "avg_answer_marks": mean_of(column_of(rows, "answer_marks")),
        "avg_material_marks": mean_of(column_of(rows, "material_marks")),
        "avg_total_time": mean_of(column_of(rows, "total_time_taken"), 3),
        "avg_keyword_recall": mean_of(column_of(rows, "keyword_recall"), 3),
        "avg_bm25_score": mean_of(column_of(rows, "bm25_score"), 3),
        "avg_semantic_similarity": mean_of(column_of(rows, "semantic_similarity"), 3),
        # Traceability fields — enables "did the questions change?" dashboard warnings.
        "judge_model": judge_model,
        "question_fingerprint": question_fingerprint,
        "comment": "",
        "scores": build_scores(rows),
        "case_scores": build_case_scores(rows),
    }
    for n in node_order(rows):
        summary[f"avg_{n}"] = mean_of([(r.get("node_timings") or {}).get(n) for r in rows], 3)
    return summary
