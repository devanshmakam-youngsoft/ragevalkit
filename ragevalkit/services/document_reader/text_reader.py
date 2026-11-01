"""Reading plain text and Markdown files."""
import re
from pathlib import Path

from ragevalkit.core.constants.document_reading import MIN_TEXT_CHARS
from ragevalkit.core.exceptions.document_reader import DocumentError
from ragevalkit.services.document_reader.models import ReadDocument
from ragevalkit.services.document_reader.passages import pack_into_chunks, split_long_unit


def read_text(path: Path, name: str, markdown: bool) -> ReadDocument:
    """Read a plain text or Markdown file into passages.

    The file is decoded as UTF-8, with undecodable bytes replaced.

    Args:
        path: The file on disk.
        name: The name to show in passage ids and error messages (the uploaded file's name, not ``path``).
        markdown: Whether to treat ``#`` headings as sections, so that passages are labelled with the section
            they belong to.

    Raises:
        DocumentError: When the file has almost no text.
    """
    text = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    if len(text.strip()) < MIN_TEXT_CHARS // 2:
        raise DocumentError(f"{name} has almost no text ({len(text.strip())} characters).")
    units: list[tuple[str, int | None, str | None]] = []
    heading: str | None = None
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if markdown:
            match = re.match(r"^#{1,6}\s+(.+)", block)
            if match:
                heading = match.group(1).strip()
        for part in split_long_unit(block):
            units.append((part, None, heading))
    return ReadDocument(name=name, chunks=pack_into_chunks(units, name), pages=None, chars=len(text))
