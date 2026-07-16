"""Точка входа: инициализация aiogram-бота и запуск long polling."""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher

from bot import crm_stub, stats
from bot.config import settings
from bot.gigachat_client import get_gigachat_client
from bot.handlers import build_router
from bot.rate_limit import RateLimitMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not settings.telegram_bot_token:
        logger.error(
            "TELEGRAM_BOT_TOKEN не задан в .env — Telegram-бот не может "
            "запуститься. Для тестирования диалога без токена используйте "
            "console_test.py."
        )
        sys.exit(1)

    stats.init_db()
    crm_stub.init_db()

    if settings.gigachat_mock_mode:
        logger.warning(
            "PROXYAPI_KEY не задан — GigaChat работает в офлайн-режиме "
            "(ответы формируются напрямую из базы знаний, без обращения к сети)."
        )

    client = get_gigachat_client()
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()

    rate_limiter = RateLimitMiddleware(min_interval_seconds=settings.rate_limit_seconds)
    dispatcher.message.middleware(rate_limiter)
    dispatcher.callback_query.middleware(rate_limiter)

    dispatcher.include_router(build_router(client))

    try:
        logger.info("Бот запущен, начинаю polling")
        await dispatcher.start_polling(bot)
    finally:
        await client.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
