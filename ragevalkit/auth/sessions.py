"""HMAC-signed, expiring session tokens (no database, no extra dependencies)."""
import base64
import hashlib
import hmac
import json
import time


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
