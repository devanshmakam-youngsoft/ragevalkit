"""Which names look like secrets, so their values are never stored."""


_SECRET_FRAGMENTS = frozenset({
    "password", "passwd", "pwd", "secret", "api_key", "apikey",
    "token", "auth", "bearer", "credential", "credentials", "authorization",
    "access_key", "private_key",
})


def is_secret_name(name: str) -> bool:
    n = name.lower().replace("-", "_")
    return any(frag in n for frag in _SECRET_FRAGMENTS)
