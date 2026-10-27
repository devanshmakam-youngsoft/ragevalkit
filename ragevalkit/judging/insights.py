"""Reading and checking the findings a model writes for a run: watch-outs, each paired with its suggestion."""
import json

_ITEM_TEXT_KEYS = ("text", "suggestion", "pitfall", "watch_out", "issue", "action", "title", "description", "summary")


_NO_ITEM = {"none", "none.", "n/a", "na", "nothing", "-"}


# models rename keys now and then; each list is read under any of these names
_LIST_NAMES = {
    "pitfalls": ("pitfalls", "watch_outs", "watchouts", "issues", "risks", "problems"),
    "suggestions": ("suggestions", "suggestion", "recommendations", "next_steps", "actions", "improvements"),
}


# a finding pairs one weakness with the action that answers it; each part is read under any of these names
_ITEM_LIST_NAMES = ("items", "findings", "insights", "points", "pairs")


_PAIR_NAMES = {
    "watch_out": ("watch_out", "watchout", "pitfall", "issue", "risk", "problem", "weakness", "finding"),
    "suggestion": ("suggestion", "action", "recommendation", "next_step", "fix"),
}


def _normal_keys(d: dict) -> dict:
    return {str(k).lower().replace("-", "_").replace(" ", "_"): v for k, v in d.items()}


def _read_pairs(data: dict, limit: int = 5) -> list[dict]:
    """The reply's findings as [{"watch_out": ..., "suggestion": ...}] (either part may be empty)."""
    entries = next((data[n] for n in _ITEM_LIST_NAMES if isinstance(data.get(n), list) and data[n]), [])
    pairs = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry = _normal_keys(entry)
        part = {key: next((_clean_items(entry.get(n), 1) for n in names if _clean_items(entry.get(n), 1)), [""])[0]
                for key, names in _PAIR_NAMES.items()}
        if part["watch_out"] or part["suggestion"]:
            pairs.append(part)
    return pairs[:limit]


def _clean_items(value, limit: int = 6) -> list[str]:
    """Short plain-text items from whatever shape the model used: a list of strings, one string, or objects."""
    if isinstance(value, (str, dict)):
        value = [value]
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for v in value:
        if isinstance(v, dict):
            v = next((v[k] for k in _ITEM_TEXT_KEYS if isinstance(v.get(k), str) and v[k].strip()), "")
        text = str(v).strip().lstrip("-•* ").strip()
        if text and text.lower() not in _NO_ITEM and text[:400] not in items:
            items.append(text[:400])
    return items[:limit]


def parse_insights(raw: str | None) -> dict | None:
    """Read the model's {"pitfalls": [...], "suggestions": [...]} reply, tolerating code fences and
    surrounding prose. Returns None when it holds neither list."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start:end + 1])
        except ValueError:
            return None
    if not isinstance(data, dict):
        return None
    data = _normal_keys(data)
    pairs = _read_pairs(data)
    if pairs:
        return {"pitfalls": [p["watch_out"] for p in pairs if p["watch_out"]],
                "suggestions": [p["suggestion"] for p in pairs if p["suggestion"]], "items": pairs}
    found = {key: next((items for items in (_clean_items(data.get(name)) for name in names) if items), []) for key, names in _LIST_NAMES.items()}
    return found if found["pitfalls"] or found["suggestions"] else None


def check_insights(raw: str | None) -> tuple[dict | None, str]:
    """A summary reply in which every watch-out has its own suggestion, or the reason it does not (worded so it
    can be sent back). Two parallel lists that line up one to one are accepted and paired up."""
    found = parse_insights(raw)
    if found is None:
        return None, 'it was not a JSON object with an "items" list of {"watch_out", "suggestion"} pairs'
    items = found.get("items")
    if items is None:
        if not found["pitfalls"]:
            return None, '"pitfalls" was empty: list 1 to 5 watch-outs, or one item saying nothing is wrong'
        if not found["suggestions"]:
            return None, ('"suggestions" was empty: give a concrete next step for each watch-out. '
                          "If nothing is wrong, suggest how to test the assistant harder or what to keep an eye on")
        if len(found["pitfalls"]) != len(found["suggestions"]):
            return None, 'every watch-out needs its own suggestion: reply with "items", each holding one "watch_out" and the "suggestion" that answers it'
        items = [{"watch_out": w, "suggestion": s} for w, s in zip(found["pitfalls"], found["suggestions"])]
    for number, item in enumerate(items, 1):
        if not item["watch_out"]:
            return None, f'item {number} has no "watch_out"'
        if not item["suggestion"]:
            return None, (f'item {number} has no "suggestion": every watch-out needs the one concrete next step that answers it. '
                          "If nothing is wrong, the suggestion is how to test the assistant harder or what to keep an eye on")
    return {"pitfalls": [i["watch_out"] for i in items], "suggestions": [i["suggestion"] for i in items], "items": items}, ""
