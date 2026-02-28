"""
Memory system for Thursday Web.

Three layers:
  1. Conversations: named chat sessions, switchable from sidebar.
  2. Short-term: recent turns per conversation, last N sent in context.
  3. Long-term:  extracted facts, injected into prompts across all conversations.

Extension point: add an embeddings index (FAISS / Chroma) alongside
the SQLite facts table for semantic memory retrieval.
"""

import sqlite3
import time
import uuid
from dataclasses import dataclass

from config import (
    DB_FILE,
    DB_PRUNE_THRESHOLD,
    LONG_TERM_MAX_INJECT,
    MEMORY_TRIGGER_PREFIXES,
    SHORT_TERM_LIMIT,
)


@dataclass(slots=True)
class Fact:
    id: int
    content: str
    created_at: float


class MemoryStore:
    """SQLite-backed conversation + short-term + long-term memory."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = str(db_path or DB_FILE)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT 'New Chat',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT    NOT NULL,
                role            TEXT    NOT NULL,
                content         TEXT    NOT NULL,
                timestamp       REAL   NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );
            CREATE TABLE IF NOT EXISTS long_term_facts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                content    TEXT    NOT NULL UNIQUE,
                created_at REAL   NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chat_conv ON chat_history(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_chat_ts   ON chat_history(timestamp);
            CREATE INDEX IF NOT EXISTS idx_facts_ts  ON long_term_facts(created_at);
            CREATE INDEX IF NOT EXISTS idx_conv_upd  ON conversations(updated_at);
        """)
        self._conn.commit()

    # ---- Conversations ----

    def create_conversation(self, title: str = "New Chat") -> dict:
        conv_id = uuid.uuid4().hex[:12]
        now = time.time()
        self._conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now),
        )
        self._conn.commit()
        return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}

    def list_conversations(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        return [
            {"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]}
            for r in rows
        ]

    def rename_conversation(self, conv_id: str, title: str) -> bool:
        cur = self._conn.execute(
            "UPDATE conversations SET title = ? WHERE id = ?", (title, conv_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete_conversation(self, conv_id: str) -> bool:
        self._conn.execute("DELETE FROM chat_history WHERE conversation_id = ?", (conv_id,))
        cur = self._conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def _touch_conversation(self, conv_id: str) -> None:
        self._conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (time.time(), conv_id),
        )

    def auto_title_conversation(self, conv_id: str, first_message: str) -> str:
        """Generate a short title from the first user message."""
        title = first_message[:50].strip()
        if len(first_message) > 50:
            title += "..."
        self.rename_conversation(conv_id, title)
        return title

    # ---- Short-term (per-conversation) ----

    def add_message(self, role: str, content: str, conversation_id: str | None = None) -> None:
        conv_id = conversation_id or "__default__"
        self._conn.execute(
            "INSERT INTO chat_history (conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (conv_id, role, content, time.time()),
        )
        self._touch_conversation(conv_id)
        self._conn.commit()
        self._maybe_prune(conv_id)

    def get_recent_messages(
        self, limit: int = SHORT_TERM_LIMIT, conversation_id: str | None = None
    ) -> list[dict]:
        conv_id = conversation_id or "__default__"
        rows = self._conn.execute(
            "SELECT role, content FROM chat_history WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (conv_id, limit),
        ).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def get_conversation_messages(self, conversation_id: str) -> list[dict]:
        """Return ALL messages for a conversation (for UI reload)."""
        rows = self._conn.execute(
            "SELECT role, content FROM chat_history WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
        return [{"role": r, "content": c} for r, c in rows]

    def get_conversation_message_count(self, conversation_id: str) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM chat_history WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()[0]

    def clear_history(self, conversation_id: str | None = None) -> None:
        if conversation_id:
            self._conn.execute("DELETE FROM chat_history WHERE conversation_id = ?", (conversation_id,))
        else:
            self._conn.execute("DELETE FROM chat_history")
        self._conn.commit()

    def _maybe_prune(self, conv_id: str) -> None:
        count = self._conn.execute(
            "SELECT COUNT(*) FROM chat_history WHERE conversation_id = ?", (conv_id,)
        ).fetchone()[0]
        if count > DB_PRUNE_THRESHOLD:
            excess = count - DB_PRUNE_THRESHOLD
            self._conn.execute(
                "DELETE FROM chat_history WHERE id IN "
                "(SELECT id FROM chat_history WHERE conversation_id = ? ORDER BY id ASC LIMIT ?)",
                (conv_id, excess),
            )
            self._conn.commit()

    # ---- Long-term ----

    def try_extract_fact(self, user_message: str) -> str | None:
        """
        Check if user message contains a memorizable fact.
        Extension point: replace with LLM-based extraction or NER.
        """
        lower = user_message.lower().strip()
        for prefix in MEMORY_TRIGGER_PREFIXES:
            if lower.startswith(prefix):
                fact = user_message.strip()
                self._store_fact(fact)
                return fact
        return None

    def _store_fact(self, fact: str) -> None:
        try:
            self._conn.execute(
                "INSERT INTO long_term_facts (content, created_at) VALUES (?, ?)",
                (fact, time.time()),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            pass

    def get_facts(self, limit: int = LONG_TERM_MAX_INJECT) -> list[Fact]:
        rows = self._conn.execute(
            "SELECT id, content, created_at FROM long_term_facts "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [Fact(id=r[0], content=r[1], created_at=r[2]) for r in rows]

    def get_facts_block(self) -> str | None:
        facts = self.get_facts()
        if not facts:
            return None
        lines = [f"- {f.content}" for f in facts]
        return "Things you know about the user:\n" + "\n".join(lines)

    def delete_fact(self, fact_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM long_term_facts WHERE id = ?", (fact_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def list_facts(self) -> list[dict]:
        facts = self.get_facts(limit=100)
        return [{"id": f.id, "content": f.content} for f in facts]

    def close(self) -> None:
        self._conn.close()
