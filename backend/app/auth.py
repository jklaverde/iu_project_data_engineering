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


def create_session_token(username: str, config: Config) -> str:
    payload = {"u": username, "exp": time.time() + config.session_ttl_seconds}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
    signature = _sign(payload_b64, config.session_secret)
    return f"{payload_b64.decode('ascii')}.{signature}"


def verify_session_token(token: str, config: Config) -> bool:
    try:
        payload_b64_str, signature = token.split(".", 1)
    except ValueError:
        return False

    payload_b64 = payload_b64_str.encode("ascii")
    expected_signature = _sign(payload_b64, config.session_secret)
    if not hmac.compare_digest(signature, expected_signature):
        return False

    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return False

    return payload.get("exp", 0) > time.time()


def check_credentials(username: str, password: str, config: Config) -> bool:
    valid_username = hmac.compare_digest(username, config.admin_username)
    valid_password = hmac.compare_digest(password, config.admin_password)
    return valid_username and valid_password


def make_require_session(config: Config):
    def require_session(session: str | None = Cookie(default=None)) -> None:
        if session is None or not verify_session_token(session, config):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return require_session
