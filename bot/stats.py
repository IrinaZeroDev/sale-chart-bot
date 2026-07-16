"""Сбор и хранение статистики взаимодействий с клиентами в SQLite."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _connect() -> sqlite3.Connection:
    from bot.config import settings

    Path(settings.stats_db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(settings.stats_db_path)


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                topic TEXT,
                question TEXT,
                answered_by TEXT,
                response_time_ms INTEGER,
                rating TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def record_interaction(
    chat_id: str,
    topic: Optional[str],
    question: str,
    answered_by: str,
    response_time_ms: Optional[int] = None,
    rating: Optional[str] = None,
) -> None:
    """answered_by: 'kb_llm' | 'manager' | 'offtopic' | 'smalltalk'."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO interactions
                (chat_id, topic, question, answered_by, response_time_ms, rating, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                topic,
                question,
                answered_by,
                response_time_ms,
                rating,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def record_rating(chat_id: str, rating: str) -> None:
    """Проставляет оценку последнему взаимодействию в диалоге."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM interactions WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        if row is None:
            return
        conn.execute("UPDATE interactions SET rating = ? WHERE id = ?", (rating, row[0]))


def get_all_interactions() -> list[dict]:
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM interactions ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]
