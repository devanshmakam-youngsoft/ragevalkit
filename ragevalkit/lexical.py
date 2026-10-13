"""Non-LLM scores: keyword recall, BM25, and embedding similarity between expected and generated answers."""
import math
import re
from collections import Counter
from functools import lru_cache

STOPWORDS = set(
    "a an the and or of to in on for with by at from as is are was were be been being it its this that "
    "these those which who whom will shall may can could should would must not no than then there their "
    "they he she his her you your we our i if but so such any all each other into over under about also "
    "has have had do does did per".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", (text or "").lower()) if t not in STOPWORDS]


def keyword_recall(expected: str, generated: str) -> float | None:
    """Share of the expected answer's distinct keywords present in the generated answer."""
    keys = set(tokenize(expected))
    if not keys:
        return None
    return round(len(keys & set(tokenize(generated))) / len(keys), 3)


def bm25_score(expected: str, generated: str, k1: float = 1.5, b: float = 0.75) -> float | None:
    """BM25 of the generated answer for the expected answer as query, normalised to [0, 1]."""
    query = tokenize(expected)
    if not query:
        return None
    docs = [tokenize(expected), tokenize(generated)]
    if not docs[1]:
        return 0.0
    n = len(docs)
    avg = sum(len(d) for d in docs) / n
    df = Counter(t for d in docs for t in set(d))

    def score(doc: list[str]) -> float:
        tf = Counter(doc)
        total = 0.0
        for t in set(query):
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            total += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(doc) / avg))
        return total

    best = score(docs[0])
    return round(min(score(docs[1]) / best, 1.0), 3) if best else None


@lru_cache(maxsize=1)
def _embedder(model_name: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


def semantic_similarity(expected: str, generated: str, model_name: str) -> float | None:
    """Cosine similarity between sentence embeddings of expected and generated answers."""
    if not expected.strip() or not (generated or "").strip():
        return None
    import numpy as np
    vecs = _embedder(model_name).encode([expected, generated])
    a, b = vecs[0], vecs[1]
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return round(float(max(0.0, np.dot(a, b) / denom)), 3) if denom else None
