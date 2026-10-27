"""Turning "the store found nothing" into a clear not-found error."""
from typing import TypeVar

from ragevalkit.exceptions import NotFoundError

T = TypeVar("T")


def ensure_found(value: T, message: str) -> T:
    """``value`` unless it is empty or False, in which case what was asked for does not exist."""
    if not value:
        raise NotFoundError(message)
    return value
