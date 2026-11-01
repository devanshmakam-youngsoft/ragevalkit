"""The base errors. Every library error inherits from ``RagevalError``, so callers can catch the base class to handle any of them."""


class RagevalError(Exception):
    """Base class for all ragevalkit exceptions."""


class ConfigError(RagevalError):
    """Invalid or conflicting value passed to serve() or Config."""


class InvalidInput(RagevalError, ValueError):
    """A value someone sent cannot be used; the message says why in plain words."""


class NotFoundError(RagevalError, KeyError):
    """Something that was asked for does not exist (or is no longer available)."""

    def __str__(self) -> str:
        return Exception.__str__(self)      # a KeyError would put quotes around the message


class TooLargeError(RagevalError):
    """An uploaded file is bigger than allowed."""
