"""The facts about a run that the judge reads before writing its findings."""
import statistics

from ragevalkit.run_summary.nodes import summary_nodes


def stats_for_llm(summary: dict, rows: list[dict]) -> str:
    by_type: dict[str, list[float]] = {}
    for r in rows:
        if r.get("answer_marks") is not None:
            by_type.setdefault(r["type"], []).append(r["answer_marks"])
    type_line = ", ".join(f"{t}: {statistics.fmean(v):.1f} over {len(v)} rows" for t, v in by_type.items())
    worst = sorted((r for r in rows if r.get("answer_marks") is not None), key=lambda r: r["answer_marks"])[:3]
    worst_lines = "\n".join(
        f"- [{r['answer_marks']}/10] {r['question'][:100]} :: {str(r.get('answer_remarks'))[:160]}"
        for r in worst
    )
    total_time = summary.get("avg_total_time") or 0
    nodes = ", ".join(
        f"{n['name']}={n['avg']}s" + (f" ({n['avg'] / total_time:.0%} of the response time)" if total_time else "")
        for n in summary_nodes(summary)
    )
    group_line = ", ".join(
        f"{g}: answer {st['avg_answer_marks']}, context {st['avg_material_marks']} over {st['total_rows']} rows"
        for g, st in (summary.get("group_stats") or {}).items()
    ) or "n/a"
    sources = (summary.get("scores") or {}).get("sources") or {}
    source_line = (
        f"{sources['matched']} of {sources['checked']} rows retrieved all expected sources"
        if sources.get("checked") else "no source checks"
    )
    tiers = (summary.get("scores") or {}).get("tiers") or {}
    return (
        f"Score tiers (answer): {tiers.get('high', 0)} high (8+), {tiers.get('mid', 0)} middling (5-7), {tiers.get('low', 0)} low (<5)\n"
        f"By group: {group_line}\nSource checks: {source_line}\n"
        f"Rows: {summary['total_rows']} (failed: {summary['failed_rows']})\n"
        f"Avg answer marks: {summary['avg_answer_marks']}/10, avg material marks: {summary['avg_material_marks']}/10\n"
        f"Key words found in answers (0 to 1): {summary['avg_keyword_recall']}; meaning match with the expected answer (0 to 1): {summary['avg_semantic_similarity']}\n"
        f"Avg end-to-end time: {summary['avg_total_time']}s; time per step: {nodes}\n"
        f"(Step names: retrieval and faiss_search = finding documents; llm = the AI model writing the answer.)\n"
        f"Answer marks by type: {type_line}\nLowest scoring rows:\n{worst_lines}"
    )
