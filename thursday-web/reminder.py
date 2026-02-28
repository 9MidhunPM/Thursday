"""
Reminder system for Thursday Web.

Components:
  - ReminderStore: SQLite-backed reminder storage
  - parse_time_expression(): natural-language time parsing
  - try_parse_user_reminder(): server-side detection of reminder intent
  - Discord webhook notifications (set + fire)

Usage flow:
  1. User sends a message like "remind me in 30s to take a break"
  2. Server detects reminder intent from user message (try_parse_user_reminder)
  3. Time + message are parsed, reminder stored in DB
  4. Discord webhook notifies that reminder is set
  5. Background loop checks every 10s for due reminders, fires them
  6. AI is told a reminder was set so it can confirm naturally
"""

import re
import sqlite3
import time
import math
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

import requests

from config import DISCORD_WEBHOOK_URL, DISCORD_USER_ID


# ------------------------------------------------------------------
# Data model
# ------------------------------------------------------------------

@dataclass(slots=True)
class Reminder:
    id: int
    message: str
    trigger_at: float      # unix timestamp
    created_at: float
    fired: bool
    conversation_id: str | None


# ------------------------------------------------------------------
# Reminder store (SQLite)
# ------------------------------------------------------------------

class ReminderStore:
    """SQLite-backed reminder storage — shares DB file with MemoryStore."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_table()

    def _init_table(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS reminders (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                message         TEXT    NOT NULL,
                trigger_at      REAL    NOT NULL,
                created_at      REAL    NOT NULL,
                fired           INTEGER NOT NULL DEFAULT 0,
                conversation_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_rem_trigger ON reminders(trigger_at);
            CREATE INDEX IF NOT EXISTS idx_rem_fired   ON reminders(fired);
        """)
        self._conn.commit()

    def add_reminder(
        self, message: str, trigger_at: float, conversation_id: str | None = None
    ) -> Reminder:
        now = time.time()
        cur = self._conn.execute(
            "INSERT INTO reminders (message, trigger_at, created_at, fired, conversation_id) "
            "VALUES (?, ?, ?, 0, ?)",
            (message, trigger_at, now, conversation_id),
        )
        self._conn.commit()
        return Reminder(
            id=cur.lastrowid,
            message=message,
            trigger_at=trigger_at,
            created_at=now,
            fired=False,
            conversation_id=conversation_id,
        )

    def get_due_reminders(self) -> list[Reminder]:
        now = time.time()
        rows = self._conn.execute(
            "SELECT id, message, trigger_at, created_at, fired, conversation_id "
            "FROM reminders WHERE trigger_at <= ? AND fired = 0",
            (now,),
        ).fetchall()
        return [
            Reminder(id=r[0], message=r[1], trigger_at=r[2],
                     created_at=r[3], fired=bool(r[4]), conversation_id=r[5])
            for r in rows
        ]

    def mark_fired(self, reminder_id: int) -> None:
        self._conn.execute(
            "UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,)
        )
        self._conn.commit()

    def list_active(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, message, trigger_at, created_at, conversation_id "
            "FROM reminders WHERE fired = 0 ORDER BY trigger_at ASC"
        ).fetchall()
        return [
            {
                "id": r[0],
                "message": r[1],
                "trigger_at": r[2],
                "created_at": r[3],
                "conversation_id": r[4],
            }
            for r in rows
        ]

    def list_all(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, message, trigger_at, created_at, fired, conversation_id "
            "FROM reminders ORDER BY trigger_at DESC LIMIT 50"
        ).fetchall()
        return [
            {
                "id": r[0],
                "message": r[1],
                "trigger_at": r[2],
                "created_at": r[3],
                "fired": bool(r[4]),
                "conversation_id": r[5],
            }
            for r in rows
        ]

    def delete_reminder(self, reminder_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM reminders WHERE id = ?", (reminder_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()


# ------------------------------------------------------------------
# Time expression parser
# ------------------------------------------------------------------

def parse_time_expression(expr: str) -> float | None:
    """Parse a natural time expression into a unix timestamp.

    Supports:
      - "in 30s", "in 5 seconds"
      - "in 2m", "in 10 minutes", "in 2 mins"
      - "in 1h", "in 3 hours"
      - "in 2d", "in 3 days"
      - "in 1 hour 30 minutes", "in 1h30m"
      - "tomorrow 5 PM", "tomorrow at 17:00"
      - "9:50 PM", "21:50", "3 PM"
      - "today at 3 PM"
    Returns None if parsing fails.
    """
    expr = expr.strip().lower()
    now = datetime.now()

    # --- Compound relative: "in 1 hour 30 minutes", "in 1h 30m", "in 1 hour and 30 minutes" ---
    compound = re.match(
        r'in\s+'
        r'(?:(\d+)\s*(?:hours?|hrs?|h)\s*(?:and\s*)?)?'
        r'(?:(\d+)\s*(?:minutes?|mins?|m)\s*(?:and\s*)?)?'
        r'(?:(\d+)\s*(?:seconds?|secs?|s))?',
        expr,
    )
    if compound and any(compound.group(i) for i in (1, 2, 3)):
        hours = int(compound.group(1) or 0)
        minutes = int(compound.group(2) or 0)
        seconds = int(compound.group(3) or 0)
        if hours or minutes or seconds:
            delta = timedelta(hours=hours, minutes=minutes, seconds=seconds)
            return (now + delta).timestamp()

    # --- "tomorrow [at] HH:MM [AM/PM]" or "tomorrow [at] H [AM/PM]" ---
    m = re.match(
        r'tomorrow\s+(?:at\s+)?(\d{1,2})(?:[: ](\d{2}))?\s*(am|pm)?', expr
    )
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        ampm = m.group(3)
        if ampm == 'pm' and hour != 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
        target = (now + timedelta(days=1)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        return target.timestamp()

    # --- "today [at] HH:MM [AM/PM]" ---
    m = re.match(
        r'today\s+(?:at\s+)?(\d{1,2})(?:[: ](\d{2}))?\s*(am|pm)?', expr
    )
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        ampm = m.group(3)
        if ampm == 'pm' and hour != 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target.timestamp()

    # --- Bare time: "9:50 PM", "21:50", "3 PM", "3:00 pm", "7 35 PM" ---
    m = re.match(r'^(\d{1,2})(?:[: ](\d{2}))?\s*(am|pm)?$', expr)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        ampm = m.group(3)
        if ampm == 'pm' and hour != 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target.timestamp()

    return None


# ------------------------------------------------------------------
# Reminder tag parser (extract from AI response)
# ------------------------------------------------------------------

REMIND_TAG_RE = re.compile(
    r'\[REMIND:\s*(.+?)\s*\|\s*(.+?)\s*\]', re.IGNORECASE
)


def extract_reminder_tags(text: str) -> list[tuple[str, str, str]]:
    """Extract all [REMIND: time_expr | message] tags from text.

    Returns list of (full_match, time_expression, reminder_message).
    """
    results = []
    for m in REMIND_TAG_RE.finditer(text):
        results.append((m.group(0), m.group(1).strip(), m.group(2).strip()))
    return results


def strip_reminder_tags(text: str) -> str:
    """Remove [REMIND: ...] tags from text."""
    return REMIND_TAG_RE.sub('', text).strip()


# ------------------------------------------------------------------
# Discord webhook
# ------------------------------------------------------------------

def send_discord_message(content: str) -> bool:
    """Send a message via Discord webhook. Returns True on success."""
    if not DISCORD_WEBHOOK_URL:
        print("[Reminder] No Discord webhook URL configured, skipping.")
        return False
    try:
        r = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": content, "username": "Thursday AI"},
            timeout=10,
        )
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"[Reminder] Discord webhook error: {e}")
        return False


