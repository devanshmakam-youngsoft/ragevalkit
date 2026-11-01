"""What the health, info and features endpoints return."""
from ragevalkit.schemas.base import ApiResponse


class Health(ApiResponse):
    """The answer of the health check: the server is up."""

    status: str               # always "ok"


class AppInfo(ApiResponse):
    """What the dashboard calls itself, shown on the login page before anyone has signed in."""

    name: str                 # the display name for the dashboard heading and the browser tab


class Features(ApiResponse):
    """Which optional parts of the dashboard are switched on."""

    guide: bool              # whether the dashboard shows the Help page
