"""The instructions for writing one multipart question."""

multipart_prompt = """Write ONE multi-part question: a single question that asks for two or more distinct things, joined the way a person would ("What is X, and who has to approve Y?", "How long does X take, and what happens if Y?"). Each part must be answered by a DIFFERENT passage (Passage A and Passage B). The expected answer addresses every part, in order. Cite at least one sentence from each passage.

Reply with JSON only: {"question": "...", "expected_answer": "...", "evidence": ["A2", "B4"]}"""
