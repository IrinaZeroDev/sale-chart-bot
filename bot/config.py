"""Загрузка конфигурации из .env через Pydantic Settings.

Ключи (GigaChat/ProxyAPI, Telegram Bot Token) хранятся только в переменных
окружения и никогда не логируются и не передаются в промпт нейросети.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram ---
    telegram_bot_token: str = ""

    # --- GigaChat через ProxyAPI ---
    # GIGACHAT_CREDENTIALS зарезервирован на случай прямой интеграции со
    # Sber (OAuth client_id:client_secret) без ProxyAPI — сейчас не используется.
    gigachat_credentials: str = ""
    proxyapi_key: str = ""
    # ЗАГЛУШКА — уточнить точный путь эндпоинта в актуальной документации
    # ProxyAPI (https://proxyapi.ru) перед боевым запуском.
    proxyapi_base_url: str = "https://api.proxyapi.ru/gigachat/v1/chat/completions"
    gigachat_model: str = "GigaChat"

    # --- Внешняя система (CRM) ---
    # Если не задан — заявки только сохраняются локально (SQLite-заглушка).
    crm_webhook_url: str = ""

    # --- Сетевые настройки / устойчивость к сбоям ---
    request_timeout_seconds: float = 18.0
    retry_attempts: int = 3

    # --- Хранилища ---
    stats_db_path: str = "data/stats.sqlite3"
    leads_db_path: str = "data/leads.sqlite3"

    # ЗАГЛУШКА — заменить на реальные данные заказчика (SLA ответа менеджера)
    manager_sla_text: str = "в течение одного рабочего дня"

    # После скольких сообщений от пользователя явно предлагать связь с менеджером
    consent_prompt_after_messages: int = 4

    # Антиспам: минимальный интервал между обработанными сообщениями от одного chat_id
    rate_limit_seconds: float = 1.0

    @property
    def gigachat_mock_mode(self) -> bool:
        """Без ключа ProxyAPI работаем в офлайн-режиме без реальных вызовов сети."""
        return not self.proxyapi_key


settings = Settings()
