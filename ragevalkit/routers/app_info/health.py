"""Is the server up."""
from fastapi import APIRouter

from ragevalkit.schemas.app_info.responses import Health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> Health:
    """Check that the server is up; needs no sign-in, so it suits load balancer and uptime checks.

    This is the only endpoint that still answers when the server runs in production mode.
    """
    return {"status": "ok"}
