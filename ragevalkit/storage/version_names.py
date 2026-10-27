"""Which version names are allowed."""
import re

VERSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,20}$")


def valid_version(version: str) -> bool:
    return bool(VERSION_RE.match(version))
