"""Static-user login with an HMAC-signed, expiring session token (no database, no extra dependencies)."""
import base64
import hashlib
import hmac
import json
import time


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


def _sign(secret: str, payload: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def make_token(secret: str, username: str, ttl_seconds: int, now: float | None = None) -> str:
    body = json.dumps({"u": username, "exp": int((now or time.time()) + ttl_seconds)}).encode()
    payload = base64.urlsafe_b64encode(body).decode().rstrip("=")
    return f"{payload}.{_sign(secret, payload)}"


def read_token(secret: str, token: str | None, now: float | None = None) -> str | None:
    """Username for a valid, unexpired token; None for anything else (bad signature, expired, garbage)."""
    if not token or "." not in token:
        return None
    payload, _, signature = token.partition(".")
    if not hmac.compare_digest(signature.encode(), _sign(secret, payload).encode()):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["exp"] < (now or time.time()):
            return None
        return str(data["u"])
    except (ValueError, KeyError, TypeError):
        return None
