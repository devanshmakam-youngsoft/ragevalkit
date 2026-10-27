"""Signing in and out."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ragevalkit.api.dependencies import current_user, get_config
from ragevalkit.api.schemas import LoginBody
from ragevalkit.auth.passwords import check_password, parse_users
from ragevalkit.auth.sessions import make_token
from ragevalkit.config import Config

router = APIRouter(prefix="/api/auth", tags=["auth"])

FAILED_LOGIN_DELAY_SECONDS = 0.6      # slows down password guessing


def _secure(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response, cfg: Config = Depends(get_config)) -> dict:
    if cfg.require_login:
        user = check_password(parse_users(cfg.eval_users), body.username, body.password)
        if user is None:
            await asyncio.sleep(FAILED_LOGIN_DELAY_SECONDS)
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
def logout(response: Response, cfg: Config = Depends(get_config)) -> dict:
    response.delete_cookie(cfg.session_cookie, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict:
    # Always require a session cookie: login is always shown first
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return {"username": user}
