"""ragevalkit exception hierarchy.

All library exceptions inherit from RagevalError so callers can catch the
base class to handle any ragevalkit error, or a specific subclass for
fine-grained handling.

    from ragevalkit import RagevalError, JudgeError, DatasetError
"""


class RagevalError(Exception):
    """Base class for all ragevalkit exceptions."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class ConfigError(RagevalError):
    """Invalid or conflicting value passed to serve() or Config."""


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class DatasetError(RagevalError):
    """Dataset file is missing, unreadable, or fails column validation."""


class DocumentError(RagevalError):
    """An uploaded document could not be read (scanned, password-protected, unsupported or empty)."""


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


class ConflictError(StoreError):
    """A change would clash with existing data (e.g. a duplicate group name)."""


class GroupNotFound(StoreError):
    """Requested test-case group does not exist."""

    def __init__(self, group_id: str | None = None):
        msg = f"Group {group_id!r} not found" if group_id else "Group not found"
        super().__init__(msg)
        self.group_id = group_id


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
