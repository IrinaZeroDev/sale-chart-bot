"""Обработчики Telegram-сообщений (aiogram) — тонкий транспортный слой.

Вся бизнес-логика вынесена в dialog.py, здесь только маппинг Telegram-апдейтов
на вызовы движка диалога и хранение сессий в памяти процесса.
"""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot import dialog
from bot.gigachat_client import BaseGigaChatClient
from bot.models import DialogSession

logger = logging.getLogger(__name__)

router = Router()

# Сессии в памяти процесса — для MVP этого достаточно, при рестарте бота
# диалоги начинаются заново (история диалогов сохраняется отдельно в stats.py).
_sessions: dict[str, DialogSession] = {}


def _get_session(chat_id: str) -> DialogSession:
    if chat_id not in _sessions:
        _sessions[chat_id] = DialogSession(chat_id=chat_id)
    return _sessions[chat_id]


def build_router(client: BaseGigaChatClient) -> Router:
    @router.message(CommandStart())
    async def on_start(message: Message) -> None:
        chat_id = str(message.chat.id)
        session = DialogSession(chat_id=chat_id)
        _sessions[chat_id] = session
        greeting = dialog.start_dialog(session)
        await message.answer(greeting)

    @router.message()
    async def on_message(message: Message) -> None:
        chat_id = str(message.chat.id)
        session = _get_session(chat_id)
        user_text = message.text or ""

        try:
            reply = await dialog.handle_message(session, client, user_text)
        except Exception:
            logger.exception("Необработанная ошибка при обработке сообщения chat_id=%s", chat_id)
            reply = (
                "Произошла техническая неполадка, уже разбираемся. "
                "Попробуйте, пожалуйста, ещё раз чуть позже."
            )

        await message.answer(reply)

    return router
