"""Движок диалога — вся бизнес-логика сценария, не зависящая от транспорта.

Используется и Telegram-обработчиками (handlers.py), и консольным
тест-харнессом (console_test.py), поэтому его можно тестировать и
эксплуатировать без Telegram-токена.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

from bot import crm_stub, stats
from bot.config import settings
from bot.gigachat_client import BaseGigaChatClient, GigaChatError, GigaChatUnavailableError
from bot.knowledge_base import GREETING_TEXT, KNOWLEDGE_BASE, PRODUCT_PITCH, find_topic, get_answer
from bot.messages import (
    ASK_COMMENT,
    ASK_CONTACT,
    ASK_NAME,
    CLOSE_KEYWORDS,
    CLOSED_MESSAGE,
    CLOSING_MESSAGE,
    COMMENT_TOO_LONG_RETRY,
    CONSENT_DECLINED,
    CONSENT_PROMPT_SUFFIX,
    CONSENT_UNCLEAR,
    CONTACT_EMPTY_RETRY,
    CONTACT_TOO_LONG_RETRY,
    FALLBACK_MESSAGE,
    GREETING_KEYWORDS,
    GREETING_SMALLTALK_REPLY,
    LEAD_SUBMITTED_MESSAGE,
    MANAGER_REQUEST_KEYWORDS,
    NAME_EMPTY_RETRY,
    NAME_TOO_LONG_RETRY,
    NEGATIVE_WORDS,
    OFF_TOPIC_MESSAGE,
    POSITIVE_WORDS,
    RATING_NEGATIVE_WORDS,
    RATING_POSITIVE_WORDS,
    RATING_THANKS_PREFIX,
    SCOPE_KEYWORDS,
    SKIP_WORDS,
    STEP_IN_PROGRESS_RETRY,
    SYSTEM_PROMPT_TEMPLATE,
    THANKS_KEYWORDS,
    THANKS_REPLY,
)
from bot.models import (
    MAX_COMMENT_LENGTH,
    MAX_CONTACT_LENGTH,
    MAX_NAME_LENGTH,
    DialogSession,
    DialogState,
    Lead,
    LeadStatus,
    Topic,
)

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Приводит пользовательский ввод к нижнему регистру без пробелов по краям."""
    return text.strip().lower()


def _contains_any(text: str, keywords: List[str]) -> bool:
    return any(kw in text for kw in keywords)


def _parse_yes_no(text: str) -> Optional[bool]:
    """Грубый разбор ответа да/нет. Возвращает None, если ответ неоднозначен."""
    normalized = _normalize(text)
    if _contains_any(normalized, NEGATIVE_WORDS):
        return False
    if _contains_any(normalized, POSITIVE_WORDS):
        return True
    return None


def _parse_rating(text: str) -> Optional[str]:
    """Разбор оценки в конце диалога: 'up' / 'down' / None (не распознано)."""
    normalized = _normalize(text)
    if "👍" in text or _contains_any(normalized, RATING_POSITIVE_WORDS):
        return "up"
    if "👎" in text or _contains_any(normalized, RATING_NEGATIVE_WORDS):
        return "down"
    return None


def start_dialog(session: DialogSession) -> str:
    """Переводит сессию в рабочее состояние и возвращает приветствие."""
    session.state = DialogState.CHATTING
    return GREETING_TEXT


