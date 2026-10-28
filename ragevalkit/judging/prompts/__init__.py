"""Every prompt the judge uses, one file each, each exporting one named variable."""
from ragevalkit.judging.prompts.grader import grader_format, grader_prompt
from ragevalkit.judging.prompts.run_summary import run_summary_format, run_summary_prompt
from ragevalkit.judging.prompts.source_check import source_check_prompt

__all__ = ["grader_format", "grader_prompt", "run_summary_format", "run_summary_prompt", "source_check_prompt"]
