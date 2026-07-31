"""
SQLite-backed GUI submission history, mirroring src/index.py's pattern.

Each row tracks one GUI submission (one URL, one spawned CLI subprocess).
The full live/finished transcript is stored separately as plain text in
TRANSCRIPTS_DIR, named by submission id.

Uses a fresh short-lived connection per call rather than one persistent
connection (unlike index.py) since runner.py touches this from a background
reader thread as well as the asyncio event loop thread, and a single sqlite3
connection isn't safe to share across threads without extra locking -- calls
here are infrequent (a few per submission, not per output chunk), so the
per-call connection overhead is a non-issue.
"""
import sys
import time
import uuid
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from initialize import home_dir  # noqa: E402

GUI_DIR = home_dir / '.gui'
TRANSCRIPTS_DIR = GUI_DIR / 'transcripts'
DB_PATH = GUI_DIR / 'sessions.sqlite3'

GUI_DIR.mkdir(exist_ok=True)
TRANSCRIPTS_DIR.mkdir(exist_ok=True)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=5, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS submissions (
            id         TEXT PRIMARY KEY,
            url        TEXT NOT NULL,
            status     TEXT NOT NULL CHECK (status IN ('running', 'needs_input', 'done', 'failed')),
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_created ON submissions(created_at)")
    return conn


def create(url: str) -> str:
    """Creates a new submission row (status='running') and returns its id."""
    sid = uuid.uuid4().hex
    now = time.time()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO submissions (id, url, status, created_at, updated_at) VALUES (?, ?, 'running', ?, ?)",
            (sid, url, now, now),
        )
    return sid


def set_status(sid: str, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?",
            (status, time.time(), sid),
        )


def list_all() -> list[dict]:
    """Most recent submissions first, for the sidebar."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, url, status, created_at FROM submissions ORDER BY created_at DESC"
        ).fetchall()
    return [{'id': r[0], 'url': r[1], 'status': r[2], 'created_at': r[3]} for r in rows]


def get(sid: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, url, status, created_at FROM submissions WHERE id = ?", (sid,)
        ).fetchone()
    return None if row is None else {'id': row[0], 'url': row[1], 'status': row[2], 'created_at': row[3]}


def transcript_path(sid: str) -> Path:
    return TRANSCRIPTS_DIR / f'{sid}.log'


def read_transcript(sid: str) -> str:
    path = transcript_path(sid)
    return path.read_text(errors='replace') if path.is_file() else ''
