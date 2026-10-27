"""Keyword recall: how many of the expected answer's key words the generated answer contains."""
from ragevalkit.metrics.tokenizer import tokenize


def keyword_recall(expected: str, generated: str) -> float | None:
    """Share of the expected answer's distinct keywords present in the generated answer."""
    keys = set(tokenize(expected))
    if not keys:
        return None
    return round(len(keys & set(tokenize(generated))) / len(keys), 3)
