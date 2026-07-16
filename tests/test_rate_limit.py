from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from bot.rate_limit import RateLimitMiddleware


def _make_message(chat_id: int) -> MagicMock:
    message = MagicMock()
    # __class__ подменяем, чтобы isinstance(event, Message) в middleware сработал
    message.__class__ = Message
    message.chat = MagicMock(id=chat_id)
    message.answer = AsyncMock()
    return message


@pytest.mark.asyncio
async def test_first_message_passes_through():
    middleware = RateLimitMiddleware(min_interval_seconds=1.0)
    handler = AsyncMock(return_value="ok")
    message = _make_message(chat_id=1)

    result = await middleware(handler, message, {})

    assert result == "ok"
    handler.assert_awaited_once()
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_second_message_too_soon_is_blocked():
    middleware = RateLimitMiddleware(min_interval_seconds=10.0)
    handler = AsyncMock(return_value="ok")
    message = _make_message(chat_id=2)

    await middleware(handler, message, {})
    result = await middleware(handler, message, {})

    assert result is None
    handler.assert_awaited_once()  # второй вызов не дошёл до хендлера
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_different_chats_are_independent():
    middleware = RateLimitMiddleware(min_interval_seconds=10.0)
    handler = AsyncMock(return_value="ok")
    message_a = _make_message(chat_id=1)
    message_b = _make_message(chat_id=2)

    await middleware(handler, message_a, {})
    result_b = await middleware(handler, message_b, {})

    assert result_b == "ok"
    assert handler.await_count == 2
