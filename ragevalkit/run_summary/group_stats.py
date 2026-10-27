"""Per-group score averages for the groups a run covered."""
from ragevalkit.run_summary.averages import column_of, mean_of
from ragevalkit.test_cases.identity import case_id_for


def build_group_stats(store, group_names: list[str], rows: list[dict]) -> dict:
    """Per-group score averages for the groups a run covered.

    A test case can sit in several groups; it is then counted once in the run's overall scores and
    once in *each* of its groups, so every group's numbers describe exactly its own cases. Group
    membership comes from the labels each row carried when it ran (falling back to the library's
    current labels for rows saved before that was recorded)."""
    if not group_names:
        return {}
    if not all("groups" in r for r in rows):
        names_of = store.group_names_by_test_case()
        rows = [
            {**r, "groups": r.get("groups") or sorted(names_of.get(
                r.get("tc_id") or case_id_for(str(r.get("chat_id", "")), int(r.get("turn_no") or 1), str(r.get("question", ""))),
                set()))}
            for r in rows
        ]
    stats: dict = {}
    for gname in group_names:
        group_rows = [r for r in rows if gname in (r.get("groups") or [])]
        if group_rows:
            stats[gname] = {
                "avg_answer_marks": mean_of(column_of(group_rows, "answer_marks")),
                "avg_material_marks": mean_of(column_of(group_rows, "material_marks")),
                "avg_total_time": mean_of(column_of(group_rows, "total_time_taken"), 3),
                "avg_keyword_recall": mean_of(column_of(group_rows, "keyword_recall"), 3),
                "avg_bm25_score": mean_of(column_of(group_rows, "bm25_score"), 3),
                "avg_semantic_similarity": mean_of(column_of(group_rows, "semantic_similarity"), 3),
                "total_rows": len(group_rows),
                "failed_rows": sum(1 for r in group_rows if r.get("status") != "ok"),
            }
    return stats
