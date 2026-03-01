"""
Thursday College Scraper — Etlab Portal
Logs into sahrdaya.etlab.in, scrapes sessional marks, attendance,
and timetable, then stores everything in a local SQLite DB.

Refresh policy
 - attendance  : re-pull if data is older than 2 hours
 - marks       : re-pull if data is older than 7 days
 - timetable   : re-pull if data is older than 7 days

Usage:
    python scraper.py              # smart refresh (only stale data)
    python scraper.py --force      # force re-pull everything
    python scraper.py --query      # dump current DB contents
"""

import os
import re
import sys
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ── Config ───────────────────────────────────────────────────────────
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

BASE_URL = "https://sahrdaya.etlab.in"
LOGIN_URL = f"{BASE_URL}/user/login"
RESULTS_URL = f"{BASE_URL}/ktuacademics/student/results"
ATTENDANCE_URL = f"{BASE_URL}/ktuacademics/student/viewattendancesubject/41356045266"
TIMETABLE_URL = f"{BASE_URL}/student/timetable"

ETLAB_USERNAME = os.getenv("ETLAB_USERNAME")
ETLAB_PASSWORD = os.getenv("ETLAB_PASSWORD")

DB_PATH = Path(__file__).parent / "college.db"

# Refresh intervals
ATTENDANCE_MAX_AGE = timedelta(hours=2)
MARKS_MAX_AGE      = timedelta(days=7)
TIMETABLE_MAX_AGE  = timedelta(days=7)

# Generous timeout for slow college server
REQUEST_TIMEOUT = 90  # seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("etlab_scraper")


# =====================================================================
#  DATABASE
# =====================================================================

