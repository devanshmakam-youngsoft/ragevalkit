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

    Args:
        group: Name of a group (not its id). Limits the comparison to that group's test cases.
        tolerance: Versions within this many overall-score points (the scale is 0-10) of the best count as
            tied, and the fastest of them wins. Overrides the ``serve()`` default for this request only.
        max_time: Response-time ceiling in seconds; slower versions are not recommended. Zero or less removes
            the ceiling. Overrides the ``serve()`` default for this request only.

    Returns:
        The recommended version in ``best`` and why in ``reason``. ``best`` is ``null`` when no version
        qualifies, for example when none reaches ``min_quality`` or none fits ``max_time``.

    Error answers:
        422 when ``tolerance`` is negative.
    """
    return recommend_version(cfg, store, group, tolerance, max_time)
