"""
Memory system for Thursday.

Two layers:
  1. Short-term: recent conversation turns stored in SQLite, last N sent in context.
  2. Long-term:  extracted facts stored in a separate table, summarized into prompts.

Extension point: replace the keyword-based long-term extraction with an
embeddings model (e.g. sentence-transformers) for semantic memory retrieval.
Add a vector store (FAISS / Chroma) alongside the SQLite facts table.
"""

import sqlite3
import time
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
    """SQLite-backed short-term + long-term memory."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = str(db_path or DB_FILE)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")  # faster concurrent reads
        self._init_tables()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_tables(self) -> None:
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                role      TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                timestamp REAL   NOT NULL
            );

            CREATE TABLE IF NOT EXISTS long_term_facts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                content    TEXT    NOT NULL UNIQUE,
                created_at REAL   NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chat_ts ON chat_history(timestamp);
            CREATE INDEX IF NOT EXISTS idx_facts_ts ON long_term_facts(created_at);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Short-term memory
    # ------------------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        """Append a message to conversation history."""
        self._conn.execute(
            "INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)",
            (role, content, time.time()),
        )
        self._conn.commit()
        self._maybe_prune()

    def get_recent_messages(self, limit: int = SHORT_TERM_LIMIT) -> list[dict]:
        """Return the last `limit` messages as OpenAI-style dicts."""
        rows = self._conn.execute(
            "SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        # Rows come newest-first; reverse for chronological order.
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def clear_history(self) -> None:
        """Wipe all short-term conversation history."""
        self._conn.execute("DELETE FROM chat_history")
        self._conn.commit()

    def _maybe_prune(self) -> None:
        """Delete oldest messages when table exceeds threshold."""
        count = self._conn.execute(
            "SELECT COUNT(*) FROM chat_history"
        ).fetchone()[0]
        if count > DB_PRUNE_THRESHOLD:
            excess = count - DB_PRUNE_THRESHOLD
            self._conn.execute(
                "DELETE FROM chat_history WHERE id IN "
                "(SELECT id FROM chat_history ORDER BY id ASC LIMIT ?)",
                (excess,),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Long-term memory
    # ------------------------------------------------------------------

    def try_extract_fact(self, user_message: str) -> str | None:
        """
        Check if the user message contains a memorizable fact.
        Returns the extracted fact string, or None.

        Extension point: replace this with an LLM-based extraction call
        or an NER pipeline for richer fact types.
        """
        lower = user_message.lower().strip()
        for prefix in MEMORY_TRIGGER_PREFIXES:
            if lower.startswith(prefix):
                # Store the original-case version, trimmed of the trigger word.
                fact = user_message.strip()
                self._store_fact(fact)
                return fact
        return None

    def _store_fact(self, fact: str) -> None:
        """Insert a fact, ignoring duplicates (UNIQUE constraint)."""
        try:
            self._conn.execute(
                "INSERT INTO long_term_facts (content, created_at) VALUES (?, ?)",
                (fact, time.time()),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            pass  # duplicate, skip silently

    def get_facts(self, limit: int = LONG_TERM_MAX_INJECT) -> list[Fact]:
        """Return the most recent long-term facts."""
        rows = self._conn.execute(
            "SELECT id, content, created_at FROM long_term_facts "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [Fact(id=r[0], content=r[1], created_at=r[2]) for r in rows]

    def get_facts_block(self) -> str | None:
        """
        Build a plain-text summary of stored facts for prompt injection.
        Returns None if no facts exist.
        """
        facts = self.get_facts()
        if not facts:
            return None
        lines = [f"- {f.content}" for f in facts]
        return "Things you know about the user:\n" + "\n".join(lines)

    def delete_fact(self, fact_id: int) -> bool:
        """Remove a specific long-term fact by ID."""
        cur = self._conn.execute(
            "DELETE FROM long_term_facts WHERE id = ?", (fact_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_facts_formatted(self) -> str:
        """Pretty-print all facts for the /memory command."""
        facts = self.get_facts(limit=100)
        if not facts:
            return "No long-term memories stored yet."
        lines = [f"  [{f.id}] {f.content}" for f in facts]
        return "Long-term memories:\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()
