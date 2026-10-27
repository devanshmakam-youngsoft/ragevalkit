"""Errors raised while starting or running an evaluation."""
from ragevalkit.exceptions import RagevalError


class RunError(RagevalError):
    """Eval run could not start or complete."""


class RunBusy(RunError):
    """Another evaluation is already in progress."""

    def __init__(self, msg: str = "Another evaluation is already running"):
        super().__init__(msg)