def init_db(db: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS marks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_code    TEXT    NOT NULL,
            subject_name    TEXT    NOT NULL,
            semester        TEXT    NOT NULL,
            exam_number     INTEGER NOT NULL,
            max_marks       REAL    NOT NULL,
            marks_obtained  REAL,
            scraped_at      TEXT    NOT NULL,
            UNIQUE(subject_code, semester, exam_number)
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_code    TEXT    NOT NULL UNIQUE,
            subject_name    TEXT,
            classes_attended INTEGER NOT NULL,
            classes_total    INTEGER NOT NULL,
            percentage       REAL    NOT NULL,
            scraped_at       TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS timetable (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            day             TEXT    NOT NULL,
            period          INTEGER NOT NULL,
            period_time     TEXT    NOT NULL,
            subject_code    TEXT,
            subject_name    TEXT,
            class_type      TEXT,
            teacher         TEXT,
            scraped_at      TEXT    NOT NULL,
            UNIQUE(day, period)
        );

        -- Tracks when each data category was last refreshed
        CREATE TABLE IF NOT EXISTS scrape_meta (
            category    TEXT PRIMARY KEY,
            last_scraped TEXT NOT NULL
        );
    """)
    db.commit()


def _needs_refresh(db: sqlite3.Connection, category: str, max_age: timedelta) -> bool:
    """Return True if `category` was never scraped or is older than max_age."""
    row = db.execute(
        "SELECT last_scraped FROM scrape_meta WHERE category = ?",
        (category,),
    ).fetchone()
    if not row:
        return True
    last = datetime.fromisoformat(row[0])
    stale = datetime.now() - last > max_age
    if stale:
        log.info("%s data is stale (last: %s)", category, row[0])
    else:
        log.info("%s data is fresh (last: %s)", category, row[0])
    return stale


def _update_meta(db: sqlite3.Connection, category: str) -> None:
    db.execute(
        "INSERT OR REPLACE INTO scrape_meta (category, last_scraped) VALUES (?, ?)",
        (category, datetime.now().isoformat()),
    )
    db.commit()


# =====================================================================
#  LOGIN
# =====================================================================

def _extract_csrf_token(html: str) -> str | None:
    match = re.search(r'"YII_CSRF_TOKEN"\s*:\s*"([^"]+)"', html)
    return match.group(1) if match else None


def create_session() -> requests.Session:
    """Return a requests.Session with login cookies set."""
    if not ETLAB_USERNAME or not ETLAB_PASSWORD:
        raise RuntimeError("ETLAB_USERNAME / ETLAB_PASSWORD not set in .env")

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    })

    log.info("Fetching login page …")
    resp = session.get(LOGIN_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    csrf = _extract_csrf_token(resp.text)

    payload = {
        "LoginForm[username]": ETLAB_USERNAME,
        "LoginForm[password]": ETLAB_PASSWORD,
        "yt0": "",
    }
    if csrf:
        payload["YII_CSRF_TOKEN"] = csrf

    log.info("Logging in as %s …", ETLAB_USERNAME)
    resp = session.post(LOGIN_URL, data=payload, allow_redirects=True, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    if "/user/login" in resp.url and "login-form" in resp.text:
        raise RuntimeError("Login failed — check credentials in .env")

    log.info("Login OK → %s", resp.url)
    return session


# =====================================================================
#  SCRAPERS
# =====================================================================

def _parse_subject_code_name(raw: str) -> tuple[str, str]:
    """
    '24CST403 - DESIGN AND ANALYSIS OF ALGORITHMS' → ('24CST403', 'DESIGN AND ANALYSIS OF ALGORITHMS')
    """
    parts = raw.split(" - ", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", raw.strip()


# ── Marks ────────────────────────────────────────────────────────────

def scrape_marks(session: requests.Session, db: sqlite3.Connection) -> int:
    """Scrape sessional exam marks (first table on the results page)."""
    log.info("Fetching marks: %s", RESULTS_URL)
    resp = session.get(RESULTS_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    tables = soup.find_all("table")
    if not tables:
        log.warning("No tables found on results page")
        return 0

    # First table = sessional exam marks
    table = tables[0]
    tbody = table.find("tbody") or table
    now = datetime.now().isoformat()
    count = 0

    for tr in tbody.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 5:
            continue

        code, name = _parse_subject_code_name(cells[0])
        semester   = cells[1]
        try:
            exam_num = int(cells[2])
        except ValueError:
            exam_num = 0
        try:
            max_marks = float(cells[3])
        except ValueError:
            max_marks = 0.0
        try:
            obtained = float(cells[4])
        except ValueError:
            obtained = None  # "Results not published" etc.

        db.execute("""
            INSERT INTO marks (subject_code, subject_name, semester, exam_number,
                               max_marks, marks_obtained, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(subject_code, semester, exam_number) DO UPDATE SET
                subject_name   = excluded.subject_name,
                max_marks      = excluded.max_marks,
                marks_obtained = excluded.marks_obtained,
                scraped_at     = excluded.scraped_at
        """, (code, name, semester, exam_num, max_marks, obtained, now))
        count += 1

    db.commit()
    _update_meta(db, "marks")
    log.info("Saved %d mark rows", count)
    return count


# ── Attendance ───────────────────────────────────────────────────────

def scrape_attendance(session: requests.Session, db: sqlite3.Connection) -> int:
    """
    Scrape subjectwise attendance.
    The page has one table where columns after the name are subject codes:
      UNi Reg No | Roll No | Name | 24MAT411 | 24CST402 | … | Total | Percentage
    Each cell looks like '22/24 (92%)'
    """
    log.info("Fetching attendance: %s", ATTENDANCE_URL)
    resp = session.get(ATTENDANCE_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    table = soup.find("table")
    if not table:
        log.warning("No attendance table found")
        return 0

    # Headers = subject codes (skip first 3: UNi Reg No, Roll No, Name)
    # and skip last 2: Total, Percentage
    thead = table.find("thead")
    headers = [th.get_text(strip=True) for th in thead.find_all(["th", "td"])] if thead else []
    subject_codes = headers[3:-2]  # just the subject code columns

    # Our row (should be only one student row or we find ours)
    tbody = table.find("tbody") or table
    rows = tbody.find_all("tr")
    now = datetime.now().isoformat()
    count = 0

    for tr in rows:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < len(headers):
            continue

        # cells[3:-2] correspond to subject_codes
        for i, code in enumerate(subject_codes):
            cell_val = cells[3 + i]
            # Parse '22/24 (92%)' → attended=22, total=24, pct=92
            m = re.match(r"(\d+)/(\d+)\s*\((\d+)%\)", cell_val)
            if not m:
                continue
            attended = int(m.group(1))
            total = int(m.group(2))
            pct = float(m.group(3))

            db.execute("""
                INSERT INTO attendance (subject_code, classes_attended, classes_total,
                                        percentage, scraped_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(subject_code) DO UPDATE SET
                    classes_attended = excluded.classes_attended,
                    classes_total    = excluded.classes_total,
                    percentage       = excluded.percentage,
                    scraped_at       = excluded.scraped_at
            """, (code, attended, total, pct, now))
            count += 1

    # Also try to populate subject_name from marks table
    db.execute("""
        UPDATE attendance SET subject_name = (
            SELECT m.subject_name FROM marks m
            WHERE m.subject_code = attendance.subject_code
            LIMIT 1
        ) WHERE subject_name IS NULL AND EXISTS (
            SELECT 1 FROM marks m WHERE m.subject_code = attendance.subject_code
        )
    """)

    db.commit()
    _update_meta(db, "attendance")
    log.info("Saved %d attendance rows", count)
    return count


# ── Timetable ────────────────────────────────────────────────────────

_PERIOD_RE = re.compile(
    r"Period\s+(\d+)\s*\[?\s*(\d{2}:\d{2}\s*[AP]M\s*-\s*\d{2}:\d{2}\s*[AP]M)\s*\]?"
)
_SUBJECT_RE = re.compile(
    r"^([\w\d]+)\s*-\s*(.+?)\[\s*(Theory|Lab|Practical|Tutorial)\s*\](.*)$",
    re.IGNORECASE,
)


def scrape_timetable(session: requests.Session, db: sqlite3.Connection) -> int:
    """
    Scrape weekly timetable (first table on the timetable page).
    """
    log.info("Fetching timetable: %s", TIMETABLE_URL)
    resp = session.get(TIMETABLE_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    tables = soup.find_all("table")
    if not tables:
        log.warning("No timetable tables found")
        return 0

    table = tables[0]
    thead = table.find("thead")
    headers_raw = [th.get_text(strip=True) for th in thead.find_all(["th", "td"])] if thead else []

    # Parse period numbers and times from header
    periods: list[tuple[int, str]] = []  # [(period_num, time_range), ...]
    for h in headers_raw[1:]:  # skip "Day"
        m = _PERIOD_RE.search(h)
        if m:
            periods.append((int(m.group(1)), m.group(2).strip()))
        else:
            # fallback
            periods.append((len(periods) + 1, h))

    tbody = table.find("tbody") or table
    now = datetime.now().isoformat()
    count = 0

    # Clear old timetable before inserting (full replace)
    db.execute("DELETE FROM timetable")

    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        day = cells[0].get_text(strip=True)
        if not day or day.lower() == "day":
            continue

        for i, (period_num, period_time) in enumerate(periods):
            if i + 1 >= len(cells):
                break
            cell_text = cells[i + 1].get_text(strip=True)

            if not cell_text or cell_text.lower() == "free period":
                # Still insert so Thursday knows a slot is free
                db.execute("""
                    INSERT INTO timetable (day, period, period_time, subject_code,
                                           subject_name, class_type, teacher, scraped_at)
                    VALUES (?, ?, ?, NULL, 'Free Period', NULL, NULL, ?)
                """, (day, period_num, period_time, now))
                count += 1
                continue

            # Try structured parse:  24CST403 - DESIGN ...[ Theory ]TEACHER NAME
            m = _SUBJECT_RE.match(cell_text)
            if m:
                code = m.group(1).strip()
                name = m.group(2).strip()
                ctype = m.group(3).strip()
                teacher = m.group(4).strip().rstrip(",") if m.group(4) else ""
            else:
                # Fallback: sometimes it's just "DATABASE MANAGEMENT SYSTEM LAB"
                code = ""
                name = cell_text
                ctype = "Lab" if "LAB" in cell_text.upper() else ""
                teacher = ""

            db.execute("""
                INSERT INTO timetable (day, period, period_time, subject_code,
                                       subject_name, class_type, teacher, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (day, period_num, period_time, code, name, ctype, teacher, now))
            count += 1

    db.commit()
    _update_meta(db, "timetable")
    log.info("Saved %d timetable slots", count)
    return count


# =====================================================================
#  ORCHESTRATOR
# =====================================================================

def refresh(force: bool = False) -> None:
    """
    Smart refresh: only re-scrape data that is stale.
    If force=True, re-scrape everything regardless.
    """
    db = sqlite3.connect(str(DB_PATH))
    init_db(db)

    need_marks      = force or _needs_refresh(db, "marks",      MARKS_MAX_AGE)
    need_attendance = force or _needs_refresh(db, "attendance",  ATTENDANCE_MAX_AGE)
    need_timetable  = force or _needs_refresh(db, "timetable",  TIMETABLE_MAX_AGE)

    if not (need_marks or need_attendance or need_timetable):
        log.info("All data is fresh — nothing to do.")
        db.close()
        return

    # Only login if we actually need to scrape something
    session = create_session()

    if need_marks:
        try:
            scrape_marks(session, db)
        except Exception as e:
            log.error("Failed to scrape marks: %s", e)

    if need_attendance:
        try:
            scrape_attendance(session, db)
        except Exception as e:
            log.error("Failed to scrape attendance: %s", e)

    if need_timetable:
        try:
            scrape_timetable(session, db)
        except Exception as e:
            log.error("Failed to scrape timetable: %s", e)

    db.close()
    log.info("Refresh complete. DB → %s", DB_PATH)


# =====================================================================
#  QUERY HELPERS  (for Thursday to import later)
# =====================================================================

def get_all_marks() -> list[dict]:
    """Return all marks from DB."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    rows = db.execute("SELECT * FROM marks ORDER BY semester, subject_code").fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_all_attendance() -> list[dict]:
    """Return all attendance from DB."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    rows = db.execute("SELECT * FROM attendance ORDER BY subject_code").fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_timetable(day: str | None = None) -> list[dict]:
    """Return timetable. Optionally filter by day."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    if day:
        rows = db.execute(
            "SELECT * FROM timetable WHERE LOWER(day) = LOWER(?) ORDER BY period",
            (day,),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM timetable ORDER BY day, period").fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_subject_summary(subject_query: str) -> dict | None:
    """
    Look up a subject by partial name or code.
    Returns marks + attendance + timetable slots for that subject.
    Useful for Thursday: "How am I doing in DAA?"
    """
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    q = f"%{subject_query}%"

    marks = db.execute(
        "SELECT * FROM marks WHERE subject_code LIKE ? OR subject_name LIKE ?",
        (q, q),
    ).fetchall()

    attendance = db.execute(
        "SELECT * FROM attendance WHERE subject_code LIKE ? OR subject_name LIKE ?",
        (q, q),
    ).fetchall()

    timetable = db.execute(
        "SELECT * FROM timetable WHERE subject_code LIKE ? OR subject_name LIKE ?",
        (q, q),
    ).fetchall()

    db.close()

    if not (marks or attendance or timetable):
        return None

    return {
        "marks":      [dict(r) for r in marks],
        "attendance":  [dict(r) for r in attendance],
        "timetable":   [dict(r) for r in timetable],
    }


def dump_db() -> None:
    """Pretty-print the full DB contents to stdout."""
    print("=" * 60)
    print("  MARKS")
    print("=" * 60)
    for m in get_all_marks():
        pct = f"{m['marks_obtained']}/{m['max_marks']}" if m['marks_obtained'] is not None else "N/A"
        print(f"  {m['subject_code']:12s}  {m['subject_name'][:40]:<40s}  "
              f"Sem: {m['semester']:<15s}  Exam {m['exam_number']}  {pct}")

    print()
    print("=" * 60)
    print("  ATTENDANCE")
    print("=" * 60)
    for a in get_all_attendance():
        name = a['subject_name'] or a['subject_code']
        print(f"  {a['subject_code']:12s}  {name[:40]:<40s}  "
              f"{a['classes_attended']}/{a['classes_total']}  ({a['percentage']}%)")

    print()
    print("=" * 60)
    print("  TIMETABLE")
    print("=" * 60)
    current_day = ""
    for t in get_timetable():
        if t['day'] != current_day:
            current_day = t['day']
            print(f"\n  {current_day}")
            print(f"  {'-' * 50}")
        name = t['subject_name'] or "—"
        ctype = f"[{t['class_type']}]" if t['class_type'] else ""
        teacher = t['teacher'] or ""
        print(f"    P{t['period']} ({t['period_time']:<21s})  {name[:35]:<35s} {ctype} {teacher}")

    print()


# =====================================================================
#  CLI
# =====================================================================

def main():
    force = "--force" in sys.argv
    query = "--query" in sys.argv

    if query:
        dump_db()
        return

    refresh(force=force)
    print()
    dump_db()


if __name__ == "__main__":
    main()
