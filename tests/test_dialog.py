import pytest

from bot import dialog
from bot.config import settings
from bot.gigachat_client import MockGigaChatClient
from bot.models import DialogSession, DialogState


@pytest.fixture(autouse=True)
def isolated_dbs(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "stats_db_path", str(tmp_path / "stats.sqlite3"))
    monkeypatch.setattr(settings, "leads_db_path", str(tmp_path / "leads.sqlite3"))
    monkeypatch.setattr(settings, "crm_webhook_url", "")
    yield


@pytest.fixture
def client():
    return MockGigaChatClient()


def _session() -> DialogSession:
    return DialogSession(chat_id="test-chat")


def test_start_dialog_returns_greeting():
    session = _session()
    greeting = dialog.start_dialog(session)
    assert session.state == DialogState.CHATTING
    assert "здравствуйте" in greeting.lower()
    assert "тариф" in greeting.lower()


@pytest.mark.asyncio
async def test_known_topic_answers_from_kb(client):
    session = _session()
    dialog.start_dialog(session)
    reply = await dialog.handle_message(session, client, "Сколько стоит подписка?")
    assert "basic" in reply.lower() or "тариф" in reply.lower()


@pytest.mark.asyncio
async def test_offtopic_question_gets_scope_redirect(client):
    session = _session()
    dialog.start_dialog(session)
    reply = await dialog.handle_message(session, client, "какая завтра погода")
    assert reply == dialog.OFF_TOPIC_MESSAGE


@pytest.mark.asyncio
async def test_unmatched_but_relevant_question_escalates_to_manager(client):
    session = _session()
    dialog.start_dialog(session)
    reply = await dialog.handle_message(
        session, client, "Поддерживаете ли вы работу с системой электронного документооборота?"
    )
    assert "менеджер" in reply.lower()


@pytest.mark.asyncio
async def test_explicit_manager_request_skips_consent_question(client):
    session = _session()
    dialog.start_dialog(session)
    reply = await dialog.handle_message(session, client, "Свяжите меня с менеджером")
    assert session.state == DialogState.COLLECTING_NAME
    assert "обращаться" in reply.lower()


@pytest.mark.asyncio
async def test_full_lead_collection_flow_requires_consent(client):
    session = _session()
    dialog.start_dialog(session)

    # Явный покупательский интерес -> бот должен спросить согласие
    reply = await dialog.handle_message(session, client, "Сколько стоит подписка?")
    assert session.state == DialogState.AWAITING_CONSENT
    assert "хотите" in reply.lower()

    reply = await dialog.handle_message(session, client, "да")
    assert session.state == DialogState.COLLECTING_NAME

    reply = await dialog.handle_message(session, client, "Иван Иванов")
    assert session.state == DialogState.COLLECTING_CONTACT

    reply = await dialog.handle_message(session, client, "ivan@example.com")
    assert session.state == DialogState.COLLECTING_COMMENT

    reply = await dialog.handle_message(session, client, "интересует тариф Pro")
    assert session.state == DialogState.CHATTING
    assert "менеджер" in reply.lower()

    from bot import crm_stub

    leads = crm_stub.get_all_leads()
    assert len(leads) == 1
    assert leads[0]["name"] == "Иван Иванов"
    assert leads[0]["contact"] == "ivan@example.com"


@pytest.mark.asyncio
async def test_declining_consent_does_not_collect_contact(client):
    session = _session()
    dialog.start_dialog(session)
    await dialog.handle_message(session, client, "Сколько стоит подписка?")
    assert session.state == DialogState.AWAITING_CONSENT

    reply = await dialog.handle_message(session, client, "нет")
    assert session.state == DialogState.CHATTING
    assert session.lead_name is None

    from bot import crm_stub

    assert crm_stub.get_all_leads() == []


@pytest.mark.asyncio
async def test_close_and_rating_flow(client):
    session = _session()
    dialog.start_dialog(session)
    reply = await dialog.handle_message(session, client, "спасибо, всё, пока")
    assert session.state == DialogState.AWAITING_RATING

    reply = await dialog.handle_message(session, client, "👍")
    assert session.state == DialogState.CLOSED
    assert "спасибо" in reply.lower()

    reply = await dialog.handle_message(session, client, "ещё вопрос")
    assert reply == dialog.CLOSED_MESSAGE
