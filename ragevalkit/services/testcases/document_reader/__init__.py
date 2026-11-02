"""Reading documents (PDF, Word, TXT, Markdown) into passages that questions can be written from.

Only the text is used and nothing is kept: the uploaded file is deleted as soon as it has been read, so a
50 MB PDF costs no storage. Text is cut into passages of about ``TARGET_CHARS`` characters that remember
which page(s) or section they came from, so every generated question can point at its evidence.
"""
from ragevalkit.core.constants import SUPPORTED_MESSAGE, SUPPORTED_SUFFIXES
from ragevalkit.core.exceptions import DocumentError
from ragevalkit.services.testcases.document_reader.models import Chunk, ReadDocument
from ragevalkit.services.testcases.document_reader.ordering import spread_order
from ragevalkit.services.testcases.document_reader.reader import read_document
from ragevalkit.services.testcases.document_reader.text_cleaning import (
    clean,
    normalise,
    sentences_of,
)

__all__ = [
    "Chunk", "DocumentError", "ReadDocument", "SUPPORTED_MESSAGE", "SUPPORTED_SUFFIXES", "clean", "normalise",
    "read_document", "sentences_of", "spread_order",
]
