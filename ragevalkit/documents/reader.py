"""Reading any supported document into passages."""
from pathlib import Path

from ragevalkit.documents.constants import SUPPORTED_MESSAGE, SUPPORTED_SUFFIXES
from ragevalkit.documents.docx_reader import read_docx
from ragevalkit.documents.exceptions import DocumentError
from ragevalkit.documents.models import ReadDocument
from ragevalkit.documents.pdf_reader import read_pdf
from ragevalkit.documents.text_reader import read_text


def read_document(path: Path, name: str | None = None) -> ReadDocument:
    """Read one document into passages. Raises DocumentError with a message fit to show the user."""
    path = Path(path)
    name = name or path.name
    suffix = Path(name).suffix.lower()
    if suffix == ".doc":
        raise DocumentError(f"{name}: old Word files (.doc) are not supported. Open it in Word and save it as .docx.")
    if suffix not in SUPPORTED_SUFFIXES:
        raise DocumentError(f"{name}: unsupported file type. {SUPPORTED_MESSAGE}")
    if suffix == ".pdf":
        doc = read_pdf(path, name)
    elif suffix == ".docx":
        doc = read_docx(path, name)
    else:
        doc = read_text(path, name, markdown=suffix != ".txt")
    if not doc.usable():
        raise DocumentError(f"{name} has no passages with enough text to write questions from.")
    return doc
