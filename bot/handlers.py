"""Обработчики Telegram-сообщений (aiogram) — тонкий транспортный слой.

Вся бизнес-логика вынесена в dialog.py, здесь только маппинг Telegram-апдейтов
на вызовы движка диалога, разметка кнопок и хранение сессий в памяти процесса.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from bot import dialog
from bot.gigachat_client import BaseGigaChatClient
from bot.knowledge_base import KNOWLEDGE_BASE
from bot.models import DialogSession, Topic

logger = logging.getLogger(__name__)

router = Router()

FAQ_BUTTON_TEXT = "📋 FAQ"
PRICE_BUTTON_TEXT = "💰 Цены"
ABOUT_BUTTON_TEXT = "📦 О продукте"
LEAD_BUTTON_TEXT = "📝 Оставить заявку"

# Сессии в памяти процесса — для MVP этого достаточно, при рестарте бота
# диалоги начинаются заново (история диалогов сохраняется отдельно в stats.py).
_sessions: dict[str, DialogSession] = {}


def _get_session(chat_id: str) -> DialogSession:
    if chat_id not in _sessions:
        _sessions[chat_id] = DialogSession(chat_id=chat_id)
    return _sessions[chat_id]


def _main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=FAQ_BUTTON_TEXT), KeyboardButton(text=PRICE_BUTTON_TEXT)],
            [KeyboardButton(text=ABOUT_BUTTON_TEXT), KeyboardButton(text=LEAD_BUTTON_TEXT)],
        ],
        resize_keyboard=True,
    )


def _faq_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=entry.title, callback_data=f"faq:{topic.value}")]
        for topic, entry in KNOWLEDGE_BASE.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_router(client: BaseGigaChatClient) -> Router:
    """Регистрирует все Telegram-обработчики на общем клиенте GigaChat.

    client передаётся один раз при старте (см. main.py) и переиспользуется
    во всех хендлерах — так что нет накладных расходов на создание нового
    HTTP-клиента на каждое сообщение.
    """

    @router.message(CommandStart())
    async def on_start(message: Message) -> None:
        chat_id = str(message.chat.id)
        session = DialogSession(chat_id=chat_id)
        _sessions[chat_id] = session
        greeting = dialog.start_dialog(session)
        await message.answer(greeting, reply_markup=_main_menu_keyboard())

    @router.message(F.text == FAQ_BUTTON_TEXT)
    async def on_faq_button(message: Message) -> None:
        await message.answer("Выберите тему вопроса:", reply_markup=_faq_inline_keyboard())

    @router.message(F.text == PRICE_BUTTON_TEXT)
    async def on_price_button(message: Message) -> None:
        session = _get_session(str(message.chat.id))
        reply = await dialog.handle_faq_selection(session, client, Topic.PRICE)
        await message.answer(reply)

    @router.message(F.text == ABOUT_BUTTON_TEXT)
    async def on_about_button(message: Message) -> None:
        session = _get_session(str(message.chat.id))
        await message.answer(dialog.answer_product_pitch(session))

    @router.message(F.text == LEAD_BUTTON_TEXT)
    async def on_lead_button(message: Message) -> None:
        session = _get_session(str(message.chat.id))
        await message.answer(dialog.start_lead_collection(session))

    @router.callback_query(F.data.startswith("faq:"))
    async def on_faq_selected(callback: CallbackQuery) -> None:
        if callback.message is None or callback.data is None:
            await callback.answer()
            return

        chat_id = str(callback.message.chat.id)
        session = _get_session(chat_id)

        try:
            topic = Topic(callback.data.split("faq:", 1)[1])
            reply = await dialog.handle_faq_selection(session, client, topic)
        except Exception:
            logger.exception("Ошибка при обработке FAQ-кнопки chat_id=%s", chat_id)
            reply = (
                "Произошла техническая неполадка, уже разбираемся. "
                "Попробуйте, пожалуйста, ещё раз чуть позже."
            )

        await callback.message.answer(reply)
        await callback.answer()

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
