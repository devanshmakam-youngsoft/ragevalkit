"""Request bodies for test cases."""
from pydantic import BaseModel


class TestCaseUpdate(BaseModel):
    """The fields to change when editing a test case; any field left out or null keeps its value."""

    chat_id: str | None = None          # cannot be empty
    turn_no: int | None = None          # position in the chat, 1 or higher
    question: str | None = None         # cannot be empty
    expected_answer: str | None = None
    expected_sources: str | None = None  # files the answer should come from: "|" joins required files, "," alternatives
    type: str | None = None             # "rag" or "non-rag"


class TestCaseStatusUpdate(BaseModel):
    """The new status for one test case."""

    status: str  # "active" | "inactive"


class BulkStatusUpdate(BaseModel):
    """The test cases to activate or deactivate, and the status to give them."""

    tc_ids: list[str]
    status: str  # "active" | "inactive"


class TestCaseIds(BaseModel):
    """A list of test cases to act on together."""

    tc_ids: list[str]


class TestCaseGroups(BaseModel):
    """The complete set of groups a test case should carry."""

    group_ids: list[str]            # replaces the groups it has now; an empty list removes them all


class CreateTestCase(BaseModel):
    """A single test case to add to the library."""

    chat_id: str                    # the conversation this question belongs to; turns of one chat share it
    turn_no: int                    # position in the chat, starting at 1
    question: str
    expected_answer: str
    type: str = "rag"               # "rag" (answer must come from the documents) or "non-rag" (no retrieval expected)
    expected_sources: str = ""      # files the answer should come from: "|" joins required files, "," alternatives
    group_id: str | None = None     # also put the test case in this group
    dataset_id: str | None = None  # backward-compat alias
