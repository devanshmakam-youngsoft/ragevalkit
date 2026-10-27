"""Errors raised while reading an uploaded document."""
from ragevalkit.exceptions import RagevalError


class DocumentError(RagevalError):
    """An uploaded document could not be read (scanned, password-protected, unsupported or empty)."""
