"""Устанавливает имя и описание бота через Bot API (не требует BotFather).

В отличие от аватарки (только через @BotFather, см. assets/generate_avatar.py),
имя и описание бот может выставить себе сам через API — запускать повторно
при изменении текста ниже.

Запуск:
    python scripts/setup_bot_profile.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot

from bot.config import settings

BOT_NAME = "Помощник по продажам"
SHORT_DESCRIPTION = (
    "Отвечу на вопросы о продукте, тарифах и подписке. Помогу оставить "
    "заявку менеджеру."
)
DESCRIPTION = (
    "Здравствуйте! Я бот отдела продаж 👋\n\n"
    "Отвечу на вопросы о тарифах, условиях подписки, интеграциях и "
    "поддержке, помогу разобраться в продукте и передам заявку менеджеру, "
    "если понадобится живое общение."
)


async def main() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан в .env")

    bot = Bot(token=settings.telegram_bot_token)
    try:
        await bot.set_my_name(BOT_NAME)
        await bot.set_my_short_description(SHORT_DESCRIPTION)
        await bot.set_my_description(DESCRIPTION)
        print("Имя и описание бота обновлены.")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
