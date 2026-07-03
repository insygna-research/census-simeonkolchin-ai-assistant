"""Authentication middleware — checks JWT cookie on every request."""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from src.auth.service import decode_access_token
from src.config import settings

logger = logging.getLogger(__name__)

PUBLIC_PREFIXES = (
    "/login", "/auth/", "/static/", "/health",
    "/.well-known/", "/a2a",
    "/api/", "/ws/",
)

PROTECTED_PREFIXES = ("/ui", "/telegram-admin")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if settings.AUTH_DISABLED:
            request.state.user_sub = "local"
            request.state.username = "local"
            return await call_next(request)

        path = request.url.path

        if any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        if path == "/" and request.method == "POST":
            return await call_next(request)

        if path == "/" or any(path.startswith(p) for p in PROTECTED_PREFIXES):
            token = request.cookies.get("ta_token")
            if not token:
                return RedirectResponse("/login", status_code=302)

            payload = decode_access_token(token)
            if payload is None:
                resp = RedirectResponse("/login", status_code=302)
                resp.delete_cookie("ta_token")
                return resp

            request.state.user_sub = payload["sub"]
            request.state.username = payload.get("username", "")

        return await call_next(request)
