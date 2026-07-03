"""
GigaChat OAuth token manager.

GigaChat не является OpenAI-совместимым по авторизации: вместо статичного
API-ключа используется access-токен, который выдаётся в обмен на
"Authorization key" (Base64 client_id:secret) и живёт ~30 минут.

Этот модуль инкапсулирует получение и кеширование токена, чтобы фабрика LLM
могла обращаться к GigaChat как к обычному OpenAI-совместимому эндпоинту
(api_base + Bearer access_token).
"""

import time
import uuid
import logging
import threading
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# За сколько секунд до истечения токена считаем его протухшим и обновляем.
_EXPIRY_SKEW_SEC = 60


class GigaChatAuth:
    """Потокобезопасный кеш access-токена GigaChat."""

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def _is_valid(self) -> bool:
        return bool(self._token) and (time.time() < self._expires_at - _EXPIRY_SKEW_SEC)

    def get_token(self, force_refresh: bool = False) -> str:
        """Вернуть валидный access-токен, при необходимости запросив новый."""
        if not force_refresh and self._is_valid():
            return self._token  # type: ignore[return-value]

        with self._lock:
            # Повторная проверка внутри лока — токен мог обновить другой поток.
            if not force_refresh and self._is_valid():
                return self._token  # type: ignore[return-value]
            return self._refresh()

    def _refresh(self) -> str:
        credentials = settings.GIGACHAT_CREDENTIALS
        if not credentials:
            raise RuntimeError(
                "GIGACHAT_CREDENTIALS не задан — невозможно получить access-токен GigaChat."
            )

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {credentials}",
        }
        data = {"scope": settings.GIGACHAT_SCOPE}

        try:
            with httpx.Client(verify=settings.GIGACHAT_VERIFY_SSL, timeout=30) as client:
                resp = client.post(settings.GIGACHAT_AUTH_URL, headers=headers, data=data)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Не удалось получить токен GigaChat: {e}") from e

        token = payload.get("access_token")
        if not token:
            raise RuntimeError(f"Ответ GigaChat OAuth без access_token: {payload}")

        # expires_at приходит в миллисекундах epoch; на случай отсутствия — +25 мин.
        expires_at_ms = payload.get("expires_at")
        if expires_at_ms:
            self._expires_at = float(expires_at_ms) / 1000.0
        else:
            self._expires_at = time.time() + 25 * 60

        self._token = token
        logger.info("GigaChat access-токен обновлён (действует до %.0f)", self._expires_at)
        return token


# Единый разделяемый экземпляр на процесс.
gigachat_auth = GigaChatAuth()
