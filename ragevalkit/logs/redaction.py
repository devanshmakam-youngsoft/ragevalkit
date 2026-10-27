"""Keep secrets out of anything written to a log or shown in the dashboard."""
import re

MASK = "[hidden]"
_KEY_LIKE = [
    re.compile(r"\b(?:sk|gsk|xai|pk|rk)[-_][A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)\bBearer\s+[\w\-.=]{12,}"),
]
_NAMED_VALUE = re.compile(r"""(?i)\b(api[_-]?key|token|secret|password)(['"]?\s*[=:]\s*['"]?)[^\s'",;]{6,}""")


def redact(text: str) -> str:
    """The text with API keys, bearer tokens and ``password=...`` style values replaced."""
    for pattern in _KEY_LIKE:
        text = pattern.sub(MASK, text)
    return _NAMED_VALUE.sub(lambda found: f"{found.group(1)}{found.group(2)}{MASK}", text)
