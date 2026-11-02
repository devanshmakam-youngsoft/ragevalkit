"""FastAPI app factory. Serves the API and the bundled React dashboard from the same port."""
import logging
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from ragevalkit.core.config import Config
from ragevalkit.core.constants import API_TITLE, LIBRARY_NAME
from ragevalkit.core.exceptions import register_error_handlers
from ragevalkit.routers import DASHBOARD_ROUTERS, HEALTH_ROUTER
from ragevalkit.services.db_services import EvalStore
from ragevalkit.services.evaluation.evaluation_runner import RunManager
from ragevalkit.services.testcases.testcase_generator import GenerationManager

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "web" / "dashboard"
DEFAULT_SECRET = "dev-only-change-me"


def _block_everything_but_health(app: FastAPI) -> None:
    """eval_env="prod": only /api/health answers. No store or manager is created."""
    logger.warning("%s: eval_env='prod' — eval dashboard and routes are DISABLED. Only /api/health is active.", LIBRARY_NAME)
    app.include_router(HEALTH_ROUTER)

    @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    def _prod_blocked(full_path: str) -> None:
        raise HTTPException(
            503,
            "Eval dashboard is disabled in production mode (eval_env='prod'). Only /api/health is available.",
        )


def _serve_dashboard(app: FastAPI) -> None:
    """Serve the compiled dashboard from ``STATIC_DIR``, or a "not built" notice when that folder is empty.

    A browser refresh on /groups or /datasets asks for that path directly, so a 404 outside /api/ returns
    index.html and React Router handles the route client-side.
    """
    index = STATIC_DIR / "index.html"

    @app.exception_handler(StarletteHTTPException)
    async def _spa_fallback(request: Request, exc: StarletteHTTPException) -> FileResponse | JSONResponse:
        if exc.status_code == 404 and not request.url.path.startswith("/api/") and index.exists():
            return FileResponse(index)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    if STATIC_DIR.exists() and any(STATIC_DIR.iterdir()):
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
        return
    logger.warning("%s/web/dashboard/ is empty. Run `npm run build` inside frontend/: it builds into %s/web/dashboard/.", LIBRARY_NAME, LIBRARY_NAME)

    @app.get("/{full_path:path}")
    def _no_ui(full_path: str) -> dict[str, str]:
        return {"detail": "Dashboard not built. Run `npm run build` inside frontend/."}


def create_app(
    config: Config,
    fn: Callable,
    *,
    judge_fn: Callable | None = None,
    extra_metrics: dict | None = None,
    on_complete: Callable | None = None,
    session_id_fn: Callable | None = None,
    generation_llm: Callable | None = None,
) -> FastAPI:
    """Build the FastAPI app: the API, the results store, the run and generation managers, and the dashboard.

    In ``eval_env="prod"`` only ``/api/health`` is served and no store or manager is created. The app is not
    started here; ``serve()`` does that, and tests can drive the returned app directly.

    Args:
        config: All options. The store, logs and uploads are placed under ``config.data_dir``.
        fn: The pipeline function under evaluation, called once per test question.
        judge_fn: Replaces the LLM judge when given.
        extra_metrics: Extra scoring functions run next to the built-in ones, by metric name.
        on_complete: Called once after each run finishes, with the run's summary and result rows.
        session_id_fn: Returns the session ID to use for a ``chat_id``; defaults to a random UUID per chat.
        generation_llm: Replaces the model that writes test cases from documents. Called with a list of chat
            messages, returns the reply text. Defaults to ``generator_model``, or ``judge_model`` if unset.
    """
    if config.eval_secret == DEFAULT_SECRET and config.require_login:
        logger.warning("Using the default EVAL_SECRET. Set a strong secret before exposing this service.")

    app = FastAPI(title=API_TITLE, docs_url="/api/docs", redoc_url=None)
    app.state.config = config
    register_error_handlers(app)

    if config.eval_env == "prod":
        _block_everything_but_health(app)
        return app

    app.state.store = EvalStore(config.store_path)
    app.state.manager = RunManager(
        config, app.state.store, fn,
        judge_fn=judge_fn, extra_metrics=extra_metrics, on_complete=on_complete, session_id_fn=session_id_fn,
    )
    app.state.generator = GenerationManager(config, app.state.store, llm=generation_llm)

    if config.eval_env == "uat":
        logger.info("%s: eval_env='uat' — UAT recording mode active.", LIBRARY_NAME)

    app.include_router(HEALTH_ROUTER)
    for router in DASHBOARD_ROUTERS:
        app.include_router(router)
    _serve_dashboard(app)
    return app
