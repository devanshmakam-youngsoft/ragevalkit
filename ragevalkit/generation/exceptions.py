"""Errors raised while writing test cases from documents."""
from ragevalkit.exceptions import RagevalError


class GenerationError(RagevalError):
    """A question could not be written that follows every rule."""


class GenerationBusy(RagevalError):
    """Another generation is already running."""
