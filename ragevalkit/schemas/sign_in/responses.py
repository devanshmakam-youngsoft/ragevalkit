"""What the sign-in endpoints return."""
from ragevalkit.schemas.base import ApiResponse


class SignedInUser(ApiResponse):
    username: str


class Acknowledged(ApiResponse):
    ok: bool
