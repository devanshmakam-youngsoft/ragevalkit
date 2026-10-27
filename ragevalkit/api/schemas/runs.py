"""Request bodies for evaluation runs."""
from pydantic import BaseModel


class SelectionBody(BaseModel):
    """What a run would execute: groups and/or individually picked test cases."""

    group_ids: list[str] = []
    tc_ids: list[str] = []
    status_filter: str = "active"
    include_context: bool = True
