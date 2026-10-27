"""What reading a document produces: passages (chunks) that remember where they came from."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from ragevalkit.documents.constants import MIN_USABLE_CHARS
from ragevalkit.documents.text_cleaning import clean, sentences_of


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

    @cached_property
    def sentences(self) -> list[str]:
        """The passage as numbered sentences: the unit evidence is cited in (A1, A2, ...)."""
        return sentences_of(self.text)

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


def is_usable(chunk: Chunk) -> bool:
    text = chunk.text
    if len(text) < MIN_USABLE_CHARS:
        return False
    letters = sum(ch.isalpha() for ch in text)
    return letters / max(1, len(text)) >= 0.55        # mostly words, not numbers or table borders
