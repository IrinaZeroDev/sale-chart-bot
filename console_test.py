"""Консольный тест-харнесс для проверки диалога без Telegram-токена и ключей.

Запуск:
    python console_test.py

Дополнительно:
    python console_test.py --show-leads   — показать сохранённые заявки
    python console_test.py --show-stats   — показать статистику взаимодействий

Логика диалога полностью совпадает с той, что использует Telegram-бот
(bot/dialog.py) — отличается только транспорт (ввод/вывод в консоли вместо
Telegram-сообщений). Без PROXYAPI_KEY GigaChat работает в офлайн-режиме и
отвечает напрямую на основе базы знаний.
"""
from __future__ import annotations

import asyncio
import sys

# На Windows консоль по умолчанию может быть не в UTF-8 — без этого кириллица
# и эмодзи (👍/👎) в диалоге и результатах могут отображаться некорректно.
if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stdin, "reconfigure") and sys.stdin.encoding and sys.stdin.encoding.lower() != "utf-8":
    sys.stdin.reconfigure(encoding="utf-8")

from bot import crm_stub, dialog, stats
from bot.config import settings
from bot.gigachat_client import get_gigachat_client
from bot.knowledge_base import KNOWLEDGE_BASE
from bot.models import DialogSession

FAQ_TOPICS = list(KNOWLEDGE_BASE.keys())


def _faq_menu_text() -> str:
    lines = ["Темы FAQ (введите номер):"]
    for i, topic in enumerate(FAQ_TOPICS, start=1):
        lines.append(f"  {i}. {KNOWLEDGE_BASE[topic].title}")
    return "\n".join(lines)


def _print_table(rows: list[dict], columns: list[str]) -> None:
    if not rows:
        print("(пусто)")
        return
    for row in rows:
        print(" | ".join(f"{col}={row.get(col)}" for col in columns))


def show_leads() -> None:
    rows = crm_stub.get_all_leads()
    print(f"Сохранённые заявки ({len(rows)}):")
    _print_table(rows, ["lead_id", "name", "contact", "question_topic", "status", "created_at"])


def show_stats() -> None:
    rows = stats.get_all_interactions()
    print(f"Статистика взаимодействий ({len(rows)}):")
    _print_table(rows, ["chat_id", "topic", "answered_by", "rating", "created_at"])


async def run_console() -> None:
    stats.init_db()
    crm_stub.init_db()

    if settings.gigachat_mock_mode:
        print(
            "[офлайн-режим] PROXYAPI_KEY не задан — GigaChat не вызывается, "
            "ответы формируются из базы знаний напрямую.\n"
        )

    client = get_gigachat_client()
    session = DialogSession(chat_id="console-user")
    print(dialog.start_dialog(session))
    print("(введите 'выход' — закончить сессию, 'faq' — меню тем кнопками)\n")

    faq_menu_open = False
    try:
        while True:
            try:
                user_text = input("Вы: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_text:
                continue
            if user_text.lower() in ("выход", "exit", "quit"):
                break

            if user_text.lower() in ("faq", "/faq"):
                faq_menu_open = True
                print(_faq_menu_text() + "\n")
                continue

            if faq_menu_open and user_text.isdigit() and 1 <= int(user_text) <= len(FAQ_TOPICS):
                faq_menu_open = False
                topic = FAQ_TOPICS[int(user_text) - 1]
                reply = await dialog.handle_faq_selection(session, client, topic)
                print(f"Бот: {reply}\n")
                if session.state.value == "closed":
                    break
                continue

            faq_menu_open = False
            reply = await dialog.handle_message(session, client, user_text)
            print(f"Бот: {reply}\n")

            if session.state.value == "closed":
                break
    finally:
        await client.aclose()

    show_leads()
    show_stats()


if __name__ == "__main__":
    if "--show-leads" in sys.argv:
        show_leads()
    elif "--show-stats" in sys.argv:
        show_stats()
    else:
        asyncio.run(run_console())
