"""Every prompt the question writer uses, one file each, each exporting one named variable."""
from ragevalkit.generation.prompts.common_rules import common_rules
from ragevalkit.generation.prompts.direct import direct_prompt
from ragevalkit.generation.prompts.indirect import indirect_prompt
from ragevalkit.generation.prompts.multipart import multipart_prompt
from ragevalkit.generation.prompts.multiturn import multiturn_prompt
from ragevalkit.generation.prompts.retry import retry_instruction
from ragevalkit.generation.prompts.single_reply_format import single_reply_format

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
