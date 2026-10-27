"""The instructions for writing one direct question."""
from ragevalkit.generation.prompts.single_reply_format import single_reply_format


direct_prompt = f"""Write ONE direct question. It asks for a fact that one passage states plainly, so a good assistant answers it by finding that sentence.

{single_reply_format}"""
