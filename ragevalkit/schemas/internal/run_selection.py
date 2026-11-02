"""The test cases a run would execute."""
from dataclasses import dataclass, field

import pandas as pd

from ragevalkit.utils import clean_expected_sources, compute_fingerprint


@dataclass
class RunSelection:
    """The test cases a run would execute, as resolved by EvalStore.resolve_selection()."""
    df: "pd.DataFrame"
    selected: int          # distinct cases the caller asked for (via groups and/or ids)
    context: int           # earlier turns added so multi-turn chats keep their history
    missing: int           # requested tc_ids that do not exist
    group_names: list[str] = field(default_factory=list)
    collisions: list[dict] = field(default_factory=list)  # distinct cases sharing a chat + turn

    @property
    def total(self) -> int:
        """The number of questions the run would ask: the selected cases plus the context turns."""
        return len(self.df)


def cases_to_dataframe(cases: list[dict], group_names_of: dict[str, list[str]] | None = None) -> "pd.DataFrame":
    """Test cases as the DataFrame the runner consumes. ``tc_id`` and the names of the groups each case
    belonged to *at run time* ride along into every receipt, so later group scores never depend on
    what the groups look like then."""
    if not cases:
        return pd.DataFrame()
    rows = []
    for tc in cases:
        row: dict = {
            "chat_id": str(tc["chat_id"]),
            "turn_no": int(tc["turn_no"]),
            "type": tc.get("type", ""),
            "question": tc["question"],
            "expected_answer": tc["expected_answer"],
            "tc_id": tc["tc_id"],
            "groups": tuple((group_names_of or {}).get(tc["tc_id"], ())),
        }
        es = clean_expected_sources(tc.get("expected_sources", ""))
        if es:
            row["expected_sources"] = es
        rows.append(row)
    df = pd.DataFrame(rows)
    df.attrs["fingerprint"] = compute_fingerprint(df)
    return df
