from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from pydantic import BaseModel

from ..auth import COOKIE_NAME, check_credentials, create_session_token, verify_session_token
from ..config import Config

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest, response: Response, request: Request):
    config: Config = request.app.state.config
    if not check_credentials(body.username, body.password, config):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_session_token(body.username, config)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=config.cookie_secure,
        max_age=config.session_ttl_seconds,
    )
    return {"username": body.username}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME)
    return {"status": "logged_out"}


@router.get("/me")
def me(request: Request, session: str | None = Cookie(default=None)):
    config: Config = request.app.state.config
    if session is None or not verify_session_token(session, config):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return {"authenticated": True}
