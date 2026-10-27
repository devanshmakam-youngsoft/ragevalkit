"""FastAPI app factory. Serves the API and the bundled React dashboard from the same port."""
import logging
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from ragevalkit.config import Config
from ragevalkit.routes import auth, generate, health, imports, runs
from ragevalkit.generation import GenerationManager
from ragevalkit.evaluation.runner import RunManager
from ragevalkit.storage.store import EvalStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_SECRET = "dev-only-change-me"


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

    # --- prod mode: block the eval dashboard and all eval routes ---
    # Only /api/health responds in prod. No store or manager is created.
    if config.eval_env == "prod":
        logger.warning(
            "ragevalkit: eval_env='prod' — eval dashboard and routes are DISABLED. "
            "Only /api/health is active."
        )
        app.include_router(health.router)

        @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
        def _prod_blocked(full_path: str):
            raise HTTPException(
                503,
                "Eval dashboard is disabled in production mode (eval_env='prod'). "
                "Only /api/health is available.",
            )

        return app

    # --- dev / uat mode ---
    app.state.store = EvalStore(config.store_path)
    app.state.manager = RunManager(
        config, app.state.store, fn,
        judge_fn=judge_fn,
        extra_metrics=extra_metrics,
        on_complete=on_complete,
        session_id_fn=session_id_fn,
    )

    app.state.generator = GenerationManager(config, app.state.store, llm=generation_llm)

    if config.eval_env == "uat":
        logger.info("ragevalkit: eval_env='uat' — UAT recording mode active.")

    for module in (health, auth, generate, imports, runs):
        app.include_router(module.router)

    # SPA fallback: on refresh, the browser requests /datasets, /groups, etc. directly.
    # StaticFiles doesn't serve index.html for these — so we intercept 404s for non-API
    # paths and return index.html so React Router can handle the route client-side.
    _index = STATIC_DIR / "index.html"

    @app.exception_handler(StarletteHTTPException)
    async def _spa_fallback(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404 and not request.url.path.startswith("/api/") and _index.exists():
            return FileResponse(_index)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    _static = STATIC_DIR
    if _static.exists() and any(_static.iterdir()):
        app.mount("/", StaticFiles(directory=_static, html=True), name="static")
    else:
        logger.warning(
            "ragevalkit/static/ is empty. "
            "Run `npm run build` inside ragevalkit/frontend/ and copy dist/* to ragevalkit/static/."
        )

        @app.get("/{full_path:path}")
        def _no_ui(full_path: str):
            return {"detail": "Dashboard not built. See ragevalkit/static/README."}

    return app
