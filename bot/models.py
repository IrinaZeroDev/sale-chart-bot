"""Pydantic-модели: лид, сообщение диалога, состояние сессии."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Topic(str, Enum):
    PRICE = "цена"
    SUBSCRIPTION_TERMS = "подписка"
    INTEGRATIONS = "интеграции"
    SUPPORT = "поддержка"
    TARIFF_DIFF = "тарифы_отличия"
    DEMO = "демо"
    PAYMENT = "оплата"
    TECH_ISSUE = "техпроблема"
    OTHER = "другое"


class LeadStatus(str, Enum):
    NEW = "new"
    NEEDS_MANAGER = "needs_manager"


class Lead(BaseModel):
    """Структура заявки — совместима со схемой из спецификации заказчика.

    Поле `comment` добавлено сверх примера в спецификации согласно
    требованиям приёмки (нужно собирать комментарий клиента).
    """

    lead_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    contact: str
    question_topic: str
    status: LeadStatus = LeadStatus.NEW
    comment: Optional[str] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class DialogState(str, Enum):
    GREETING = "greeting"
    CHATTING = "chatting"
    AWAITING_CONSENT = "awaiting_consent"
    COLLECTING_NAME = "collecting_name"
    COLLECTING_CONTACT = "collecting_contact"
    COLLECTING_COMMENT = "collecting_comment"
    AWAITING_RATING = "awaiting_rating"
    CLOSED = "closed"


class DialogSession(BaseModel):
    """Состояние одного диалога. Не зависит от транспорта (Telegram/консоль)."""

    chat_id: str
    state: DialogState = DialogState.GREETING
    user_message_count: int = 0
    last_topic: Optional[Topic] = None
    consent_given: Optional[bool] = None
    lead_name: Optional[str] = None
    lead_contact: Optional[str] = None
    lead_comment: Optional[str] = None
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
