"""The meaning score says how to install what it needs when the optional package is missing."""
import re
import sys

import pytest

from ragevalkit.core.config import SEMANTIC_INSTALL_COMMAND
from ragevalkit.services.text_metrics import embeddings


def test_a_missing_package_gives_the_install_command(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)     # makes `import sentence_transformers` fail
    embeddings._embedder.cache_clear()
    with pytest.raises(ImportError, match=re.escape(SEMANTIC_INSTALL_COMMAND)):
        embeddings.semantic_similarity("refunds take 30 days", "you have 30 days", "any-model")
    embeddings._embedder.cache_clear()
