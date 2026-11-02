"""What routes ask FastAPI to hand them: settings, the results store, the managers, and the signed-in user."""
from fastapi import HTTPException, Request

from ragevalkit.core.config import Config
from ragevalkit.core.security import read_token
from ragevalkit.services.db_services import EvalStore
from ragevalkit.services.evaluation.evaluation_runner import RunManager
from ragevalkit.services.testcases.testcase_generator import GenerationManager


def get_config(request: Request) -> Config:
    """Hand the route the settings the server was started with."""
    return request.app.state.config


def get_store(request: Request) -> EvalStore:
    """Hand the route the results store: test cases, groups, saved runs and generated batches."""
    return request.app.state.store


def get_run_manager(request: Request) -> RunManager:
    """Hand the route the manager that starts, tracks and stops evaluation runs."""
    return request.app.state.manager


def get_generation_manager(request: Request) -> GenerationManager:
    """Hand the route the manager that writes test cases from uploaded documents and reviews them."""
    return request.app.state.generator


def current_user(request: Request) -> str | None:
    """Read the signed-in user's name from the session cookie.

    Returns:
        The username, or ``None`` when there is no cookie or it is invalid or expired.
    """
    cfg: Config = request.app.state.config
    return read_token(cfg.eval_secret, request.cookies.get(cfg.session_cookie))


def require_user(request: Request) -> str:
    """Let a request through only when someone is signed in; every route except sign-in, health and info uses it.

    When the server runs without login (``require_login`` off) nobody has to sign in and the user is
    reported as ``"anonymous"``.

    Returns:
        The username of the signed-in user.

    Raises:
        HTTPException: 401 when login is required and the session cookie is missing, invalid or expired.
    """
    if not request.app.state.config.require_login:
        return "anonymous"
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user
