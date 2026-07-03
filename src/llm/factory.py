"""
LLM Factory using LiteLLM for a unified interface to multiple providers.

Поддерживаются:
  - DeepSeek  (deepseek/<model>)   — нативно в LiteLLM
  - OpenAI    (openai/<model>)     — нативно в LiteLLM, можно указать свой base_url
  - GigaChat  (gigachat/<model>)   — OpenAI-совместимый эндпоинт Сбера +
                                     автоматический OAuth access-токен

Провайдер выбирается по префиксу id модели, поэтому переключение модели в UI
автоматически меняет ключ, base_url и путь обращения.
"""

import os
import logging
import litellm
from typing import Dict, Any, List, Optional, Tuple

from src.config import settings
from src.llm.gigachat_auth import gigachat_auth

logger = logging.getLogger(__name__)


class LLMFactory:
    """Factory for creating and configuring LLM clients"""

    # Runtime state for reasoning mode (can be toggled via API)
    _reasoning_enabled: bool = False

    @classmethod
    def set_reasoning_enabled(cls, enabled: bool):
        """Enable or disable reasoning mode at runtime"""
        cls._reasoning_enabled = enabled

    @classmethod
    def is_reasoning_enabled(cls) -> bool:
        """Check if reasoning mode is enabled"""
        return cls._reasoning_enabled or settings.DEEPSEEK_REASONING

    @staticmethod
    def create():
        """Create and configure the LiteLLM client for all configured providers."""
        # Ключи, которые LiteLLM читает из окружения для нативных провайдеров.
        if settings.DEEPSEEK_API_KEY:
            os.environ["DEEPSEEK_API_KEY"] = settings.DEEPSEEK_API_KEY
        if settings.OPENAI_API_KEY:
            os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
        if settings.DEEPSEEK_BASE_URL:
            os.environ["DEEPSEEK_API_BASE"] = settings.DEEPSEEK_BASE_URL

        # GigaChat использует собственный корневой сертификат (НУЦ Минцифры).
        # Если проверка SSL отключена — отключаем её на уровне LiteLLM-клиента.
        if settings.GIGACHAT_CREDENTIALS and not settings.GIGACHAT_VERIFY_SSL:
            litellm.ssl_verify = False

        litellm.drop_params = True
        litellm.set_verbose = settings.LOG_LEVEL == "DEBUG"

        return LLMClient()


class LLMClient:
    """Wrapper around LiteLLM for a consistent, provider-agnostic interface"""

    def __init__(self):
        # Дефолтная модель активного провайдера в формате "<provider>/<model>".
        self._base_model = settings.get_default_model()

    @property
    def model(self) -> str:
        """Get current default model id (provider-prefixed), considering reasoning mode"""
        return self._apply_reasoning(self._base_model)

    @staticmethod
    def _apply_reasoning(model_id: str) -> str:
        """Для legacy DeepSeek-моделей включить reasoner при включённом reasoning-режиме."""
        provider = settings.get_provider_from_model(model_id)
        if provider != "deepseek":
            return model_id
        if LLMFactory.is_reasoning_enabled() and "v4" not in model_id and "reasoner" not in model_id:
            return "deepseek/deepseek-reasoner"
        return model_id

    def _resolve_call(self, model_id: str) -> Tuple[str, Dict[str, Any]]:
        """
        Преобразовать id модели из UI в параметры вызова LiteLLM.

        Возвращает (litellm_model, extra_params), где extra_params содержит
        api_key/api_base под конкретного провайдера.
        """
        model_id = self._apply_reasoning(model_id)
        provider = settings.get_provider_from_model(model_id)
        extra: Dict[str, Any] = {}

        if provider == "gigachat":
            # gigachat/GigaChat-2-Max -> openai/GigaChat-2-Max + Bearer access-токен.
            real_model = model_id.split("/", 1)[1] if "/" in model_id else settings.GIGACHAT_MODEL
            extra["api_base"] = settings.GIGACHAT_BASE_URL
            extra["api_key"] = gigachat_auth.get_token()
            return f"openai/{real_model}", extra

        if provider == "openai":
            if settings.OPENAI_API_KEY:
                extra["api_key"] = settings.OPENAI_API_KEY
            if settings.OPENAI_BASE_URL:
                extra["api_base"] = settings.OPENAI_BASE_URL
            return model_id, extra

        if provider == "deepseek":
            if settings.DEEPSEEK_API_KEY:
                extra["api_key"] = settings.DEEPSEEK_API_KEY
            if settings.DEEPSEEK_BASE_URL:
                extra["api_base"] = settings.DEEPSEEK_BASE_URL
            model_id = model_id if model_id.startswith("deepseek/") else f"deepseek/{model_id}"
            return model_id, extra

        # Неизвестный провайдер — отдаём как есть, пусть LiteLLM разбирается.
        return model_id, extra

    def is_reasoning_mode(self) -> bool:
        """Check if currently in reasoning mode"""
        return LLMFactory.is_reasoning_enabled()

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Create a chat completion with optional tool calling.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tool definitions
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            model: Optional model override ("<provider>/<model>")
            **kwargs: Additional arguments for litellm

        Returns:
            LiteLLM response object
        """
        litellm_model, extra = self._resolve_call(model or self._base_model)
        params = {
            "model": litellm_model,
            "messages": messages,
            "temperature": temperature,
        }

        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        if max_tokens:
            params["max_tokens"] = max_tokens

        params.update(extra)
        params.update(kwargs)

        try:
            response = litellm.completion(**params)
            return response
        except Exception as e:
            raise RuntimeError(f"LLM API call failed: {str(e)}") from e

    async def achat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Async version of chat_completion.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tool definitions
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            model: Optional model override ("<provider>/<model>")
            **kwargs: Additional arguments for litellm

        Returns:
            LiteLLM response object (with optional reasoning_content attribute)
        """
        litellm_model, extra = self._resolve_call(model or self._base_model)
        params = {
            "model": litellm_model,
            "messages": messages,
            "temperature": temperature,
        }

        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        if max_tokens:
            params["max_tokens"] = max_tokens

        params.update(extra)
        params.update(kwargs)

        try:
            is_reasoner = "reasoner" in litellm_model
            timeout = params.pop("timeout", 300 if is_reasoner else 120)
            response = await litellm.acompletion(**params, timeout=timeout)

            if is_reasoner and response.choices:
                choice = response.choices[0]
                if hasattr(choice.message, 'reasoning_content'):
                    response._reasoning_content = choice.message.reasoning_content
                elif hasattr(choice, 'reasoning_content'):
                    response._reasoning_content = choice.reasoning_content
                else:
                    response._reasoning_content = None
            else:
                response._reasoning_content = None

            return response
        except Exception as e:
            raise RuntimeError(f"LLM API call failed: {str(e)}") from e

    def extract_reasoning(self, response: Any) -> Optional[str]:
        """Extract reasoning content from a response if available"""
        if hasattr(response, '_reasoning_content'):
            return response._reasoning_content
        return None

    def count_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        Count tokens in a list of messages.

        Args:
            messages: List of message dictionaries

        Returns:
            Approximate token count
        """
        try:
            litellm_model, _ = self._resolve_call(self._base_model)
            return litellm.token_counter(model=litellm_model, messages=messages)
        except Exception:
            # Fallback: approximate 4 chars per token
            total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
            return total_chars // 4
