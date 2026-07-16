"""Простой антиспам-троттлинг: не чаще одного сообщения от chat_id за интервал.

In-memory реализация — для MVP этого достаточно (сессии и так живут в памяти
процесса, см. handlers.py). При горизонтальном масштабировании на несколько
инстансов потребуется вынести состояние в общее хранилище (Redis и т.п.).
"""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.messages import RATE_LIMITED_MESSAGE


class RateLimitMiddleware(BaseMiddleware):
    """Ограничивает частоту обработки апдейтов от одного чата."""

    def __init__(self, min_interval_seconds: float = 1.0) -> None:
        self._min_interval = min_interval_seconds
        self._last_seen: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        chat_id = _extract_chat_id(event)
        if chat_id is not None:
            now = time.monotonic()
            last = self._last_seen.get(chat_id)
            if last is not None and (now - last) < self._min_interval:
                await _notify_rate_limited(event)
                return None
            self._last_seen[chat_id] = now
        return await handler(event, data)


def _extract_chat_id(event: TelegramObject) -> Optional[int]:
    if isinstance(event, Message):
        return event.chat.id
    if isinstance(event, CallbackQuery) and event.message is not None:
        return event.message.chat.id
    return None


async def _notify_rate_limited(event: TelegramObject) -> None:
    if isinstance(event, Message):
        await event.answer(RATE_LIMITED_MESSAGE)
    elif isinstance(event, CallbackQuery):
        await event.answer(RATE_LIMITED_MESSAGE, show_alert=False)
