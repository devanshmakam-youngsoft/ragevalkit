"""Reading PDF files page by page."""
import re
from pathlib import Path

from pypdf import PdfReader

from ragevalkit.documents.constants import MAX_PAGES, MIN_TEXT_CHARS
from ragevalkit.documents.exceptions import DocumentError
from ragevalkit.documents.models import ReadDocument
from ragevalkit.documents.passages import pack_into_chunks, paragraph_units, split_long_unit


def read_pdf(path: Path, name: str) -> ReadDocument:
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentError(f"{name} is password-protected. Remove the password and upload it again.")
        total = len(reader.pages)
        units: list[tuple[str, int | None, str | None]] = []
        chars = 0
        for number, page in enumerate(reader.pages[:MAX_PAGES], start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""  # one unreadable page should not lose the whole document
            text = re.sub(r"[ \t]+", " ", text).strip()
            chars += len(text)
            for unit in paragraph_units(text):
                for part in split_long_unit(unit):
                    units.append((part, number, None))
    except DocumentError:
        raise
    except Exception as e:
        raise DocumentError(f"{name} could not be read as a PDF: {e}") from e
    if chars < MIN_TEXT_CHARS:
        raise DocumentError(
            f"{name} has no selectable text (it looks like a scan). Upload a text-based PDF, or the text as .txt / .md."
        )
    return ReadDocument(name=name, chunks=pack_into_chunks(units, name), pages=total, chars=chars)
