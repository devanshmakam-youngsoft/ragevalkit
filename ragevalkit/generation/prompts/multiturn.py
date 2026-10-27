"""The instructions for writing one multiturn question."""

multiturn_prompt = """Write ONE realistic conversation of exactly {turns} turns between a user and an assistant that answers from the passages.

How the conversation must work
- Turn 1 is an ordinary, self-contained question about one topic in the passages.
- Every later turn is what a real person types NEXT, after reading the assistant's last answer. It must be IMPOSSIBLE to understand or answer without the earlier turns. Refer back the way people do: "it", "that", "those", "the second one", "in that case", "and what about ...?", "why?", "what if ...?".
- Do NOT repeat the topic's name or the nouns the user already used: people say "it", not "the expense claim submission deadline".
- Each follow-up builds on something the previous answer actually said (a number, a condition, a name, an option) and moves the conversation forward: dig into a detail, ask about an exception or a consequence, compare with another case, or ask what happens next. Never just start a new, unrelated question.
- Keep the whole conversation on one topic.
- Each answer must still come from the passages. An expected answer may use what the earlier answers established. Every turn has its own "evidence": the numbers of the sentences that support THAT turn's answer.
- For every turn after the first add "depends_on": one short sentence saying exactly what from the earlier turns the question relies on.
- Check before you reply: read each follow-up on its own, as if it were the first message. If it makes sense alone, rewrite it so it refers back.

Bad follow-up (it stands alone, so it is just another direct question): "What is the deadline for submitting expense claims?"
Good follow-up (it needs the earlier answer): "And what happens if I miss that?"

Example of the style (a made-up topic; never reuse it):
1. "How many books can I borrow at once?" -> "Up to six books, for three weeks."
2. "Can I keep them longer than that?" (depends_on: "the three-week loan period")
3. "And if somebody else is waiting for one of them?" (depends_on: "the books that may be kept longer")

Reply with JSON only: {"turns": [{"question": "...", "expected_answer": "...", "evidence": ["A3"]}, {"question": "...", "expected_answer": "...", "evidence": ["A5"], "depends_on": "..."}, ...]}"""