async def handle_message(
    session: DialogSession,
    client: BaseGigaChatClient,
    user_text: str,
) -> str:
    """Главная точка входа движка диалога — обрабатывает одно сообщение клиента.

    Транспорт (Telegram-обработчик, консольный тест) вызывает эту функцию на
    каждое входящее сообщение и просто отправляет пользователю возвращённый
    текст; вся логика состояний, сбора лида и статистики — здесь.
    """
    if session.state == DialogState.GREETING:
        start_dialog(session)

    normalized = _normalize(user_text)

    if session.state == DialogState.CLOSED:
        return CLOSED_MESSAGE

    if session.state == DialogState.AWAITING_RATING:
        rating = _parse_rating(user_text)
        stats.record_rating(session.chat_id, rating or "неопределено")
        session.state = DialogState.CLOSED
        return RATING_THANKS_PREFIX + CLOSED_MESSAGE

    if _contains_any(normalized, CLOSE_KEYWORDS) or normalized in ("/end",):
        session.state = DialogState.AWAITING_RATING
        return CLOSING_MESSAGE

    if session.state == DialogState.AWAITING_CONSENT:
        return _handle_consent_answer(session, user_text)

    if session.state == DialogState.COLLECTING_NAME:
        name = user_text.strip()
        if not name:
            return NAME_EMPTY_RETRY
        if len(name) > MAX_NAME_LENGTH:
            return NAME_TOO_LONG_RETRY
        session.lead_name = name
        session.state = DialogState.COLLECTING_CONTACT
        return ASK_CONTACT

    if session.state == DialogState.COLLECTING_CONTACT:
        contact = user_text.strip()
        if not contact:
            return CONTACT_EMPTY_RETRY
        if len(contact) > MAX_CONTACT_LENGTH:
            return CONTACT_TOO_LONG_RETRY
        session.lead_contact = contact
        session.state = DialogState.COLLECTING_COMMENT
        return ASK_COMMENT

    if session.state == DialogState.COLLECTING_COMMENT:
        if len(user_text.strip()) > MAX_COMMENT_LENGTH:
            return COMMENT_TOO_LONG_RETRY
        return await _finalize_lead(session, user_text)

    # Обычный вопрос в состоянии CHATTING
    session.user_message_count += 1
    return await _handle_question(session, client, user_text)


def _handle_consent_answer(session: DialogSession, user_text: str) -> str:
    answer = _parse_yes_no(user_text)
    if answer is True:
        session.consent_given = True
        session.state = DialogState.COLLECTING_NAME
        return ASK_NAME
    if answer is False:
        session.consent_given = False
        session.state = DialogState.CHATTING
        return CONSENT_DECLINED
    return CONSENT_UNCLEAR


async def _finalize_lead(session: DialogSession, comment_text: str) -> str:
    comment = None if _contains_any(_normalize(comment_text), SKIP_WORDS) else comment_text.strip()
    session.lead_comment = comment

    lead = Lead(
        name=session.lead_name or "Не указано",
        contact=session.lead_contact or session.chat_id,
        question_topic=(session.last_topic.value if session.last_topic else Topic.OTHER.value),
        status=LeadStatus.NEW,
        comment=comment,
    )
    await crm_stub.submit_lead(lead)
    stats.record_interaction(
        chat_id=session.chat_id,
        topic=lead.question_topic,
        question=comment_text,
        answered_by="lead_qualified",
    )

    session.state = DialogState.CHATTING
    session.lead_name = None
    session.lead_contact = None
    session.lead_comment = None

    return LEAD_SUBMITTED_MESSAGE


async def _handle_question(
    session: DialogSession,
    client: BaseGigaChatClient,
    user_text: str,
) -> str:
    normalized = _normalize(user_text)

    if _contains_any(normalized, GREETING_KEYWORDS) and len(normalized) < 40:
        return GREETING_SMALLTALK_REPLY

    if _contains_any(normalized, THANKS_KEYWORDS) and len(normalized) < 40:
        return THANKS_REPLY

    # Классификация по базе знаний — приоритетнее эвристики "просит менеджера",
    # иначе вопросы вроде "как связаться с поддержкой" (тема SUPPORT) будут
    # перехватываться раньше, чем до них дойдёт поиск по базе знаний.
    topic = find_topic(user_text)
    start = time.monotonic()

    if topic is None:
        if _contains_any(normalized, MANAGER_REQUEST_KEYWORDS):
            return start_lead_collection(session)

        if _contains_any(normalized, SCOPE_KEYWORDS) or "?" in user_text:
            reply = await _escalate_to_manager(session, user_text, topic=None)
            stats.record_interaction(
                chat_id=session.chat_id,
                topic=Topic.OTHER.value,
                question=user_text,
                answered_by="manager",
                response_time_ms=int((time.monotonic() - start) * 1000),
            )
            return reply

        stats.record_interaction(
            chat_id=session.chat_id,
            topic=None,
            question=user_text,
            answered_by="offtopic",
        )
        return OFF_TOPIC_MESSAGE

    return await _answer_known_topic(session, client, topic, user_text, start)


