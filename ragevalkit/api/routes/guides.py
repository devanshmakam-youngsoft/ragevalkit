"""The guide, so it can be read inside the dashboard, and which optional parts the dashboard shows."""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ragevalkit.api.dependencies import get_config, require_user
from ragevalkit.api.services.guides import enabled_features, guide_page
from ragevalkit.config import Config

router = APIRouter(prefix="/api", tags=["help"], dependencies=[Depends(require_user)])


@router.get("/features")
def features(cfg: Config = Depends(get_config)) -> dict:
    return enabled_features(cfg)


@router.get("/help/guide")
def read_guide(cfg: Config = Depends(get_config)) -> HTMLResponse:
    """The guide as a complete page, meant for an iframe on the Help page."""
    return HTMLResponse(guide_page(cfg))
