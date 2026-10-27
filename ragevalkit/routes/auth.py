import asyncio

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ragevalkit.auth.passwords import check_password, parse_users
from ragevalkit.auth.sessions import make_token
from ragevalkit.routes.deps import current_user

router = APIRouter(prefix="/api/auth")


class LoginBody(BaseModel):
    username: str
    password: str


def _secure(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response) -> dict:
    cfg = request.app.state.config
    if cfg.require_login:
        user = check_password(parse_users(cfg.eval_users), body.username, body.password)
        if user is None:
            await asyncio.sleep(0.6)
            raise HTTPException(status_code=401, detail="Invalid username or password")
    else:
        # Guest mode: any non-empty username is accepted as-is
        user = body.username.strip().lower() or "anonymous"
    ttl = cfg.session_hours * 3600
    response.set_cookie(
        cfg.session_cookie,
        make_token(cfg.eval_secret, user, ttl),
        max_age=ttl,
        httponly=True,
        samesite="lax",
        secure=_secure(request),
        path="/",
    )
    return {"username": user}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    response.delete_cookie(request.app.state.config.session_cookie, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict:
    # Always require a session cookie — login is always shown first
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return {"username": user}
