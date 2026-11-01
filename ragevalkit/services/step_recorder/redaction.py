"""Which names look like secrets, so their values are never stored."""


_SECRET_FRAGMENTS = frozenset({
    "password", "passwd", "pwd", "secret", "api_key", "apikey",
    "token", "auth", "bearer", "credential", "credentials", "authorization",
    "access_key", "private_key",
})


def is_secret_name(name: str) -> bool:
    """Return whether ``name`` looks like it holds a secret (password, token, API key, ...).

    The match is a case-insensitive substring test, with ``-`` read as ``_``. It errs towards redacting, so a
    name such as ``author_id`` is also treated as secret because it contains ``auth``.
    """
    n = name.lower().replace("-", "_")
    return any(frag in n for frag in _SECRET_FRAGMENTS)
