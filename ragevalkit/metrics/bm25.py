"""BM25 similarity between the expected and the generated answer."""
import math
from collections import Counter

from ragevalkit.metrics.tokenizer import tokenize


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
