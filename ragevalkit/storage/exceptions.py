"""Errors raised by the results store."""
from ragevalkit.exceptions import RagevalError


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
