"""The instructions for writing one indirect question."""
from ragevalkit.generation.prompts.single_reply_format import single_reply_format

indirect_prompt = f"""Write ONE indirect question. The answer is in the passages, but the question does NOT use the passage's own wording. Instead describe a real situation, use everyday words and synonyms, or require one small step of inference.

Examples of the style (a made-up topic; never reuse it):
- Passage: "Unused leave may be carried over, up to five days." -> "I haven't taken all my holiday this year. Do I lose the rest in January?"
- Passage: "Invoices unpaid after 30 days incur a 2% late fee." -> "If a customer pays six weeks after we bill them, are we allowed to charge extra?"

Never copy a phrase of four or more words from the passages into the question.

{single_reply_format}"""
