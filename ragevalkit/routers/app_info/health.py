"""Is the server up."""
from fastapi import APIRouter

from ragevalkit.schemas.app_info.responses import Health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> Health:
    return {"status": "ok"}
