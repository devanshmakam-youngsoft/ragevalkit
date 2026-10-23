"""Checking that a question's evidence is really in the document.

Models rarely copy a quote perfectly and return it in many shapes. This module reads those replies
tolerantly but never accepts an invented quote: what is stored is always the passage's own wording.
"""
from __future__ import annotations

import difflib
import math
import re

from ragevalkit.docs import Chunk, clean, normalise

MIN_QUOTE_CHARS = 15
MIN_FRAGMENT_WORDS = 4
MAX_EVIDENCE = 6

_KEYS = ("evidence", "evidences", "quotes", "quote", "supporting_quotes", "supporting_evidence")


def _word_key(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def find_quote(quote: str, chunks: list[Chunk]) -> tuple[int, str] | None:
    """Where a quote is in the passages, as (passage index, the passage's own wording of it).

    The quote is matched word by word (ignoring case and punctuation) and accepted when a long enough run of
    its words is really in a passage; what is *kept* is the passage's exact text for that run, so stored
    evidence is always verbatim. A quote with nothing of the sort in the passages is not accepted."""
    wanted = [k for k in (_word_key(w) for w in re.sub(r"\.{3,}|…", " ", clean(quote)).split()) if k]
    if len(wanted) < MIN_FRAGMENT_WORDS:
        return None
    best: tuple[int, int, str] | None = None
    for index, chunk in enumerate(chunks):
        original = [w for w in chunk.cleaned.split() if _word_key(w)]
        keys = [_word_key(w) for w in original]
        match = difflib.SequenceMatcher(None, wanted, keys, autojunk=False).find_longest_match(0, len(wanted), 0, len(keys))
        if match.size >= max(5, math.ceil(len(wanted) * 0.6)):
            text = " ".join(original[match.b:match.b + match.size])
            if len(text) >= MIN_QUOTE_CHARS and (best is None or match.size > best[0]):
                best = (match.size, index, text)
    return (best[1], best[2]) if best else None


def _strings(value) -> list[str]:
    """Every piece of text in a reply field, whatever shape the model gave it: a list of quotes, a list of
    objects, or a mapping such as {"A": "...", "B": "..."} (the keys are ignored)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _strings(v)]
    if isinstance(value, (list, tuple)):
        return [t for v in value for t in _strings(v)]
    return []


def _fragments(text: str) -> list[str]:
    """A quote cut at ellipses and sentence ends, so a string that joins a sentence from each passage is checked
    sentence by sentence. Fragments of under four words prove nothing and are dropped."""
    parts = re.split(r"\.{3,}|…|(?<=[.!?])\s+(?=[A-Z0-9\"'(])", clean(text))
    return [p.strip() for p in parts if len(p.split()) >= MIN_FRAGMENT_WORDS]


def raw_evidence(reply: dict):
    """The evidence field of a reply, under whichever name the model used."""
    for key in _KEYS:
        if reply.get(key):
            return reply[key]
    return None


def extract(value, chunks: list[Chunk]) -> list[dict]:
    """The quotes in ``value`` that really are in the passages, with the file, page and passage letter each came from."""
    found, seen = [], set()
    for text in _strings(value):
        for fragment in _fragments(text):
            hit = find_quote(fragment, chunks)
            if hit is None or hit[1] in seen:
                continue
            index, quote = hit
            seen.add(quote)
            chunk = chunks[index]
            found.append({"quote": quote, "file": chunk.file, "page": chunk.page_of(normalise(quote)), "passage": "AB"[index] if index < 2 else "A"})
    return found[:MAX_EVIDENCE]
