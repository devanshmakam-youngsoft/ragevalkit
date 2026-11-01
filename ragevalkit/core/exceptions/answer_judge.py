"""Errors raised by the AI judge."""
from ragevalkit.core.exceptions.base import RagevalError


class JudgeError(RagevalError):
    """LLM judge failed to return a valid response after all retries."""
