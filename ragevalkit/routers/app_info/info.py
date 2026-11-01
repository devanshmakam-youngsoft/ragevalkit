"""What the dashboard calls itself. Public, because the login page shows it before anyone has signed in."""
from fastapi import APIRouter

from ragevalkit.core.constants.library import DISPLAY_NAME
from ragevalkit.schemas.app_info.responses import AppInfo

router = APIRouter(prefix="/api", tags=["info"])


@router.get("/info")
def info() -> AppInfo:
    return AppInfo(name=DISPLAY_NAME)
