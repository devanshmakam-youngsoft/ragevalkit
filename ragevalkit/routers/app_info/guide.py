"""The guide, so it can be read inside the dashboard, and which optional parts the dashboard shows."""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ragevalkit.core.config import Config
from ragevalkit.routers.dependencies import get_config, require_user
from ragevalkit.schemas.app_info import Features
from ragevalkit.services.app_info import enabled_features, guide_page

router = APIRouter(prefix="/api", tags=["help"], dependencies=[Depends(require_user)])


@router.get("/features")
def features(cfg: Config = Depends(get_config)) -> Features:
    """Report which optional parts of the dashboard are switched on.

    Currently this is only the Help page: ``guide`` is true when the guide can be read from `/api/help/guide`.
    """
    return enabled_features(cfg)


@router.get("/help/guide")
def read_guide(cfg: Config = Depends(get_config)) -> HTMLResponse:
    """The guide as a complete page, meant for an iframe on the Help page.

    Answers 404 when the guide has been switched off.
    """
    return HTMLResponse(guide_page(cfg))
