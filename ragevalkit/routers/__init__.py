"""The HTTP routes, one file per area. Routers are listed in the order they are registered: the more specific
``/api/test-cases/import`` comes before ``/api/test-cases/{tc_id}``."""
from ragevalkit.routers.app_info import guide, health
from ragevalkit.routers.evaluation import recommendation, runs, versions
from ragevalkit.routers.sign_in import login
from ragevalkit.routers.testcase_generator import generation
from ragevalkit.routers.testcase_library import datasets, groups, imports, testcases

DASHBOARD_ROUTERS = [
    login.router, generation.router, imports.router, runs.router, versions.router, recommendation.router,
    testcases.router, groups.router, datasets.router, guide.router,
]
HEALTH_ROUTER = health.router

__all__ = ["DASHBOARD_ROUTERS", "HEALTH_ROUTER"]
