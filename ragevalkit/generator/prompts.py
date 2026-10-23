"""The instructions given to the model, one block per kind of question.

They are written to produce questions a real person would ask, answered from the passages only, each with
quotable evidence. What the model returns is never trusted: ``checks.validate`` enforces the rules that matter.
"""
from __future__ import annotations

from ragevalkit.generator.planning import Task

COMMON_RULES = """You write test questions for an assistant that answers questions from a company's documents. A tester will put your question to that assistant and compare its reply with your expected answer, so both must be right.

You are given one or two passages from a single document.

Ground rules
- Use ONLY the passages. Every fact in the expected answer must be stated in them. Never add outside knowledge.
- Write the question the way a real person would type it into a chat box: natural, specific, in their own words.
- It must make sense to someone who has never seen the document. Never write "the passage", "the document", "the text", "this section" or "according to".
- Ask about something substantive: a rule, a number, a condition, a step, a reason, a definition. Never ask about page numbers, headings, layout or the document itself.
- Write in the same language as the passages.
- The expected answer is complete but short (one to three sentences) and states the facts the assistant must give.

Evidence
- "evidence" lists the sentences that prove the answer, copied character for character from the passages: one sentence or clause each, 8 to 30 words. Do not paraphrase, do not shorten with "...", do not change punctuation or wording."""

_SINGLE_FORMAT = 'Reply with JSON only: {"question": "...", "expected_answer": "...", "evidence": ["exact sentence from the passage"]}'

CATEGORY_RULES = {
    "direct": f"""Write ONE direct question. It asks for a fact that one passage states plainly, so a good assistant answers it by finding that sentence.

{_SINGLE_FORMAT}""",

    "indirect": f"""Write ONE indirect question. The answer is in the passages, but the question does NOT use the passage's own wording. Instead describe a real situation, use everyday words and synonyms, or require one small step of inference.

Examples of the style (a made-up topic; never reuse it):
- Passage: "Unused leave may be carried over, up to five days." -> "I haven't taken all my holiday this year. Do I lose the rest in January?"
- Passage: "Invoices unpaid after 30 days incur a 2% late fee." -> "If a customer pays six weeks after we bill them, are we allowed to charge extra?"

Never copy a phrase of four or more words from the passages into the question.

{_SINGLE_FORMAT}""",

    "multipart": """Write ONE multi-part question: a single question that asks for two or more distinct things, joined the way a person would ("What is X, and who has to approve Y?", "How long does X take, and what happens if Y?"). Each part must be answered by a DIFFERENT passage (Passage A and Passage B). The expected answer addresses every part, in order. Give at least one evidence sentence from each passage.

Reply with JSON only: {"question": "...", "expected_answer": "...", "evidence": ["sentence from Passage A", "sentence from Passage B"]}""",

    "multiturn": """Write ONE realistic conversation of exactly {turns} turns between a user and an assistant that answers from the passages.

How the conversation must work
- Turn 1 is an ordinary, self-contained question about one topic in the passages.
- Every later turn is what a real person types NEXT, after reading the assistant's last answer. It must be IMPOSSIBLE to understand or answer without the earlier turns. Refer back the way people do: "it", "that", "those", "the second one", "in that case", "and what about ...?", "why?", "what if ...?".
- Do NOT repeat the topic's name or the nouns the user already used: people say "it", not "the expense claim submission deadline".
- Each follow-up builds on something the previous answer actually said (a number, a condition, a name, an option) and moves the conversation forward: dig into a detail, ask about an exception or a consequence, compare with another case, or ask what happens next. Never just start a new, unrelated question.
- Keep the whole conversation on one topic.
- Each answer must still come from the passages. An expected answer may use what the earlier answers established.
- For every turn after the first add "depends_on": one short sentence saying exactly what from the earlier turns the question relies on.

Bad follow-up (it stands alone, so it is just another direct question): "What is the deadline for submitting expense claims?"
Good follow-up (it needs the earlier answer): "And what happens if I miss that?"

Example of the style (a made-up topic; never reuse it):
1. "How many books can I borrow at once?" -> "Up to six books, for three weeks."
2. "Can I keep them longer than that?" (depends_on: "the three-week loan period")
3. "And if somebody else is waiting for one of them?" (depends_on: "the books that may be kept longer")

Reply with JSON only: {"turns": [{"question": "...", "expected_answer": "...", "evidence": ["exact sentence"], "depends_on": ""}, ...]}""",
}

RETRY_INSTRUCTION = "That was rejected: {reason}. Write a different one that follows every rule. Reply with JSON only."


def system_prompt(category: str, turns: int) -> str:
    return COMMON_RULES + "\n\n" + CATEGORY_RULES[category].replace("{turns}", str(turns))


def build_messages(task: Task, turns: int, avoid: list[str]) -> list[dict]:
    """The conversation sent to the model for one task: the rules, the passages, and what is already written."""
    parts = [f"[Passage {'AB'[i]}] ({c.label})\n{c.text}" for i, c in enumerate(task.chunks[:2])]
    user = "\n\n".join(parts)
    if avoid:
        user += "\n\nQuestions already written (do not repeat or closely resemble them):\n" + "\n".join(f"- {q}" for q in avoid[-12:])
    return [{"role": "system", "content": system_prompt(task.category, turns)}, {"role": "user", "content": user}]
