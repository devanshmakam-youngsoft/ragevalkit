"""What the health, info and features endpoints return."""
from ragevalkit.schemas.base import ApiResponse


class Health(ApiResponse):
    status: str


class AppInfo(ApiResponse):
    name: str                 # the display name for the dashboard heading and the browser tab


class Features(ApiResponse):
    guide: bool               # whether the dashboard shows the Help page
