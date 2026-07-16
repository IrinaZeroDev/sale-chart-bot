"""Обёртка над GigaChat через ProxyAPI: retry, таймауты, валидация ответа.

Ключ ProxyAPI никогда не логируется и не попадает в текст промпта — только
в заголовок Authorization исходящего HTTP-запроса.

Без ключа ProxyAPI (settings.gigachat_mock_mode) используется офлайн-заглушка
MockGigaChatClient, чтобы диалоговую логику можно было тестировать локально
без реальных кредов — см. console_test.py.
"""
from __future__ import annotations

import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bot.config import settings

logger = logging.getLogger(__name__)


class GigaChatError(Exception):
    """Базовая ошибка клиента GigaChat."""


class GigaChatUnavailableError(GigaChatError):
    """Сеть/лимиты/невалидный ответ — после исчерпания retry."""


class BaseGigaChatClient:
    async def generate(self, system_prompt: str, user_message: str) -> str:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


class GigaChatClient(BaseGigaChatClient):
    """Реальный клиент поверх ProxyAPI (OpenAI-совместимый chat/completions).

    ЗАГЛУШКА/ПРОВЕРИТЬ: точный путь эндпоинта и формат тела запроса нужно
    сверить с актуальной документацией ProxyAPI (proxyapi.ru) перед боевым
    использованием — здесь предполагается OpenAI-совместимая схема
    {model, messages: [{role, content}]}.
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"Authorization": f"Bearer {settings.proxyapi_key}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.retry_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(GigaChatUnavailableError),
    )
    async def generate(self, system_prompt: str, user_message: str) -> str:
        # Сетевые сбои и лимиты всегда переводятся в GigaChatUnavailableError,
        # чтобы после исчерпания retry наружу уходило единообразное
        # исключение (dialog.py ловит именно его для эскалации на менеджера),
        # а не «сырое» httpx-исключение.
        payload = {
            "model": settings.gigachat_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.3,
        }
        try:
            response = await self._client.post(
                settings.proxyapi_base_url, json=payload
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            logger.warning("GigaChat/ProxyAPI: сетевой сбой запроса, будет retry")
            raise GigaChatUnavailableError("network error") from exc

        if response.status_code == 429:
            logger.warning("GigaChat/ProxyAPI: превышен лимит запросов (429)")
            raise GigaChatUnavailableError("rate limited")

        if response.status_code in (401, 403):
            # Авторизация — не повторяем автоматически без действий человека
            logger.error("GigaChat/ProxyAPI: ошибка авторизации %s", response.status_code)
            raise GigaChatError("auth error")

        if response.status_code >= 500:
            logger.warning("GigaChat/ProxyAPI: ошибка сервера %s", response.status_code)
            raise GigaChatUnavailableError(f"server error {response.status_code}")

        if response.status_code != 200:
            logger.error("GigaChat/ProxyAPI: неожиданный статус %s", response.status_code)
            raise GigaChatError(f"unexpected status {response.status_code}")

        return self._extract_content(response)

    @staticmethod
    def _extract_content(response: httpx.Response) -> str:
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            logger.error("GigaChat/ProxyAPI: невалидный формат ответа")
            raise GigaChatUnavailableError("invalid response payload")

        content = (content or "").strip()
        if not content:
            logger.error("GigaChat/ProxyAPI: пустой ответ модели")
            raise GigaChatUnavailableError("empty response")

        return content


class MockGigaChatClient(BaseGigaChatClient):
    """Офлайн-заглушка для разработки/тестов без ключей ProxyAPI.

    Не делает сетевых вызовов — просто аккуратно оборачивает переданный в
    system_prompt контекст базы знаний в связный ответ, чтобы можно было
    проверить весь сценарий диалога локально (см. console_test.py).
    """

    async def generate(self, system_prompt: str, user_message: str) -> str:
        logger.info("[MOCK GigaChat] запрос без обращения к сети")
        context = _extract_context(system_prompt)
        if context:
            return context
        return (
            "Не нашёл точного ответа в базе знаний по вашему вопросу — "
            "передам его менеджеру."
        )


def _extract_context(system_prompt: str) -> str:
    marker = "КОНТЕКСТ:"
    if marker not in system_prompt:
        return ""
    return system_prompt.split(marker, 1)[1].strip()


def get_gigachat_client() -> BaseGigaChatClient:
    if settings.gigachat_mock_mode:
        return MockGigaChatClient()
    return GigaChatClient()