def send_reminder_set_notification(message: str, trigger_at: float) -> bool:
    """Notify via Discord that a reminder has been set."""
    ts = int(trigger_at)
    content = (
        f"⏰ **Reminder Set!**\n"
        f"📝 {message}\n"
        f"🕐 Scheduled for: <t:{ts}:F> (<t:{ts}:R>)"
    )
    return send_discord_message(content)


def send_reminder_fire_notification(message: str) -> bool:
    """Notify via Discord that a reminder is due — pings the user."""
    content = (
        f"🔔 <@{DISCORD_USER_ID}> **Time's up!**\n"
        f"📝 {message}"
    )
    return send_discord_message(content)


# ------------------------------------------------------------------
# Helper: current time string for system prompt
# ------------------------------------------------------------------

def get_current_time_string() -> str:
    """Return a human-readable current date/time string for the AI."""
    now = datetime.now()
    return now.strftime("%A, %B %d, %Y at %I:%M %p")


# ------------------------------------------------------------------
# Server-side reminder detection from user message
# ------------------------------------------------------------------

# Patterns that indicate the user wants a reminder.
# Each pattern captures two groups:  (time_expression, reminder_message)
# We try multiple patterns in order.

_TIME_UNIT = r'(?:s|sec|secs|seconds?|m|min|mins|minutes?|h|hr|hrs|hours?|d|days?)'
_REL_TIME = (
    r'in\s+\d+\s*' + _TIME_UNIT +
    r'(?:\s*(?:and\s*)?\d+\s*' + _TIME_UNIT + r')*'
)
_ABS_TIME = r'\d{1,2}(?:[: ]\d{2})?\s*(?:am|pm)'

