"""Тестовая заглушка REST API для передачи лидов (POST /leads).

Реальной CRM у заказчика нет. Каждый лид всегда сохраняется локально в
SQLite (таблица leads) — это гарантирует, что заявка не потеряется, даже
если внешний вебхук недоступен или не настроен. Если задан
CRM_WEBHOOK_URL, дополнительно выполняется настоящий POST-запрос с retry —
структура тела запроса уже готова к замене заглушки на реальный эндпоинт
заказчика.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from bot.config import settings
from bot.models import Lead

logger = logging.getLogger(__name__)


def _connect() -> sqlite3.Connection:
    Path(settings.leads_db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(settings.leads_db_path)


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                lead_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                contact TEXT NOT NULL,
                question_topic TEXT NOT NULL,
                status TEXT NOT NULL,
                comment TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def _save_local(lead: Lead) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO leads
                (lead_id, name, contact, question_topic, status, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead.lead_id,
                lead.name,
                lead.contact,
                lead.question_topic,
                lead.status.value,
                lead.comment,
                lead.created_at,
            ),
        )


@retry(
    reraise=True,
    stop=stop_after_attempt(settings.retry_attempts),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
)
async def _post_to_webhook(lead: Lead) -> None:
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.post(
            settings.crm_webhook_url, json=lead.model_dump(mode="json")
        )
        response.raise_for_status()


async def submit_lead(lead: Lead) -> Lead:
    """Сохраняет лид локально и (если настроено) отправляет во внешнюю CRM."""
    init_db()
    _save_local(lead)
    logger.info(
        "[CRM STUB] лид сохранён локально: lead_id=%s topic=%s status=%s",
        lead.lead_id,
        lead.question_topic,
        lead.status.value,
    )

    if settings.crm_webhook_url:
        try:
            await _post_to_webhook(lead)
            logger.info("[CRM STUB] лид %s отправлен во внешнюю систему", lead.lead_id)
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            logger.error(
                "[CRM STUB] не удалось отправить лид %s во внешнюю систему: %s",
                lead.lead_id,
                exc,
            )
    else:
        logger.info(
            "[CRM STUB] CRM_WEBHOOK_URL не задан — лид доступен только в локальной БД"
        )

    return lead


def get_all_leads() -> list[dict]:
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]
