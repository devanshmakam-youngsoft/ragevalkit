"""Request bodies for test cases."""
from pydantic import BaseModel


class TestCaseUpdate(BaseModel):
    chat_id: str | None = None
    turn_no: int | None = None
    question: str | None = None
    expected_answer: str | None = None
    expected_sources: str | None = None
    type: str | None = None


class TestCaseStatusUpdate(BaseModel):
    status: str  # "active" | "inactive"


class BulkStatusUpdate(BaseModel):
    tc_ids: list[str]
    status: str  # "active" | "inactive"


class TestCaseIds(BaseModel):
    tc_ids: list[str]


class TestCaseGroups(BaseModel):
    group_ids: list[str]


class CreateTestCase(BaseModel):
    chat_id: str
    turn_no: int
    question: str
    expected_answer: str
    type: str = "rag"
    expected_sources: str = ""
    group_id: str | None = None
    dataset_id: str | None = None  # backward-compat alias
