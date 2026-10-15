"""ragevalkit exception hierarchy.

All library exceptions inherit from RagevalError so callers can catch the
base class to handle any ragevalkit error, or a specific subclass for
fine-grained handling.

    from ragevalkit import RagevalError, JudgeError, DatasetError
"""


class RagevalError(Exception):
    """Base class for all ragevalkit exceptions."""


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class DatasetError(RagevalError):
    """Dataset file is missing, unreadable, or fails column validation."""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class StoreError(RagevalError):
    """TinyDB storage operation failed."""


class VersionNotFound(StoreError):
    """Requested version does not exist in the store."""

    def __init__(self, version: str | None = None):
        msg = f"Version {version!r} not found" if version else "Version not found"
        super().__init__(msg)
        self.version = version


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class RunError(RagevalError):
    """Eval run could not start or complete."""


class RunBusy(RunError):
    """Another evaluation is already in progress."""

    def __init__(self, msg: str = "Another evaluation is already running"):
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

class JudgeError(RagevalError):
    """LLM judge failed to return a valid response after all retries."""
