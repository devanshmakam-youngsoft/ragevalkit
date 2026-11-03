"""The AI judge: grades answers, checks sources and writes the findings of a run."""
from ragevalkit.core.exceptions import JudgeError
from ragevalkit.services.evaluation.answer_judge.fallback_insights import finish_insights
from ragevalkit.services.evaluation.answer_judge.insights import check_insights, parse_insights
from ragevalkit.services.evaluation.answer_judge.judge import Judge
from ragevalkit.services.evaluation.answer_judge.remark_tags import (
    add_remark_tags,
    clean_answer_tags,
    clean_material_tags,
    remark_summary,
)
from ragevalkit.services.evaluation.answer_judge.run_summary_input import stats_for_llm
from ragevalkit.services.evaluation.answer_judge.schemas import Grade, SourceCheckResult

__all__ = [
    "Grade", "Judge", "JudgeError", "SourceCheckResult", "add_remark_tags", "check_insights", "clean_answer_tags",
    "clean_material_tags", "finish_insights", "parse_insights", "remark_summary", "stats_for_llm"
]
