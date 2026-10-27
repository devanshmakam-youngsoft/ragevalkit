"""The shapes of what the judge returns."""
from pydantic import BaseModel, Field


class Grade(BaseModel):
    answer_marks: int = Field(ge=0, le=10)
    answer_comment: str
    material_marks: int | None = Field(default=None, ge=0, le=10)
    material_comment: str = ""


class SourceCheckResult(BaseModel):
    """Outcome of an LLM source check, resolved against the AND/OR groups in expected_sources."""
    source_match: bool
    matched_sources: list[str] = []   # one retrieved alternative per satisfied group
    missing_sources: list[str] = []   # the full group string for each unsatisfied group
    source_score: int = Field(ge=0, le=10)
    source_comment: str = ""
