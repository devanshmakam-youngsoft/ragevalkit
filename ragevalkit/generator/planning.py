"""Deciding which passages each question is written from."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ragevalkit.documents.models import Chunk, ReadDocument
from ragevalkit.documents.ordering import spread_order


@dataclass
class Task:
    """One question (or conversation) to write."""
    category: str
    doc: str
    chunks: list[Chunk]      # one passage, or two for a multi-part question
    number: int              # 1-based within its category


def _halves(chunk: Chunk) -> list[Chunk]:
    """A document with a single passage: split it so a multi-part question still has two passages."""
    pieces = [p for p in re.split(r"\n\s*\n|\n", chunk.text) if p.strip()]
    if len(pieces) < 2:  # one long paragraph: cut at a sentence boundary instead
        pieces = [p for p in re.split(r"(?<=[.!?])\s+", chunk.text) if p.strip()]
    middle = max(1, len(pieces) // 2)
    texts = [" ".join(pieces[:middle]), " ".join(pieces[middle:]) or chunk.text]
    return [Chunk(id=f"{chunk.id}.{i}", file=chunk.file, text=t, label=chunk.label, pages=chunk.pages) for i, t in enumerate(texts, 1)]


class _Stream:
    """Hands out a document's usable passages in a spread order (so any few of them sample the whole
    document), wrapping round when it runs out."""

    def __init__(self, doc: ReadDocument):
        self.chunks = doc.usable()
        self.order = spread_order(len(self.chunks))
        self.pointer = 0

    def take(self, k: int) -> list[Chunk]:
        if len(self.chunks) == 1 and k == 2:
            return _halves(self.chunks[0])
        picked = []
        for _ in range(k):
            picked.append(self.chunks[self.order[self.pointer % len(self.order)]])
            self.pointer += 1
        return picked


def plan_tasks(docs: list[ReadDocument], categories: list[str], per_category: int) -> list[Task]:
    """``per_category`` questions in each category, shared out across the documents in turn."""
    streams = {d.name: _Stream(d) for d in docs}
    tasks = []
    for category in categories:
        for i in range(per_category):
            doc = docs[i % len(docs)]
            tasks.append(Task(category, doc.name, streams[doc.name].take(2 if category == "multipart" else 1), i + 1))
    return tasks
