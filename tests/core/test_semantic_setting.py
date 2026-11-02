"""The meaning score needs an optional package: automatic by default, and a clear message when it is asked for without it."""
import importlib.util

import pytest

from ragevalkit.core.config import SEMANTIC_INSTALL_COMMAND, Config, semantic_extra_installed
from ragevalkit.core.exceptions import ConfigError
from ragevalkit.launcher import serve


@pytest.fixture
def installed(monkeypatch):
    """Pretend the semantic extra is (True) or is not (False) installed; the check is cached, so clear it around the test."""
    real = importlib.util.find_spec

    def pretend(is_installed: bool) -> None:
        monkeypatch.setattr(importlib.util, "find_spec",
                            lambda name, *args: (object() if is_installed else None) if name == "sentence_transformers" else real(name, *args))
        semantic_extra_installed.cache_clear()

    yield pretend
    monkeypatch.undo()
    semantic_extra_installed.cache_clear()


@pytest.mark.parametrize("is_installed", [True, False])
def test_left_unset_the_meaning_score_follows_whether_the_extra_is_installed(installed, is_installed):
    installed(is_installed)
    assert Config().semantic_similarity_enabled is is_installed


def test_an_explicit_choice_wins_over_what_is_installed(installed):
    installed(True)
    assert Config(run_semantic_similarity=False).semantic_similarity_enabled is False
    installed(False)
    assert Config(run_semantic_similarity=True).semantic_similarity_enabled is True


def test_serve_refuses_the_meaning_score_without_the_extra_and_says_how_to_install_it(installed):
    installed(False)
    with pytest.raises(ConfigError) as error:
        serve(lambda question: "", run_semantic_similarity=True)
    assert SEMANTIC_INSTALL_COMMAND in str(error.value)
