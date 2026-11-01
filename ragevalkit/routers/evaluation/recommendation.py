"""Which version to ship."""
from fastapi import APIRouter, Depends

from ragevalkit.core.config import Config
from ragevalkit.data_access.store import EvalStore
from ragevalkit.routers.dependencies import get_config, get_store, require_user
from ragevalkit.schemas.evaluation.responses import Recommendation
from ragevalkit.services.version_recommender.recommendation_views import recommend_version

router = APIRouter(prefix="/api/recommendation", tags=["recommendation"], dependencies=[Depends(require_user)])


@router.get("")
def get_recommendation(
    group: str | None = None,
    tolerance: float | None = None,
    max_time: float | None = None,
    cfg: Config = Depends(get_config),
    store: EvalStore = Depends(get_store),
) -> Recommendation:
    """Which version to ship, computed now from the saved scores of every non-archived run.

    ``group`` limits the comparison to one group's scores. ``tolerance`` and ``max_time`` override
    the ``serve()`` defaults for this request only.
    """
    return recommend_version(cfg, store, group, tolerance, max_time)
