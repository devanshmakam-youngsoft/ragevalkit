"""The instructions that make the judge decide which expected documents were retrieved."""


source_check_prompt = """You are verifying whether a RAG system retrieved the right source documents.

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
