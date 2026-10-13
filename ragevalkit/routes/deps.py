from fastapi import HTTPException, Request

from ragevalkit.auth import read_token


def current_user(request: Request) -> str | None:
    cfg = request.app.state.config
    return read_token(cfg.eval_secret, request.cookies.get(cfg.session_cookie))


def require_user(request: Request) -> str:
    if not request.app.state.config.require_login:
        return "anonymous"
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user
