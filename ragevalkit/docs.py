"""Reading documents (PDF, TXT, Markdown) into passages that questions can be written from.

Only the text is used and nothing is kept: the uploaded file is deleted as soon as it has been read, so a
50 MB PDF costs no storage. Text is cut into passages of about ``TARGET_CHARS`` characters that remember
which page(s) or section they came from, so every generated question can point at its evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from ragevalkit.exceptions import DocumentError

SUPPORTED_SUFFIXES = (".pdf", ".txt", ".md", ".markdown")
TARGET_CHARS = 3500          # size of one passage handed to the model
MIN_USABLE_CHARS = 400       # shorter passages (headers, captions, contents lines) make poor questions
MAX_PAGES = 2000             # safety limit for very large PDFs
MIN_TEXT_CHARS = 200         # below this a PDF has no real text layer (scanned images)


@dataclass
class Chunk:
    """A passage of a document, with where it came from."""
    id: str
    file: str
    text: str
    label: str                                   # "page 3", "pages 3–4" or "section: Refunds"
    pages: list[tuple[int, str]] = field(default_factory=list)   # (page number, normalised text) per page

    @cached_property
    def cleaned(self) -> str:
        """The passage as quotes are matched against it: markdown marks and odd quotes removed, case kept."""
        return clean(self.text)

    def page_of(self, quote_norm: str) -> str:
        """The page a normalised quote is on (or the passage's label when it spans pages / has none)."""
        for number, text in self.pages:
            if quote_norm in text:
                return f"page {number}"
        return self.label


@dataclass
class ReadDocument:
    name: str
    chunks: list[Chunk]
    pages: int | None
    chars: int

    def usable(self) -> list[Chunk]:
        return [c for c in self.chunks if is_usable(c)]


_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
                         "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ", "­": ""})


def clean(text: str) -> str:
    """Text with the noise models and documents disagree about removed: odd quotes and dashes, line-break
    hyphenation, markdown marks (**bold**, `code`, # headings, > quotes, | tables, list bullets) and spacing."""
    text = (text or "").translate(_DASHES)
    text = re.sub(r"-\s*\n\s*", "", text)                          # "refund-\nable" -> "refundable"
    text = re.sub(r"(?m)^\s*(?:[-*\u2022]|\d+[.)])\s+", "", text)  # list bullets and numbers at the start of a line
    text = re.sub(r"[*`~#>|]+", " ", text)                           # emphasis, code, headings, quotes, table cells
    return re.sub(r"\s+", " ", text).strip()


def normalise(text: str) -> str:
    """``clean`` in lower case: how two pieces of text are compared."""
    return clean(text).lower()


def is_usable(chunk: Chunk) -> bool:
    text = chunk.text
    if len(text) < MIN_USABLE_CHARS:
        return False
    letters = sum(ch.isalpha() for ch in text)
    return letters / max(1, len(text)) >= 0.55        # mostly words, not numbers or table borders


def _units(text: str) -> list[str]:
    """Paragraphs, or lines when the text has no blank lines (typical of PDF extraction)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) > 1:
        return paragraphs
    return [ln.strip() for ln in text.splitlines() if ln.strip()] or paragraphs


def _split_long(unit: str) -> list[str]:
    """A single unit longer than a passage is cut at sentence ends."""
    if len(unit) <= TARGET_CHARS * 1.5:
        return [unit]
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", unit):
        if current and len(current) + len(sentence) > TARGET_CHARS:
            parts.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
    return parts + ([current] if current else [])


def _pack(units: list[tuple[str, int | None, str | None]], name: str) -> list[Chunk]:
    """Group (text, page, heading) units into passages of about TARGET_CHARS."""
    chunks: list[Chunk] = []
    buffer: list[tuple[str, int | None, str | None]] = []

    def flush():
        if not buffer:
            return
        text = "\n\n".join(u[0] for u in buffer)
        pages = sorted({u[1] for u in buffer if u[1] is not None})
        headings = [u[2] for u in buffer if u[2]]
        if pages:
            label = f"page {pages[0]}" if len(pages) == 1 else f"pages {pages[0]}–{pages[-1]}"
        elif headings:
            label = f"section: {headings[0]}"
        else:
            label = "document"
        by_page: dict[int, list[str]] = {}
        for t, p, _ in buffer:
            if p is not None:
                by_page.setdefault(p, []).append(t)
        chunks.append(Chunk(
            id=f"{name}#{len(chunks) + 1}", file=name, text=text, label=label,
            pages=[(p, normalise("\n".join(ts))) for p, ts in sorted(by_page.items())],
        ))
        buffer.clear()

    size = 0
    for unit in units:
        if buffer and size + len(unit[0]) > TARGET_CHARS:
            flush()
            size = 0
        buffer.append(unit)
        size += len(unit[0])
    flush()
    return chunks


def _read_pdf(path: Path, name: str) -> ReadDocument:
    from pypdf import PdfReader

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
            for unit in _units(text):
                for part in _split_long(unit):
                    units.append((part, number, None))
    except DocumentError:
        raise
    except Exception as e:
        raise DocumentError(f"{name} could not be read as a PDF: {e}") from e
    if chars < MIN_TEXT_CHARS:
        raise DocumentError(
            f"{name} has no selectable text (it looks like a scan). Upload a text-based PDF, or the text as .txt / .md."
        )
    return ReadDocument(name=name, chunks=_pack(units, name), pages=total, chars=chars)


def _read_text(path: Path, name: str, markdown: bool) -> ReadDocument:
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
        for part in _split_long(block):
            units.append((part, None, heading))
    return ReadDocument(name=name, chunks=_pack(units, name), pages=None, chars=len(text))


def read_document(path: Path, name: str | None = None) -> ReadDocument:
    """Read one document into passages. Raises DocumentError with a message fit to show the user."""
    path = Path(path)
    name = name or path.name
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise DocumentError(f"{name}: unsupported file type. Upload PDF, TXT or MD files.")
    doc = _read_pdf(path, name) if suffix == ".pdf" else _read_text(path, name, markdown=suffix != ".txt")
    if not doc.usable():
        raise DocumentError(f"{name} has no passages with enough text to write questions from.")
    return doc


def spread_order(n: int) -> list[int]:
    """0..n-1 ordered so that any prefix is spread across the whole range (van der Corput order):
    n=8 gives 0, 4, 2, 6, 1, 5, 3, 7. Taking passages in this order samples a document evenly."""
    def reverse_bits(i: int) -> float:
        value, base = 0.0, 0.5
        while i:
            value += (i & 1) * base
            i >>= 1
            base /= 2
        return value

    return sorted(range(n), key=lambda i: (reverse_bits(i), i))
