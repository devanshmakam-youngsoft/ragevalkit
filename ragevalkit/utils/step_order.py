"""The pipeline steps ("nodes") a run recorded, and the order they ran in."""
from ragevalkit.utils.score_math import is_nan

METRIC_AVGS = {"answer_marks", "material_marks", "total_time", "keyword_recall", "bm25_score", "semantic_similarity"}


def node_order(rows: list[dict]) -> list[str]:
    """Return the step names found in the rows' ``node_timings`` in the order they ran.

    Rows can record different steps (a step may be skipped for some questions), so the names are merged:
    each new name is placed right after the step that preceded it in the row where it first appeared.
    """
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
    """Return ``{"name", "avg"}`` for each pipeline step average (``avg_<step>``) in a run summary.

    The built-in metric averages in ``METRIC_AVGS`` and missing values are left out.
    """
    return [
        {"name": k[4:], "avg": v}
        for k, v in summary.items()
        if k.startswith("avg_") and k[4:] not in METRIC_AVGS and v is not None and not is_nan(v)
    ]
