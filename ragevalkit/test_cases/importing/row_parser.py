"""Turning a table into clean test case rows, and saying which rows cannot be used and why."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

import pandas as pd

from ragevalkit.test_cases.importing.cell_values import cell_text
from ragevalkit.test_cases.importing.fields import FIELDS


@dataclass
class Problem:
    row: int          # the row number as the user sees it in the spreadsheet (header is row 1)
    reason: str
    cells: dict[str, str]

    def as_dict(self) -> dict:
        return asdict(self)


def split_labels(text: str) -> list[str]:
    """'billing; refunds | faq' -> ['billing', 'refunds', 'faq'] (case-insensitive de-dupe, order kept)."""
    seen: dict[str, str] = {}
    for part in re.split(r"[;|,\n]", text or ""):
        name = part.strip()
        if name:
            seen.setdefault(name.lower(), name[:80])
    return list(seen.values())


def parse_rows(df: pd.DataFrame, mapping: dict[str, str | None]) -> tuple[list[dict], list[Problem]]:
    """Turn a table into clean test-case rows plus a list of the rows that could not be used.

    Missing columns are filled in sensibly rather than rejected: no chat column makes every question its
    own single-turn chat, no turn column numbers the turns of each chat in file order, a blank type
    becomes "rag". Anything that is *present but wrong* is reported, never altered.
    """
    cols = {f: mapping.get(f) for f in FIELDS}
    rows: list[dict] = []
    problems: list[Problem] = []
    seen_key: dict[tuple, int] = {}
    seen_slot: dict[tuple, int] = {}
    next_turn: dict[str, int] = {}

    for index, record in enumerate(df.to_dict("records")):
        number = index + 2
        cells = {str(k): cell_text(v) for k, v in record.items()}
        if not any(cells.values()):
            continue  # a blank line

        def get(field: str) -> str:
            col = cols[field]
            return cells.get(col, "") if col else ""

        question = get("question")
        if not question:
            problems.append(Problem(number, "Question is empty", cells))
            continue

        if cols["chat_id"] is None:
            chat = "q-" + hashlib.sha1(question.encode("utf-8")).hexdigest()[:6]
        else:
            chat = get("chat_id")
            if not chat:
                problems.append(Problem(number, "Chat ID is empty", cells))
                continue

        if cols["turn_no"] is None:
            if cols["chat_id"] is None:
                turn = 1  # every question is its own chat, so a repeated question is a duplicate, not turn 2
            else:
                next_turn[chat] = next_turn.get(chat, 0) + 1
                turn = next_turn[chat]
        else:
            raw = get("turn_no")
            if raw == "":
                turn = 1
            else:
                try:
                    value = float(raw)
                    if value != int(value) or value < 1:
                        raise ValueError
                    turn = int(value)
                except ValueError:
                    problems.append(Problem(number, f"Turn number '{raw}' is not a whole number, 1 or higher", cells))
                    continue

        key, slot = (chat, turn, question), (chat, turn)
        if key in seen_key:
            where = "" if cols["chat_id"] is None else f" (chat {chat}, turn {turn})"
            problems.append(Problem(number, f"Same question as row {seen_key[key]}{where}", cells))
            continue
        if slot in seen_slot:
            problems.append(Problem(
                number, f"Chat {chat} turn {turn} is already used by row {seen_slot[slot]} with a different question", cells))
            continue
        seen_key[key], seen_slot[slot] = number, number

        rows.append({
            "row": number,
            "chat_id": chat,
            "turn_no": turn,
            "type": get("type") or "rag",
            "question": question,
            "expected_answer": get("expected_answer"),
            "expected_sources": get("expected_sources"),
            "groups": split_labels(get("groups")),
        })
    return rows, problems