async def _answer_known_topic(
    session: DialogSession,
    client: BaseGigaChatClient,
    topic: Topic,
    log_question: str,
    start: float,
) -> str:
    session.last_topic = topic
    kb_answer = get_answer(topic)
    reply = await _answer_with_context(client, log_question, kb_answer)
    answered_by = "kb_llm"

    if reply is None:
        reply = await _escalate_to_manager(session, log_question, topic=topic)
        answered_by = "manager"

    stats.record_interaction(
        chat_id=session.chat_id,
        topic=topic.value,
        question=log_question,
        answered_by=answered_by,
        response_time_ms=int((time.monotonic() - start) * 1000),
    )

    if answered_by == "kb_llm":
        reply = _maybe_prompt_consent(session, reply, topic)

    return reply


async def handle_faq_selection(
    session: DialogSession,
    client: BaseGigaChatClient,
    topic: Topic,
) -> str:
    """Ответ на выбор темы из FAQ-меню (кнопка в Telegram / пункт в консоли).

    Использует тот же движок, что и обычный вопрос текстом — согласие на
    передачу контакта и статистика собираются одинаково независимо от того,
    выбрал ли клиент тему кнопкой или напечатал вопрос сам.
    """
    if session.state == DialogState.GREETING:
        start_dialog(session)
    if session.state != DialogState.CHATTING:
        return STEP_IN_PROGRESS_RETRY

    session.user_message_count += 1
    entry = KNOWLEDGE_BASE[topic]
    start = time.monotonic()
    return await _answer_known_topic(session, client, topic, f"[FAQ] {entry.title}", start)


def start_lead_collection(session: DialogSession) -> str:
    """Запускает сбор контакта в обход эвристик распознавания намерения —
    по явному действию клиента (кнопка «Оставить заявку» или фраза вроде
    «свяжите с менеджером»). Это уже само по себе явное согласие."""
    if session.state == DialogState.GREETING:
        start_dialog(session)
    if session.state not in (DialogState.CHATTING, DialogState.AWAITING_CONSENT):
        return STEP_IN_PROGRESS_RETRY

    session.consent_given = True
    session.state = DialogState.COLLECTING_NAME
    return ASK_NAME


def answer_product_pitch(session: DialogSession) -> str:
    """Короткий рассказ о продукте по кнопке «О продукте» (не тема FAQ)."""
    if session.state == DialogState.GREETING:
        start_dialog(session)
    if session.state != DialogState.CHATTING:
        return STEP_IN_PROGRESS_RETRY

    stats.record_interaction(
        chat_id=session.chat_id,
        topic=None,
        question="[кнопка] О продукте",
        answered_by="product_pitch",
    )
    return PRODUCT_PITCH


async def _answer_with_context(
    client: BaseGigaChatClient, user_text: str, kb_answer: Optional[str]
) -> Optional[str]:
    """Вызывает GigaChat с контекстом из базы знаний; None — сигнал эскалации."""
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=kb_answer or "")
    try:
        return await client.generate(system_prompt, user_text)
    except GigaChatUnavailableError:
        logger.error("GigaChat недоступен после retry — эскалация на менеджера")
        return None
    except GigaChatError:
        logger.error("Ошибка GigaChat (не retry) — эскалация на менеджера")
        return None


async def _escalate_to_manager(
    session: DialogSession, user_text: str, topic: Optional[Topic]
) -> str:
    lead = Lead(
        name="Не указано",
        contact=session.chat_id,
        question_topic=(topic.value if topic else Topic.OTHER.value),
        status=LeadStatus.NEEDS_MANAGER,
        comment=user_text,
    )
    await crm_stub.submit_lead(lead)
    return FALLBACK_MESSAGE


def _maybe_prompt_consent(session: DialogSession, reply: str, topic: Topic) -> str:
    if session.consent_given is True:
        return reply

    buying_intent = topic in (Topic.PRICE, Topic.DEMO, Topic.PAYMENT)
    threshold_reached = session.user_message_count >= settings.consent_prompt_after_messages

    if session.consent_given is None and (buying_intent or threshold_reached):
        session.state = DialogState.AWAITING_CONSENT
        return reply + CONSENT_PROMPT_SUFFIX

    return reply
