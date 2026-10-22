GRADER_PROMPT = """You are a strict but fair evaluator of an AI assistant or RAG system.
You receive a Question, the Expected Answer (written by a human), the system's Generated Answer, and the
Material (document excerpts or context) the system retrieved.

Wording may differ from the expected answer; judge meaning, not phrasing.

answer_marks (integer 0-10): how well the Generated Answer matches the Expected Answer in facts and intent.
  10 = fully correct and complete; 7-9 = correct with minor omissions/extra detail; 4-6 = partially correct;
  1-3 = mostly wrong or missing the key point; 0 = wrong, hallucinated, empty, or generation failed.
  Penalise facts that are not supported by the Material (hallucination) or that contradict the Expected Answer.
  If the Expected Answer describes a behaviour (e.g. greet politely, decline off-topic), judge that behaviour.

material_marks (integer 0-10, or null): does the Material contain enough information to support the Expected
  Answer? 10 = everything needed is present; 5 = some of it; 0 = nothing relevant. Use null when no material
  applies (conversational / off-topic replies where no retrieval is expected).

Respond ONLY with a JSON object with these exact keys:
  answer_marks, answer_comment, material_marks, material_comment

Give a one or two sentence comment for each score."""

SOURCE_CHECK_PROMPT = """You are verifying whether a RAG system retrieved the right source documents.

Expected sources: documents the system SHOULD have retrieved to answer the question correctly.
Retrieved sources: documents the system ACTUALLY retrieved.

For each expected source, decide if it was retrieved. A match requires the retrieved source to be
the SAME specific document. Apply these rules strictly:

ALLOWED to ignore (these do not make two sources different):
  - file extension   ("ai_listener" matches "ai_listener.pdf")
  - folder path prefix   ("docs/ai_listener.pdf" matches "ai_listener")
  - capitalisation and spaces/underscores   ("AI Listener" matches "ai_listener")

NOT allowed to ignore (these make two sources different documents — do NOT match them):
  - year, date, or version number   ("annual_report_2025" ≠ "annual_report_2026")
  - any numeric or alphabetic suffix that distinguishes two editions of the same document type
  - different document names even if they cover a similar topic

When in doubt about whether a difference is meaningful, treat the sources as different.

Judge each expected source independently; do not try to combine them. The expected list may contain
alternatives for the same document, and the caller decides which combinations are required.

Respond ONLY with a JSON object with exactly these keys:
  matched_sources  — list of expected sources that WERE retrieved (use the exact strings from the expected list)
  missing_sources  — list of expected sources that were NOT retrieved
  source_comment   — one sentence explaining the result"""

SUMMARY_PROMPT = """You are reviewing the results of one evaluation run of an AI system.
Write a 3-4 sentence plain-text assessment: overall answer and material quality, where it is strong or weak
(by question type if visible), which pipeline node dominates latency, and one concrete improvement to try.
Do not use bullet points or markdown. Be specific and use the numbers provided."""
