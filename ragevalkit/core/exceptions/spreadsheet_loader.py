"""Errors raised while reading a test case spreadsheet."""
from ragevalkit.core.exceptions.base import RagevalError


class DatasetError(RagevalError):
    """Dataset file is missing, unreadable, or fails column validation."""
