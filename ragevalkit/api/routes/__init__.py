"""The HTTP routes, one file per area. Routers are listed in the order they are registered: the more specific
``/api/test-cases/import`` comes before ``/api/test-cases/{tc_id}``."""
from ragevalkit.api.routes import (
    auth,
    datasets,
    generation,
    groups,
    guides,
    health,
    imports,
    recommendation,
    runs,
    test_cases,
    versions,
)

DASHBOARD_ROUTERS = [
    auth.router, generation.router, imports.router, runs.router, versions.router, recommendation.router,
    test_cases.router, groups.router, datasets.router, guides.router,
]
HEALTH_ROUTER = health.router

__all__ = ["DASHBOARD_ROUTERS", "HEALTH_ROUTER"]
