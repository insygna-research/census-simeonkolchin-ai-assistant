"""Authentication service: OIDC via Authentik, JWT session."""

import logging
import secrets
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import httpx
import jwt

from src.config import settings

logger = logging.getLogger(__name__)


def create_access_token(userinfo: dict) -> str:
    payload = {
        "sub": userinfo.get("sub", ""),
        "username": userinfo.get("preferred_username", ""),
        "email": userinfo.get("email", ""),
        "name": userinfo.get("name", ""),
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def build_authorize_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.OIDC_CLIENT_ID,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "scope": settings.OIDC_SCOPES,
        "state": state,
    }
    base = settings.OIDC_ISSUER_URL.rstrip("/").rsplit("/application/o/", 1)[0]
    return f"{base}/application/o/authorize/?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    base = settings.OIDC_ISSUER_URL.rstrip("/").rsplit("/application/o/", 1)[0]
    token_url = f"{base}/application/o/token/"

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.OIDC_REDIRECT_URI,
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


def decode_id_token(id_token: str) -> dict:
    return jwt.decode(
        id_token,
        settings.OIDC_CLIENT_SECRET,
        algorithms=["HS256"],
        audience=settings.OIDC_CLIENT_ID,
        options={"verify_exp": True},
    )


async def fetch_userinfo(access_token: str) -> dict:
    base = settings.OIDC_ISSUER_URL.rstrip("/").rsplit("/application/o/", 1)[0]
    userinfo_url = f"{base}/application/o/userinfo/"

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp = await client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


def generate_state() -> str:
    return secrets.token_urlsafe(32)
