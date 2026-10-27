"""How a test case is identified and ordered."""
import hashlib
import re


def case_id_for(chat_id: str, turn_no: int, question: str) -> str:
    """Stable test case ID — keyed by content so the same question always gets the same ID."""
    key = f"{chat_id}|{turn_no}|{question.strip()}"
    return "tc_" + hashlib.sha256(key.encode()).hexdigest()[:12]


def natural_sort_key(text) -> list:
    """Sort key that orders 'c2' before 'c10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(text))]


def case_order(tc: dict):
    return (natural_sort_key(tc.get("chat_id", "")), tc.get("turn_no", 0))


def latest_versions(records: list[dict]) -> dict[str, dict]:
    """Collapse versioned test-case records to the newest one per tc_id."""
    by_id: dict[str, dict] = {}
    for rec in records:
        cur = by_id.get(rec["tc_id"])
        if cur is None or rec["version"] > cur["version"]:
            by_id[rec["tc_id"]] = rec
    return by_id
