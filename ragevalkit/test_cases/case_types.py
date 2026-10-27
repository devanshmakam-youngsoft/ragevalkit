"""Test case types.

A test case is either ``rag`` (its answer has to come from your documents, so retrieval is scored) or
``non-rag`` (greetings, small talk, anything where no retrieval is expected, so it is graded on the answer only).
Other values found in older data (``query``, ``conversational``...) keep working: only the non-rag ones are
treated as such.
"""
import re


RAG = "rag"


NON_RAG = "non-rag"


TYPES = (RAG, NON_RAG)


_NON_RAG = {"nonrag", "notrag", "norag"}


def is_non_rag(value) -> bool:
    """True for ``non-rag`` however it is spelled (non-rag, non_rag, not rag, Non RAG...)."""
    return re.sub(r"[\s_-]+", "", str(value or "").lower()) in _NON_RAG
