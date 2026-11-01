"""The instructions for the findings of a run: each watch-out paired with the suggestion that answers it."""


run_summary_prompt = """You are reviewing the results of one evaluation run of an AI assistant, for a business reader who is not technical.
The reader already sees the headline averages (answer quality, context quality, speed) on screen, so do NOT restate
them and do not open with an overall verdict. Point out what needs attention and what to do about it, using the numbers
provided only as evidence.

Give 2-5 findings, the most important first. Each finding has two parts that belong together:
watch_out: ONE concrete weakness and the evidence for it: which group or question type scored lowest, which
questions scored poorly and what their answers were missing, which step takes most of the response time, questions that
failed, expected documents that were not found. Name the actual group or question when you can.
suggestion: the one concrete action that answers THAT watch-out, never empty, starting with a verb ("Add ...",
"Check ...", "Rewrite ..."). It must make sense read right after its watch-out and must not repeat it.
If nothing is really wrong, give one finding whose watch_out says so plainly and whose suggestion says how to test the
assistant harder or what to keep an eye on.

Example of one finding: {"watch_out": "The multi-turn group scores lowest (5.8): follow-up questions lose track of the
earlier answer.", "suggestion": "Add the previous answer to the prompt for each follow-up question and run this group
again."}

Rules: plain everyday language, no jargon. Never write BM25, embeddings, recall, semantic similarity, retrieval, LLM,
token or latency; say "key words", "meaning", "finding documents", "the AI model" and "response time" instead. One
sentence per part, with at most one number in it. No markdown. Use only the facts provided and do not invent causes the
data does not show."""


# Appended to the summary prompt whether or not the developer replaced the wording above, so the
# dashboard can always show the result as bullet lists.
run_summary_format = """

Respond ONLY with a JSON object of exactly this shape: {"items": [{"watch_out": "...", "suggestion": "..."}]}.
There must be at least one item, and every item needs both parts. Each part is a single sentence."""
