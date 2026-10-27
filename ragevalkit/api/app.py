"""FastAPI app factory. Serves the API and the bundled React dashboard from the same port."""
import logging
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from ragevalkit.api.error_handlers import register_error_handlers
from ragevalkit.api.routes import DASHBOARD_ROUTERS, HEALTH_ROUTER
from ragevalkit.config import Config
from ragevalkit.evaluation.runner import RunManager
from ragevalkit.generation.manager import GenerationManager
from ragevalkit.storage.store import EvalStore

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
DEFAULT_SECRET = "dev-only-change-me"


def _block_everything_but_health(app: FastAPI) -> None:
    """eval_env="prod": only /api/health answers. No store or manager is created."""
    logger.warning("ragevalkit: eval_env='prod' — eval dashboard and routes are DISABLED. Only /api/health is active.")
    app.include_router(HEALTH_ROUTER)

    @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    def _prod_blocked(full_path: str):
        raise HTTPException(
            503,
            "Eval dashboard is disabled in production mode (eval_env='prod'). Only /api/health is available.",
        )


def _serve_dashboard(app: FastAPI) -> None:
    """Serve the compiled dashboard. A browser refresh on /groups or /datasets asks for that path directly, so a 404
    outside /api/ returns index.html and React Router handles the route client-side."""
    index = STATIC_DIR / "index.html"

    @app.exception_handler(StarletteHTTPException)
    async def _spa_fallback(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404 and not request.url.path.startswith("/api/") and index.exists():
            return FileResponse(index)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    if STATIC_DIR.exists() and any(STATIC_DIR.iterdir()):
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
        return
    logger.warning("ragevalkit/static/ is empty. Run `npm run build` inside ragevalkit/frontend/ and copy dist/* to ragevalkit/static/.")

    @app.get("/{full_path:path}")
    def _no_ui(full_path: str):
        return {"detail": "Dashboard not built. See ragevalkit/static/README."}


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
    if config.eval_secret == DEFAULT_SECRET and config.require_login:
        logger.warning("Using the default EVAL_SECRET. Set a strong secret before exposing this service.")

    app = FastAPI(title="ragevalkit", docs_url="/api/docs", redoc_url=None)
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
        logger.info("ragevalkit: eval_env='uat' — UAT recording mode active.")

    app.include_router(HEALTH_ROUTER)
    for router in DASHBOARD_ROUTERS:
        app.include_router(router)
    _serve_dashboard(app)
    return app
