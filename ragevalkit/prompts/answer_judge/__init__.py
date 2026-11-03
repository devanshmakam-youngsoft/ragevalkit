"""Every prompt the judge uses, one file each, each exporting one named variable."""
from ragevalkit.prompts.answer_judge.grader import grader_format, grader_prompt
from ragevalkit.prompts.answer_judge.remark_tags import (
    ANSWER_TAGS,
    MATERIAL_TAGS,
    MAX_TAGS_PER_SCORE,
)
from ragevalkit.prompts.answer_judge.run_summary import run_summary_format, run_summary_prompt
from ragevalkit.prompts.answer_judge.source_check import source_check_prompt

__all__ = [
    "ANSWER_TAGS", "MATERIAL_TAGS", "MAX_TAGS_PER_SCORE", "grader_format", "grader_prompt", "run_summary_format", "run_summary_prompt", "source_check_prompt"
]
