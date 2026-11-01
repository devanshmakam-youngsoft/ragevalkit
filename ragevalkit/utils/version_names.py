"""Which version names are allowed."""
import re

VERSION_RE = re.compile(r"[A-Za-z0-9._-]{1,20}")


def valid_version(version: str) -> bool:
    """Return whether ``version`` is 1 to 20 characters of letters, digits, ``.``, ``_`` or ``-``."""
    return bool(VERSION_RE.fullmatch(version))   # fullmatch: a trailing newline must not slip through
