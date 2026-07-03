"""
SQLite-based chat history storage.
"""

import json
import sqlite3
import uuid
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ChatDB:
    """Persistent chat storage using SQLite."""

    def __init__(self, db_path: str = "data/chats.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'Новый чат',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT,
                    tool_calls TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id);
            """)
        logger.info(f"Chat DB initialized at {self.db_path}")

    def create_chat(self, title: str = "Новый чат", chat_id: Optional[str] = None) -> Dict[str, Any]:
        cid = chat_id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (cid, title, now, now),
            )
        return {"id": cid, "title": title, "created_at": now, "updated_at": now}

    def list_chats(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at FROM chats ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_chat(self, chat_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        return dict(row) if row else None

    def delete_chat(self, chat_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        return cur.rowcount > 0

    def rename_chat(self, chat_id: str, title: str) -> bool:
        now = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            cur = conn.execute(
                "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
                (title, now, chat_id),
            )
        return cur.rowcount > 0

    def save_message(
        self,
        chat_id: str,
        role: str,
        content: Optional[str],
        tool_calls: Optional[Any] = None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        tc_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
        with self._get_conn() as conn:
            conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
            cur = conn.execute(
                "INSERT INTO messages (chat_id, role, content, tool_calls, created_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, role, content, tc_json, now),
            )
        return cur.lastrowid

    def get_messages(self, chat_id: str) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content, tool_calls, created_at FROM messages WHERE chat_id = ? ORDER BY id",
                (chat_id,),
            ).fetchall()
        result = []
        for r in rows:
            msg = {"role": r["role"], "content": r["content"]}
            if r["tool_calls"]:
                msg["tool_calls"] = json.loads(r["tool_calls"])
            result.append(msg)
        return result

    def auto_title(self, chat_id: str, user_message: str):
        """Set title from first user message (first 60 chars)."""
        title = user_message.strip()[:60]
        if len(user_message.strip()) > 60:
            title += "..."
        self.rename_chat(chat_id, title)
