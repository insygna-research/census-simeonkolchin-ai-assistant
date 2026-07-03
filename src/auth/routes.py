"""Auth routes: OIDC login via Authentik."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.config import settings
from src.auth import service as auth_service

logger = logging.getLogger(__name__)
router = APIRouter()

LOGIN_HTML = """<!DOCTYPE html>
<html lang="ru" class="h-full bg-gray-100">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Вход — Team Assistant</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="h-full flex items-center justify-center">
    <div class="w-full max-w-sm">
        <div class="bg-white rounded-2xl shadow-lg p-8">
            <div class="text-center mb-8">
                <h1 class="text-2xl font-bold text-gray-900">Team Assistant</h1>
                <p class="text-sm text-gray-500 mt-1">AI-помощник команды</p>
            </div>
            {error_block}
            <a href="/auth/redirect"
               class="flex items-center justify-center gap-3 w-full px-4 py-3 bg-purple-600 text-white text-sm font-medium rounded-lg hover:bg-purple-700 transition-colors">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"/>
                </svg>
                Войти через Authentik
            </a>
        </div>
        <p class="text-center text-xs text-gray-400 mt-4">Единый вход для всех сервисов компании</p>
    </div>
</body>
</html>"""


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    error = request.query_params.get("error", "")
    error_block = ""
    if error:
        messages = {
            "state_mismatch": "Ошибка безопасности. Попробуйте ещё раз.",
            "token_exchange": "Не удалось получить токен. Попробуйте ещё раз.",
        }
        msg = messages.get(error, "Ошибка авторизации. Попробуйте ещё раз.")
        error_block = f'<div class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{msg}</div>'
    return HTMLResponse(LOGIN_HTML.replace("{error_block}", error_block))


@router.get("/auth/redirect")
async def auth_redirect():
    state = auth_service.generate_state()
    url = auth_service.build_authorize_url(state)
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie("oidc_state", state, httponly=True, max_age=600, samesite="lax", path="/")
    return resp


@router.get("/auth/callback")
async def auth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    saved_state = request.cookies.get("oidc_state")

    if not code:
        return RedirectResponse("/login?error=no_code", status_code=302)

    if state != saved_state:
        return RedirectResponse("/login?error=state_mismatch", status_code=302)

    try:
        tokens = await auth_service.exchange_code(code)
    except Exception as e:
        logger.error(f"OIDC token exchange failed: {e}", exc_info=True)
        return RedirectResponse("/login?error=token_exchange", status_code=302)

    userinfo = None
    id_token = tokens.get("id_token")
    if id_token:
        try:
            userinfo = auth_service.decode_id_token(id_token)
        except Exception as e:
            logger.warning(f"Failed to decode id_token: {e}")

    if not userinfo:
        access_token = tokens.get("access_token")
        if not access_token:
            return RedirectResponse("/login?error=no_token", status_code=302)
        try:
            userinfo = await auth_service.fetch_userinfo(access_token)
        except Exception as e:
            logger.error(f"OIDC userinfo failed: {e}", exc_info=True)
            return RedirectResponse("/login?error=userinfo", status_code=302)

    token = auth_service.create_access_token(userinfo)
    resp = RedirectResponse("/ui", status_code=302)
    resp.set_cookie(
        "ta_token",
        token,
        httponly=True,
        max_age=settings.JWT_EXPIRE_HOURS * 3600,
        samesite="lax",
        path="/",
    )
    resp.delete_cookie("oidc_state", path="/")
    return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("ta_token", path="/")
    return resp
