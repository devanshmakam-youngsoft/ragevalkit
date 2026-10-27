"""What routes ask FastAPI to hand them: settings, the results store, the managers, and the signed-in user."""
from fastapi import HTTPException, Request

from ragevalkit.auth.sessions import read_token
from ragevalkit.config import Config
from ragevalkit.evaluation.runner import RunManager
from ragevalkit.generation.manager import GenerationManager
from ragevalkit.storage.store import EvalStore


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_store(request: Request) -> EvalStore:
    return request.app.state.store


def get_run_manager(request: Request) -> RunManager:
    return request.app.state.manager


def get_generation_manager(request: Request) -> GenerationManager:
    return request.app.state.generator


def current_user(request: Request) -> str | None:
    cfg: Config = request.app.state.config
    return read_token(cfg.eval_secret, request.cookies.get(cfg.session_cookie))


def require_user(request: Request) -> str:
    if not request.app.state.config.require_login:
        return "anonymous"
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user
