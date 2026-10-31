"""SQLite-сховище повідомлень з груп."""

import sqlite3
import time
from dataclasses import dataclass


@dataclass
class StoredMessage:
    chat_id: int
    chat_title: str
    message_id: int
    user_id: int | None
    username: str | None
    full_name: str
    text: str
    date: int  # unix timestamp


class Storage:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                chat_id     INTEGER NOT NULL,
                chat_title  TEXT    NOT NULL,
                message_id  INTEGER NOT NULL,
                user_id     INTEGER,
                username    TEXT,
                full_name   TEXT    NOT NULL,
                text        TEXT    NOT NULL,
                date        INTEGER NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_date ON messages (chat_id, date)")
        self.conn.commit()

    def save(self, m: StoredMessage) -> None:
        # INSERT OR REPLACE: відредаговане повідомлення перезаписує стару версію
        self.conn.execute(
            "INSERT OR REPLACE INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (m.chat_id, m.chat_title, m.message_id, m.user_id, m.username, m.full_name, m.text, m.date),
        )
        self.conn.commit()

    def chats(self) -> list[tuple[int, str, int]]:
        """Список (chat_id, назва, кількість повідомлень), найактивніші першими."""
        rows = self.conn.execute(
            """
            SELECT chat_id,
                   (SELECT chat_title FROM messages m2 WHERE m2.chat_id = m.chat_id
                    ORDER BY date DESC LIMIT 1),
                   COUNT(*)
            FROM messages m
            GROUP BY chat_id
            ORDER BY COUNT(*) DESC
            """
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    def messages(self, chat_id: int, hours: float | None = None) -> list[StoredMessage]:
        """Повідомлення чату за останні `hours` годин (або всі), від старих до нових."""
        since = int(time.time() - hours * 3600) if hours else 0
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? AND date >= ? ORDER BY date, message_id",
            (chat_id, since),
        ).fetchall()
        return [StoredMessage(*r) for r in rows]
