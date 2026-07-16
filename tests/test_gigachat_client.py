from unittest.mock import AsyncMock, patch

import httpx
import pytest

from bot.gigachat_client import (
    GigaChatClient,
    GigaChatError,
    GigaChatUnavailableError,
    MockGigaChatClient,
)


@pytest.mark.asyncio
async def test_generate_returns_content_on_success():
    client = GigaChatClient()
    response = httpx.Response(200, json={"choices": [{"message": {"content": "Привет!"}}]})
    with patch.object(client._client, "post", AsyncMock(return_value=response)):
        result = await client.generate("system", "вопрос")
    assert result == "Привет!"
    await client.aclose()


@pytest.mark.asyncio
async def test_generate_retries_then_succeeds():
    client = GigaChatClient()
    response = httpx.Response(200, json={"choices": [{"message": {"content": "Готово"}}]})
    mock_post = AsyncMock(side_effect=[httpx.TimeoutException("timeout"), response])
    with patch.object(client._client, "post", mock_post):
        result = await client.generate("system", "вопрос")
    assert result == "Готово"
    assert mock_post.await_count == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_generate_raises_unavailable_after_exhausted_retries():
    client = GigaChatClient()
    mock_post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    with patch.object(client._client, "post", mock_post):
        with pytest.raises(GigaChatUnavailableError):
            await client.generate("system", "вопрос")
    await client.aclose()


@pytest.mark.asyncio
async def test_generate_raises_unavailable_on_empty_content():
    client = GigaChatClient()
    response = httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]})
    with patch.object(client._client, "post", AsyncMock(return_value=response)):
        with pytest.raises(GigaChatUnavailableError):
            await client.generate("system", "вопрос")
    await client.aclose()


@pytest.mark.asyncio
async def test_generate_raises_error_on_auth_failure_without_retry():
    client = GigaChatClient()
    response = httpx.Response(401, json={"error": "unauthorized"})
    mock_post = AsyncMock(return_value=response)
    with patch.object(client._client, "post", mock_post):
        with pytest.raises(GigaChatError):
            await client.generate("system", "вопрос")
    assert mock_post.await_count == 1  # ошибки авторизации не повторяются
    await client.aclose()


@pytest.mark.asyncio
async def test_mock_client_uses_context_from_prompt():
    client = MockGigaChatClient()
    prompt = "правила...\n\nКОНТЕКСТ:\nТестовый ответ из базы знаний"
    result = await client.generate(prompt, "вопрос")
    assert "Тестовый ответ" in result


@pytest.mark.asyncio
async def test_mock_client_falls_back_without_context():
    client = MockGigaChatClient()
    result = await client.generate("правила без контекста", "вопрос")
    assert "менеджер" in result.lower()
