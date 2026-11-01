"""Every prompt the question writer uses, one file each, each exporting one named variable."""
from ragevalkit.prompts.testcase_generator.common_rules import common_rules
from ragevalkit.prompts.testcase_generator.direct import direct_prompt
from ragevalkit.prompts.testcase_generator.indirect import indirect_prompt
from ragevalkit.prompts.testcase_generator.multipart import multipart_prompt
from ragevalkit.prompts.testcase_generator.multiturn import multiturn_prompt
from ragevalkit.prompts.testcase_generator.retry import retry_instruction
from ragevalkit.prompts.testcase_generator.single_reply_format import single_reply_format

CATEGORY_PROMPTS = {
    "direct": direct_prompt,
    "indirect": indirect_prompt,
    "multipart": multipart_prompt,
    "multiturn": multiturn_prompt,
}

__all__ = [
    "CATEGORY_PROMPTS", "common_rules", "direct_prompt", "indirect_prompt", "multipart_prompt", "multiturn_prompt",
    "retry_instruction", "single_reply_format",
]
