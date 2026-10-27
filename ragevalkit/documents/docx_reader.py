"""Reading Word (.docx) files: paragraphs, headings, lists and tables in reading order."""
import zipfile
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from ragevalkit.documents.constants import MAX_UNPACKED_BYTES, MIN_TEXT_CHARS
from ragevalkit.documents.exceptions import DocumentError
from ragevalkit.documents.models import ReadDocument
from ragevalkit.documents.passages import pack_into_chunks, split_long_unit


def _docx_units(doc) -> list[tuple[str, int | None, str | None]]:
    """The paragraphs and tables of a Word document in reading order, each with the heading it sits under."""
    units: list[tuple[str, int | None, str | None]] = []
    heading: str | None = None
    for child in doc.element.body.iterchildren():
        kind = child.tag.rsplit("}", 1)[-1]
        if kind == "p":
            paragraph = Paragraph(child, doc)
            text = paragraph.text.strip()
            if not text:
                continue
            style = (paragraph.style.name or "") if paragraph.style is not None else ""
            if style.startswith("Heading") or style == "Title":
                heading = text
            elif "List" in style:
                text = f"- {text}"
            for part in split_long_unit(text):
                units.append((part, None, heading))
        elif kind == "tbl":
            rows = []
            for row in Table(child, doc).rows:
                cells: list[str] = []
                for cell in row.cells:                     # merged cells repeat: keep each once
                    text = cell.text.strip()
                    if text and text not in cells:
                        cells.append(text)
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                units.append(("\n".join(rows), None, heading))
    return units


def read_docx(path: Path, name: str) -> ReadDocument:
    try:
        with zipfile.ZipFile(path) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_UNPACKED_BYTES:
                raise DocumentError(f"{name} is too large once unpacked.")
        units = _docx_units(Document(str(path)))
    except DocumentError:
        raise
    except Exception as e:
        raise DocumentError(
            f"{name} could not be read as a Word document (.docx). If it is password-protected, remove the password first."
        ) from e
    chars = sum(len(u[0]) for u in units)
    if chars < MIN_TEXT_CHARS // 2:
        raise DocumentError(f"{name} has almost no text ({chars} characters).")
    return ReadDocument(name=name, chunks=pack_into_chunks(units, name), pages=None, chars=chars)
