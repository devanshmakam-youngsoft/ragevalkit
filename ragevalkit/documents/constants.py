"""Limits and settings for reading documents."""


SUPPORTED_SUFFIXES = (".pdf", ".docx", ".txt", ".md", ".markdown")


TARGET_CHARS = 3500          # size of one passage handed to the model


MIN_USABLE_CHARS = 400       # shorter passages (headers, captions, contents lines) make poor questions


MAX_PAGES = 2000             # safety limit for very large PDFs


MIN_TEXT_CHARS = 200         # below this a PDF has no real text layer (scanned images)


MAX_UNPACKED_BYTES = 300 * 1024 * 1024   # a .docx is a zip: refuse one that unpacks to something absurd


SUPPORTED_MESSAGE = "Upload PDF, Word (.docx), TXT or Markdown files."
