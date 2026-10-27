"""The pipeline steps ("nodes") a run recorded, and the order they ran in."""
from ragevalkit.run_summary.averages import is_nan

METRIC_AVGS = {"answer_marks", "material_marks", "total_time", "keyword_recall", "bm25_score", "semantic_similarity"}


def node_order(rows: list[dict]) -> list[str]:
    order: list[str] = []
    for r in rows:
        seq = list((r.get("node_timings") or {}).keys())
        for i, name in enumerate(seq):
            if name in order:
                continue
            if i == 0:
                order.insert(0, name)
            else:
                order.insert(order.index(seq[i - 1]) + 1, name)
    return order


def summary_nodes(summary: dict) -> list[dict]:
    return [
        {"name": k[4:], "avg": v}
        for k, v in summary.items()
        if k.startswith("avg_") and k[4:] not in METRIC_AVGS and v is not None and not is_nan(v)
    ]
