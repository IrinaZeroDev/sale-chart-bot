from unittest.mock import AsyncMock, patch

import httpx
import pytest

from bot import crm_stub
from bot.config import settings
from bot.models import Lead


@pytest.fixture(autouse=True)
def isolated_leads_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "leads_db_path", str(tmp_path / "leads.sqlite3"))
    monkeypatch.setattr(settings, "crm_webhook_url", "")
    yield


@pytest.mark.asyncio
async def test_submit_lead_saves_locally():
    lead = Lead(name="Иван", contact="+79990000000", question_topic="цена")
    result = await crm_stub.submit_lead(lead)
    assert result.lead_id == lead.lead_id

    rows = crm_stub.get_all_leads()
    assert len(rows) == 1
    assert rows[0]["name"] == "Иван"
    assert rows[0]["status"] == "new"


@pytest.mark.asyncio
async def test_submit_lead_posts_to_webhook_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "crm_webhook_url", "https://example.test/leads")
    ok_response = httpx.Response(
        200, json={"ok": True}, request=httpx.Request("POST", "https://example.test/leads")
    )
    mock_post = AsyncMock(return_value=ok_response)
    with patch.object(httpx.AsyncClient, "post", mock_post):
        lead = Lead(name="Пётр", contact="p@example.com", question_topic="демо")
        await crm_stub.submit_lead(lead)

    mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_submit_lead_survives_webhook_failure(monkeypatch):
    monkeypatch.setattr(settings, "crm_webhook_url", "https://example.test/leads")
    mock_post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    with patch.object(httpx.AsyncClient, "post", mock_post):
        lead = Lead(name="Анна", contact="a@example.com", question_topic="оплата")
        result = await crm_stub.submit_lead(lead)

    # Локальная запись — гарантия, что заявка не потеряется даже при сбое вебхука
    assert result.lead_id == lead.lead_id
    rows = crm_stub.get_all_leads()
    assert any(r["lead_id"] == lead.lead_id for r in rows)
