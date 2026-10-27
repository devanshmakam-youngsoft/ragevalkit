"""Static users and password checking."""
import hmac


def parse_users(spec: str) -> dict[str, str]:
    """'alice:pw1,bob:pw2' -> {'alice': 'pw1', 'bob': 'pw2'} (a password may contain ':')."""
    users = {}
    for item in spec.split(","):
        name, sep, password = item.strip().partition(":")
        if name and sep:
            users[name.strip().lower()] = password
    return users


def check_password(users: dict[str, str], username: str, password: str) -> str | None:
    """Return the canonical username if the credentials match. Compares in constant time either way."""
    name = username.strip().lower()
    expected = users.get(name)
    ok = hmac.compare_digest((expected or "\0").encode(), password.encode())
    return name if expected is not None and ok else None
