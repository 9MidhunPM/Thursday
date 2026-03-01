"""
College data bridge for Thursday Web.

Imports the scraper module and provides:
  - background_refresh()  — non-blocking scrape (runs in thread)
  - get_college_context()  — returns a string block for the system prompt
  - get_subject_detail()   — deep-dive for a specific subject query
"""

import sys
import logging
import threading
from pathlib import Path
from datetime import datetime

# Make the scraper package importable
_SCRAPER_DIR = str(Path(__file__).resolve().parent.parent / "scraper")
if _SCRAPER_DIR not in sys.path:
    sys.path.insert(0, _SCRAPER_DIR)

import scraper  # noqa: E402

log = logging.getLogger("thursday.college")

# ── Background refresh ───────────────────────────────────────────────

_refresh_lock = threading.Lock()
_refreshing = False


def background_refresh(force: bool = False) -> None:
    """
    Kick off a scraper refresh in a background thread.
    Safe to call on every startup — it respects the staleness checks
    and won't hit the network if data is fresh.
    """
    global _refreshing

    if _refreshing:
        log.info("College scraper already running, skipping")
        return

    def _run():
        global _refreshing
        with _refresh_lock:
            _refreshing = True
            try:
                log.info("College data refresh starting …")
                scraper.refresh(force=force)
                log.info("College data refresh complete")
            except Exception as e:
                log.error("College data refresh failed: %s", e)
            finally:
                _refreshing = False

    t = threading.Thread(target=_run, daemon=True, name="college-refresh")
    t.start()


# ── Day helpers ──────────────────────────────────────────────────────

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _today_name() -> str:
    return _DAY_NAMES[datetime.now().weekday()]


def _tomorrow_name() -> str:
    return _DAY_NAMES[(datetime.now().weekday() + 1) % 7]


# ── Context builder ─────────────────────────────────────────────────

def get_college_context() -> str:
    """
    Build a compact text block summarising the student's college data.
    This goes into the system prompt so Thursday is always aware.
    Returns empty string if DB doesn't exist yet.
    Kept short to save prompt tokens for the actual response.
    """
    if not scraper.DB_PATH.exists():
        return ""

    parts: list[str] = []
    parts.append("[COLLEGE DATA]")

    # ── Marks (compact) ──────────────────────────────────────────────
    marks = scraper.get_all_marks()
    if marks:
        parts.append("Marks (Sessional):")
        for m in marks:
            obtained = m["marks_obtained"]
            pct = f"{obtained}/{m['max_marks']}" if obtained is not None else "N/A"
            # Use short name, skip semester/exam since there's only one
            parts.append(f"  {m['subject_name']}: {pct}")

    # ── Attendance (compact) ─────────────────────────────────────────
    attendance = scraper.get_all_attendance()
    if attendance:
        parts.append("Attendance:")
        for a in attendance:
            name = a["subject_name"] or a["subject_code"]
            parts.append(f"  {name}: {a['classes_attended']}/{a['classes_total']} ({a['percentage']}%)")

    # ── Today's timetable (skip free periods) ────────────────────────
    today = _today_name()
    today_tt = scraper.get_timetable(day=today)
    if today_tt:
        slots = []
        for t in today_tt:
            if t["subject_name"] and t["subject_name"] != "Free Period":
                slots.append(f"P{t['period']}({t['period_time']}) {t['subject_name']}")
        if slots:
            parts.append(f"Today ({today}): " + ", ".join(slots))
        else:
            parts.append(f"Today ({today}): No classes")

    # ── Tomorrow's timetable (skip free periods) ─────────────────────
    tomorrow = _tomorrow_name()
    tomorrow_tt = scraper.get_timetable(day=tomorrow)
    if tomorrow_tt:
        slots = []
        for t in tomorrow_tt:
            if t["subject_name"] and t["subject_name"] != "Free Period":
                slots.append(f"P{t['period']}({t['period_time']}) {t['subject_name']}")
        if slots:
            parts.append(f"Tomorrow ({tomorrow}): " + ", ".join(slots))

    parts.append("[/COLLEGE DATA]")
    return "\n".join(parts)


def get_subject_detail(query: str) -> str | None:
    """
    Look up a specific subject by partial name/code.
    Returns a formatted string, or None if not found.
    Used for deep-dive queries like "how am I doing in DAA?"
    """
    if not scraper.DB_PATH.exists():
        return None

    result = scraper.get_subject_summary(query)
    if not result:
        return None

    parts: list[str] = []

    if result["marks"]:
        for m in result["marks"]:
            obtained = m["marks_obtained"]
            pct = f"{obtained}/{m['max_marks']} ({obtained/m['max_marks']*100:.0f}%)" if obtained is not None else "N/A"
            parts.append(f"Marks: {m['subject_code']} {m['subject_name']} — {pct}")

    if result["attendance"]:
        for a in result["attendance"]:
            parts.append(
                f"Attendance: {a['classes_attended']}/{a['classes_total']} ({a['percentage']}%)"
            )

    if result["timetable"]:
        parts.append("Schedule:")
        for t in result["timetable"]:
            if t["subject_name"] and t["subject_name"] != "Free Period":
                ctype = f" [{t['class_type']}]" if t.get("class_type") else ""
                parts.append(f"  {t['day']} P{t['period']} ({t['period_time']}){ctype}")

    return "\n".join(parts) if parts else None