_REMINDER_PATTERNS = [
    # "remind me in 30s to take a break"
    re.compile(
        r'remind\s+me\s+(' + _REL_TIME + r')\s+(?:to|that|about)\s+(.+)',
        re.IGNORECASE,
    ),
    # "remind me to take a break in 30 minutes"
    re.compile(
        r'remind\s+me\s+(?:to|that|about)\s+(.+?)\s+(' + _REL_TIME + r')',
        re.IGNORECASE,
    ),
    # "remind me at 7 35 PM to take a break"  (time first)
    re.compile(
        r'remind\s+me\s+((?:at\s+)?' + _ABS_TIME + r')\s+(?:to|that|about)\s+(.+)',
        re.IGNORECASE,
    ),
    # "remind me to take a break at 7 35 PM"  (time last)
    re.compile(
        r'remind\s+me\s+(?:to|that|about)\s+(.+?)\s+((?:at\s+)?' + _ABS_TIME + r')',
        re.IGNORECASE,
    ),
    # "remind me tomorrow at 5 PM to do something"
    re.compile(
        r'remind\s+me\s+(tomorrow\s+(?:at\s+)?' + _ABS_TIME + r'?)\s+(?:to|that|about)\s+(.+)',
        re.IGNORECASE,
    ),
    # "remind me to do something tomorrow at 5 PM"
    re.compile(
        r'remind\s+me\s+(?:to|that|about)\s+(.+?)\s+(tomorrow\s+(?:at\s+)?' + _ABS_TIME + r'?)',
        re.IGNORECASE,
    ),
    # "remind me today at 3 PM to something"
    re.compile(
        r'remind\s+me\s+(today\s+(?:at\s+)?' + _ABS_TIME + r'?)\s+(?:to|that|about)\s+(.+)',
        re.IGNORECASE,
    ),
    # "remind me to something today at 3 PM"
    re.compile(
        r'remind\s+me\s+(?:to|that|about)\s+(.+?)\s+(today\s+(?:at\s+)?' + _ABS_TIME + r'?)',
        re.IGNORECASE,
    ),
    # Simplified fallback: "remind me in <time> <anything>"
    re.compile(
        r'remind\s+me\s+(' + _REL_TIME + r')\s*(.+)',
        re.IGNORECASE,
    ),
]


def try_parse_user_reminder(user_message: str) -> tuple[str, str] | None:
    """Try to detect a reminder request in the user's message.

    Returns (time_expression, reminder_message) or None.
    Patterns support both orders:
      - "remind me in 30s to take a break"
      - "remind me to take a break in 30s"
    """
    text = user_message.strip()

    for i, pattern in enumerate(_REMINDER_PATTERNS):
        m = pattern.search(text)
        if not m:
            continue

        g1, g2 = m.group(1).strip(), m.group(2).strip()

        # For patterns where time comes SECOND (odd indices 1, 3, 5, 7),
        # g1 = message, g2 = time.
        # For patterns where time comes FIRST (even indices 0, 2, 4, 6, 8),
        # g1 = time, g2 = message.
        if i in (1, 3, 5, 7):
            time_expr, message = g2, g1
        else:
            time_expr, message = g1, g2

        # Strip leading "at " from time if present for parser compatibility
        time_clean = re.sub(r'^at\s+', '', time_expr, flags=re.IGNORECASE)

        # Clean up message — remove trailing punctuation
        message = message.rstrip('.,!?;: ')

        # Validate time parses
        trigger_at = parse_time_expression(time_clean)
        if trigger_at is not None:
            return time_clean, message

    return None
