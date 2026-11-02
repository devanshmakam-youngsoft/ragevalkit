"""What the dashboard calls itself. Public, because the login page shows it before anyone has signed in."""
from fastapi import APIRouter

from ragevalkit.core.constants import DISPLAY_NAME
from ragevalkit.schemas.app_info import AppInfo

router = APIRouter(prefix="/api", tags=["info"])


@router.get("/info")
def info() -> AppInfo:
    """Give the name the dashboard shows in its heading and browser tab; needs no sign-in."""
    return AppInfo(name=DISPLAY_NAME)
