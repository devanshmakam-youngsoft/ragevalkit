"""Reading PDF files page by page."""
import re
from pathlib import Path

from pypdf import PdfReader

from ragevalkit.core.constants import MAX_PAGES, MIN_TEXT_CHARS
from ragevalkit.core.exceptions import DocumentError
from ragevalkit.services.document_reader.models import ReadDocument
from ragevalkit.services.document_reader.passages import (
    pack_into_chunks,
    paragraph_units,
    split_long_unit,
)


def read_pdf(path: Path, name: str) -> ReadDocument:
    """Read a PDF into passages, remembering the page each passage came from.

    Only the first ``MAX_PAGES`` pages are read, though ``ReadDocument.pages`` reports the real page count. A page
    whose text cannot be extracted is skipped instead of failing the whole file.

    Args:
        path: The file on disk.
        name: The name to show in passage ids and error messages (the uploaded file's name, not ``path``).

    Raises:
        DocumentError: When the PDF is password-protected, cannot be read, or has no selectable text (a scan).
    """
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
