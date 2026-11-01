"""Request bodies for evaluation runs."""
from pydantic import BaseModel


class SelectionBody(BaseModel):
    """What a run would execute: groups and/or individually picked test cases."""

    group_ids: list[str] = []       # every test case carrying one of these groups, filtered by ``status_filter``
    tc_ids: list[str] = []          # individual test cases, included whatever their status
    status_filter: str = "active"   # "active", "inactive" or "all"; applies to the cases pulled in by ``group_ids``
    include_context: bool = True    # add the earlier turns of each selected chat so a conversation can be replayed
