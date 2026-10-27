"""Errors raised while reading a test case spreadsheet."""
from ragevalkit.exceptions import RagevalError


class DatasetError(RagevalError):
    """Dataset file is missing, unreadable, or fails column validation."""
