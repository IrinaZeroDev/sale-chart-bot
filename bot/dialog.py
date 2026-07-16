"""Движок диалога — вся бизнес-логика сценария, не зависящая от транспорта.

Используется и Telegram-обработчиками (handlers.py), и консольным
тест-харнессом (console_test.py), поэтому его можно тестировать и
эксплуатировать без Telegram-токена.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from bot import crm_stub, stats
from bot.config import settings
from bot.gigachat_client import BaseGigaChatClient, GigaChatError, GigaChatUnavailableError
from bot.knowledge_base import GREETING_TEXT, KNOWLEDGE_BASE, find_topic, get_answer
from bot.models import DialogSession, DialogState, Lead, LeadStatus, Topic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = (
    "Ты — бот отдела продаж B2B SaaS-компании. Отвечай кратко, по-деловому, "
    "без панибратства, для аудитории, знакомой с техническими терминами "
    "(API, интеграции).\n\n"
    "ПРАВИЛА:\n"
    "- Отвечай ТОЛЬКО на основе блока КОНТЕКСТ ниже. Не придумывай цены, "
    "сроки, гарантии и факты, которых нет в контексте.\n"
    "- Если контекста недостаточно для ответа — прямо скажи об этом, не "
    "гадай.\n"
    "- Не обсуждай темы, не связанные с продуктом и продажами.\n\n"
    "КОНТЕКСТ:\n{context}"
)

FALLBACK_MESSAGE = (
    "Здесь у меня пока нет точных данных, а гадать не хочу, чтобы не ввести "
    "вас в заблуждение — передам вопрос менеджеру, он свяжется с вами "
    f"{settings.manager_sla_text}."
)

OFF_TOPIC_MESSAGE = (
    "Эту тему, к сожалению, не подскажу — помогаю с вопросами о продукте и "
    "подписке. Может, расскажу про тарифы, интеграции или условия?"
)

CLOSING_MESSAGE = (
    "Спасибо, что заглянули! Оцените, пожалуйста, как всё прошло: 👍 или 👎."
)

CLOSED_MESSAGE = (
    "На этом всё! Если появятся вопросы — просто напишите /start, и продолжим."
)

GREETING_KEYWORDS = ["привет", "здравствуй", "добрый день", "доброе утро", "добрый вечер"]
THANKS_KEYWORDS = ["спасибо", "благодар"]
CLOSE_KEYWORDS = ["пока", "до свидан", "заверши", "законч", "хватит", "стоп"]
MANAGER_REQUEST_KEYWORDS = ["связат", "менеджер", "перезвон", "созвон"]
SCOPE_KEYWORDS = [
    "продукт", "сервис", "компани", "функци", "систем", "купить", "подключ",
    "стоимост", "оплат", "техподдержк", "помощ", "менеджер", "заказ", "услуг",
    "api", "crm", "тариф", "подписк", "демо", "интеграц", "счет", "счёт",
    "договор", "безопасн", "данн", "конфиденциальн", "отчет", "отчёт",
    "аналитик", "воронк", "лид", "клиент", "пользовател", "цена", "цены",
]
NEGATIVE_WORDS = ["нет", "не над", "не хочу", "не буду"]
POSITIVE_WORDS = ["да", "хорошо", "давай", "конечно", "ок", "окей", "согласен", "согласна"]
SKIP_WORDS = ["нет", "пропустить", "не буду", "без комментария", "-"]


def _normalize(text: str) -> str:
    return text.strip().lower()


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(kw in text for kw in keywords)


def _parse_yes_no(text: str) -> Optional[bool]:
    normalized = _normalize(text)
    if _contains_any(normalized, NEGATIVE_WORDS):
        return False
    if _contains_any(normalized, POSITIVE_WORDS):
        return True
    return None


def _parse_rating(text: str) -> Optional[str]:
    normalized = _normalize(text)
    if "👍" in text or _contains_any(normalized, ["хорош", "понрав", "отлично", "супер"]):
        return "up"
    if "👎" in text or _contains_any(normalized, ["плохо", "не понрав", "ужасно"]):
        return "down"
    return None


def start_dialog(session: DialogSession) -> str:
    session.state = DialogState.CHATTING
    return GREETING_TEXT


async def handle_message(
    session: DialogSession,
    client: BaseGigaChatClient,
    user_text: str,
) -> str:
    if session.state == DialogState.GREETING:
        start_dialog(session)

    normalized = _normalize(user_text)

    if session.state == DialogState.CLOSED:
        return CLOSED_MESSAGE

    if session.state == DialogState.AWAITING_RATING:
        rating = _parse_rating(user_text)
        stats.record_rating(session.chat_id, rating or "неопределено")
        session.state = DialogState.CLOSED
        return "Спасибо за обратную связь! " + CLOSED_MESSAGE

    if _contains_any(normalized, CLOSE_KEYWORDS) or normalized in ("/end",):
        session.state = DialogState.AWAITING_RATING
        return CLOSING_MESSAGE

    if session.state == DialogState.AWAITING_CONSENT:
        return _handle_consent_answer(session, user_text)

    if session.state == DialogState.COLLECTING_NAME:
        session.lead_name = user_text.strip()
        session.state = DialogState.COLLECTING_CONTACT
        return "Спасибо! Укажите, пожалуйста, телефон или e-mail для связи."

    if session.state == DialogState.COLLECTING_CONTACT:
        session.lead_contact = user_text.strip()
        session.state = DialogState.COLLECTING_COMMENT
        return "Отлично, спасибо! И коротко — что вас интересует? (или напишите «нет», чтобы пропустить)"

    if session.state == DialogState.COLLECTING_COMMENT:
        return await _finalize_lead(session, user_text)

    # Обычный вопрос в состоянии CHATTING
    session.user_message_count += 1
    return await _handle_question(session, client, user_text)


def _handle_consent_answer(session: DialogSession, user_text: str) -> str:
    answer = _parse_yes_no(user_text)
    if answer is True:
        session.consent_given = True
        session.state = DialogState.COLLECTING_NAME
        return "Отлично! Как я могу к вам обращаться?"
    if answer is False:
        session.consent_given = False
        session.state = DialogState.CHATTING
        return "Хорошо, контакт передавать не буду — просто спрашивайте, если будут ещё вопросы!"
    return "Уточните, пожалуйста: да или нет — передать ваш контакт менеджеру?"


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

    return (
        "Готово! Заявка передана менеджеру — он свяжется с вами "
        f"{settings.manager_sla_text}. Если будут ещё вопросы, с радостью отвечу!"
    )


async def _handle_question(
    session: DialogSession,
    client: BaseGigaChatClient,
    user_text: str,
) -> str:
    normalized = _normalize(user_text)

    if _contains_any(normalized, GREETING_KEYWORDS) and len(normalized) < 40:
        return "Здравствуйте! Чем могу помочь — тарифы, подписка, интеграции?"

    if _contains_any(normalized, THANKS_KEYWORDS) and len(normalized) < 40:
        return "Пожалуйста! Могу ещё чем-то помочь?"

    # Классификация по базе знаний — приоритетнее эвристики "просит менеджера",
    # иначе вопросы вроде "как связаться с поддержкой" (тема SUPPORT) будут
    # перехватываться раньше, чем до них дойдёт поиск по базе знаний.
    topic = find_topic(user_text)
    start = time.monotonic()

    if topic is None:
        if _contains_any(normalized, MANAGER_REQUEST_KEYWORDS):
            session.consent_given = True
            session.state = DialogState.COLLECTING_NAME
            return "Хорошо! Как я могу к вам обращаться?"

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
        return "Давайте сначала закончим предыдущий шаг, а после — выберем тему из FAQ."

    session.user_message_count += 1
    entry = KNOWLEDGE_BASE[topic]
    start = time.monotonic()
    return await _answer_known_topic(session, client, topic, f"[FAQ] {entry.title}", start)


async def _answer_with_context(
    client: BaseGigaChatClient, user_text: str, kb_answer: Optional[str]
) -> Optional[str]:
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
        return reply + "\n\nКстати, хотите, чтобы с вами связался менеджер? Могу передать ему ваш контакт."

    return reply
