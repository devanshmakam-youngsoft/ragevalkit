"""The guides, so they can be read inside the dashboard."""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ragevalkit.api.dependencies import require_user
from ragevalkit.api.services.guides import find_guide, list_guides

router = APIRouter(prefix="/api/help", tags=["help"], dependencies=[Depends(require_user)])


@router.get("/guides")
def guides() -> list[dict]:
    return list_guides()


@router.get("/guides/{guide_id}")
def read_guide(guide_id: str) -> HTMLResponse:
    """A guide as a complete page, meant for an iframe on the Help page."""
    return HTMLResponse(find_guide(guide_id).path.read_text(encoding="utf-8"))
