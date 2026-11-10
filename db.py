"""Хранение заявок в SQLite (встроен в Python, ставить ничего не нужно)."""
import sqlite3
from datetime import datetime

DB_PATH = "leads.db"


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                username    TEXT,
                name        TEXT NOT NULL,
                phone       TEXT NOT NULL,
                service     TEXT NOT NULL,
                comment     TEXT,
                created_at  TEXT NOT NULL
            )
            """
        )


def add_lead(user_id: int, username: str | None, name: str, phone: str,
             service: str, comment: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO leads (user_id, username, name, phone, service, comment, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, name, phone, service, comment,
             datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        return cur.lastrowid


def last_leads(limit: int = 10) -> list[tuple]:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT id, name, phone, service, created_at FROM leads "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
