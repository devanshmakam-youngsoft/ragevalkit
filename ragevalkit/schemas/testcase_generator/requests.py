"""Request bodies for writing test cases from documents."""
from pydantic import BaseModel


class TurnText(BaseModel):
    question: str
    expected_answer: str


class ItemEdit(BaseModel):
    turns: list[TurnText]


class Approval(BaseModel):
    item_ids: list[str] | None = None   # default: everything left in the batch
