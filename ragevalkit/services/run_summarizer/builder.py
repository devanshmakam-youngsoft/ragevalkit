"""The summary saved with every run."""
from datetime import datetime, timezone

from ragevalkit.services.run_summarizer.scores import build_scores
from ragevalkit.utils import build_case_scores, column_of, mean_of, node_order


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
    """Build the summary dict that is saved with a run from its result rows.

    Averages skip rows that have no value for a metric, so a metric nobody scored is ``None`` rather than 0.
    The time each pipeline step took is added as one ``avg_<step name>`` key per step.

    Args:
        version: Label of the run (the version of the application under test).
        rows: One result dict per evaluated question, as produced by the evaluation runner.
        started: When the run began; must be timezone-aware, as the duration is measured against the current UTC time.
        dataset_name: Display name of the dataset or test case selection that was run.
        judge_model: Model that graded the answers, kept so the dashboard can warn when it changed between runs.
        question_fingerprint: Fingerprint of the question set, kept so the dashboard can warn when it changed.
        dataset_id: ID of the library dataset the run used, or an empty string if it had none.

    Returns:
        The summary: run identity and totals (``version``, ``date``, ``duration_seconds``, ``total_rows``,
        ``failed_rows``), the ``avg_*`` metrics, ``scores`` and ``case_scores``, and an empty ``comment``.
    """
    finished =datetime.now(timezone.utc)
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
