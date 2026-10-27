"""Cutting a document's text into passages of a size a model can write questions from."""
import re

from ragevalkit.documents.constants import TARGET_CHARS
from ragevalkit.documents.models import Chunk
from ragevalkit.documents.text_cleaning import normalise


def paragraph_units(text: str) -> list[str]:
    """Paragraphs, or lines when the text has no blank lines (typical of PDF extraction)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) > 1:
        return paragraphs
    return [ln.strip() for ln in text.splitlines() if ln.strip()] or paragraphs


def split_long_unit(unit: str) -> list[str]:
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


def pack_into_chunks(units: list[tuple[str, int | None, str | None]], name: str) -> list[Chunk]:
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
