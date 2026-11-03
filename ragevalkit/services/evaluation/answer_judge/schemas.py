"""The shapes of what the judge returns."""
from pydantic import BaseModel, Field, field_validator

from ragevalkit.services.evaluation.answer_judge.remark_tags import (
    clean_answer_tags,
    clean_material_tags,
)


class Grade(BaseModel):
    """The judge's marks and reasons for one generated answer, each mark out of 10.

    ``material_marks`` is None when the question needs no retrieval (a conversational turn).
    """
    answer_marks: int = Field(ge=0, le=10)
    answer_comment: str
    material_marks: int | None = Field(default=None, ge=0, le=10)
    material_comment: str = ""
    answer_tags: list[str] = []      # short reasons for the answer mark, from the fixed list in prompts/answer_judge/remark_tags.py
    material_tags: list[str] = []    # the same for the context mark

    @field_validator("answer_tags", mode="before")
    @classmethod
    def _known_answer_tags(cls, value: object) -> list[str]:
        """Keep only tags from the fixed list, so a reply with an odd word is still a valid grade."""
        return clean_answer_tags(value)

    @field_validator("material_tags", mode="before")
    @classmethod
    def _known_material_tags(cls, value: object) -> list[str]:
        """Keep only tags from the fixed list, so a reply with an odd word is still a valid grade."""
        return clean_material_tags(value)


class SourceCheckResult(BaseModel):
    """Outcome of an LLM source check, resolved against the AND/OR groups in expected_sources."""
    source_match: bool
    matched_sources: list[str] = []   # one retrieved alternative per satisfied group
    missing_sources: list[str] = []   # the full group string for each unsatisfied group
    source_score: int = Field(ge=0, le=10)
    source_comment: str = ""
