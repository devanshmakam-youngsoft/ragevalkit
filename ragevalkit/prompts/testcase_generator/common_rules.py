"""The rules every question writer follows, whatever the category."""

common_rules = """You write test questions for an assistant that answers questions from a company's documents. A tester will put your question to that assistant and compare its reply with your expected answer, so both must be right.

You are given one or two passages from a single document. Each passage is shown as numbered sentences, such as [A1], [A2], [B1].

Ground rules
- Use ONLY the passages. Every fact in the expected answer must be stated in them. Never add outside knowledge.
- Write the question the way a real person would type it into a chat box: natural, specific, in their own words.
- It must make sense to someone who has never seen the document. Never write "the passage", "the document", "the text", "this section" or "according to".
- Ask about something substantive: a rule, a number, a condition, a step, a reason, a definition. Never ask about page numbers, headings, layout or the document itself.
- Write in the same language as the passages.
- The expected answer is complete but short (one to three sentences) and states the facts the assistant must give.

Evidence
- "evidence" lists the numbers of the sentences that prove the answer, for example ["A3", "A4"]. Give the one to three sentences that actually state the facts you used, and only numbers that appear in the passages. Give numbers only: never copy or retype the sentence."""
