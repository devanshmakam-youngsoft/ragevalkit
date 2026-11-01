"""Meaning similarity from sentence embeddings (a small local model, no API call)."""
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def _embedder(model_name: str) -> "SentenceTransformer":
    # Imported on first use: loading sentence-transformers is slow and the metric can be switched off.
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
