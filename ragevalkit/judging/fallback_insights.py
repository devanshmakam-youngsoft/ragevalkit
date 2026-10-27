"""Findings read straight from a run's numbers, for when the model left a watch-out without a suggestion."""
from ragevalkit.run_summary.nodes import summary_nodes


def default_suggestions(summary: dict, rows: list[dict]) -> list[str]:
    """Next steps read straight from the run's numbers, for when the model's summary came back without any.
    Never empty: a clean run is told how to test harder."""
    out: list[str] = []
    failed = summary.get("failed_rows") or 0
    if failed:
        out.append(f"Open the {failed} failed question{'s' if failed != 1 else ''} in the results to see what went wrong before comparing versions.")
    low = ((summary.get("scores") or {}).get("tiers") or {}).get("low", 0)
    if low:
        out.append("Open the weak answers (filter the results by Weak) and compare each with the expected answer to see what is missing.")
    sources = (summary.get("scores") or {}).get("sources") or {}
    if sources.get("checked") and sources.get("matched", 0) < sources["checked"]:
        out.append("Some expected documents were not retrieved: check that they are indexed and that the search finds them.")
    material = summary.get("avg_material_marks")
    if material is not None and material < 7:
        out.append("Context quality is low, so the right passages are often not found: review how documents are split and how the search is set up.")
    total = summary.get("avg_total_time") or 0
    slow = max(summary_nodes(summary), key=lambda n: n["avg"], default=None)
    if slow and total and slow["avg"] >= 0.5 * total:
        out.append(f"{slow['name'].replace('_', ' ').capitalize()} takes {slow['avg'] / total:.0%} of the response time: start there to make answers faster.")
    if not out:
        out.append("Keep this version as the baseline and add harder test cases (indirect and multi-turn questions) to find where it breaks.")
    return out[:3]


_GENERIC_NEXT_STEP = "Open the related questions in the results to see what went wrong, then adjust the assistant or the test case."


def finish_insights(insights: dict, summary: dict, rows: list[dict]) -> dict:
    """The summary as stored: ``items`` pairing every watch-out with a suggestion, plus the two plain lists.

    A watch-out the model left without a suggestion gets one read from the run's numbers (or a general next step),
    so the page never shows a watch-out with nothing to do about it."""
    items = [dict(i) for i in insights.get("items") or []]
    if not items:                                   # parallel lists from an older-style reply: pair them by position
        pits, sugs = insights.get("pitfalls") or [], insights.get("suggestions") or []
        items = [{"watch_out": pits[i] if i < len(pits) else "", "suggestion": sugs[i] if i < len(sugs) else ""}
                 for i in range(max(len(pits), len(sugs)))]
    spare = [s for s in default_suggestions(summary, rows) if s not in {i["suggestion"] for i in items}]
    for item in items:
        if item["watch_out"] and not item["suggestion"]:
            item["suggestion"] = spare.pop(0) if spare else _GENERIC_NEXT_STEP
    items = [i for i in items if i["watch_out"] or i["suggestion"]]
    return {"items": items, "pitfalls": [i["watch_out"] for i in items if i["watch_out"]],
            "suggestions": [i["suggestion"] for i in items if i["suggestion"]]}
