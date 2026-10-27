"""Which version to ship."""
from fastapi import APIRouter, Depends

from ragevalkit.api.dependencies import get_config, get_store, require_user
from ragevalkit.api.services.recommendations import recommend_version
from ragevalkit.config import Config
from ragevalkit.storage.store import EvalStore

router = APIRouter(prefix="/api/recommendation", tags=["recommendation"], dependencies=[Depends(require_user)])


@router.get("")
def get_recommendation(
    group: str | None = None,
    tolerance: float | None = None,
    max_time: float | None = None,
    cfg: Config = Depends(get_config),
    store: EvalStore = Depends(get_store),
) -> dict:
    """Which version to ship, computed now from the saved scores of every non-archived run.

    ``group`` limits the comparison to one group's scores. ``tolerance`` and ``max_time`` override
    the ``serve()`` defaults for this request only.
    """
    return recommend_version(cfg, store, group, tolerance, max_time)
