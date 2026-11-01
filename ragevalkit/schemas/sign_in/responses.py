"""What the sign-in endpoints return."""
from ragevalkit.schemas.base import ApiResponse


class SignedInUser(ApiResponse):
    """Who is signed in."""

    username: str


class Acknowledged(ApiResponse):
    """A plain confirmation that an action was carried out."""

    ok: bool                        # always true
