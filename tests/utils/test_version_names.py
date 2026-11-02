"""Which names a version may have."""
import pytest

from ragevalkit.utils import valid_version


@pytest.mark.parametrize("name", ["1", "v2", "rerank-on", "ci_0102.1", "a" * 20])
def test_letters_digits_dot_underscore_and_dash_are_allowed(name):
    assert valid_version(name)


@pytest.mark.parametrize("name", ["", "a" * 21, "has space", "v1\n", "slash/name", "semi;colon"])
def test_anything_else_is_refused_including_a_trailing_newline(name):
    assert not valid_version(name)
