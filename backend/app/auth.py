import base64
import hashlib
import hmac
import json
import time

from fastapi import Cookie, HTTPException, status

from .config import Config

COOKIE_NAME = "session"


def _sign(payload_b64: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_b64, hashlib.sha256).hexdigest()


def create_session_token(username: str, role: str, config: Config) -> str:
    payload = {"u": username, "r": role, "exp": time.time() + config.session_ttl_seconds}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
    signature = _sign(payload_b64, config.session_secret)
    return f"{payload_b64.decode('ascii')}.{signature}"


def verify_session_token(token: str, config: Config) -> dict | None:
    """Returns the decoded payload (with at least "u"/"r"/"exp") if the token
    is validly signed and unexpired, otherwise None."""
    try:
        payload_b64_str, signature = token.split(".", 1)
    except ValueError:
        return None

    payload_b64 = payload_b64_str.encode("ascii")
    expected_signature = _sign(payload_b64, config.session_secret)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None

    if payload.get("exp", 0) <= time.time():
        return None
    return payload


def check_credentials(username: str, password: str, config: Config) -> str | None:
    """Returns the matched role ("admin"/"planner") or None if no account matches."""
    if hmac.compare_digest(username, config.admin_username) and hmac.compare_digest(
        password, config.admin_password
    ):
        return "admin"
    if hmac.compare_digest(username, config.planner_username) and hmac.compare_digest(
        password, config.planner_password
    ):
        return "planner"
    return None


def make_require_session(config: Config):
    def require_session(session: str | None = Cookie(default=None)) -> dict:
        payload = verify_session_token(session, config) if session is not None else None
        if payload is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        return payload

    return require_session


def make_require_role(config: Config, role: str):
    require_session = make_require_session(config)

    def require_role(session: str | None = Cookie(default=None)) -> dict:
        payload = require_session(session)
        if payload.get("r") != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return payload

    return require_role
