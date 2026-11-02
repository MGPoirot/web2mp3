import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gui.runner import exit_status
import sessions


TRACE = """
spotipy.exceptions.SpotifyException: http status: 429, code:-1 - /v1/albums/6KoGMkF6Fp3W9C339E5eVx/tracks/?limit=50&offset=15:
 Max Retries, reason: too many 429 error responses
"""


class ExitStatusTests(unittest.TestCase):
    def test_spotify_max_retries_429_is_throttled(self):
        self.assertEqual(exit_status(1, TRACE), "throttled")

    def test_single_429_stays_failed(self):
        self.assertEqual(exit_status(1, "HTTP Error 429: Too Many Requests"), "failed")

    def test_other_failure_stays_failed(self):
        self.assertEqual(exit_status(1, "Video unavailable"), "failed")

    def test_zero_exit_is_done_even_if_text_mentions_retries(self):
        self.assertEqual(exit_status(0, TRACE), "done")


class SessionsSchemaTests(unittest.TestCase):
    def test_existing_db_accepts_throttled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.sqlite3"
            conn = sqlite3.connect(path)
            conn.execute(
                """
                CREATE TABLE submissions (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('running', 'needs_input', 'done', 'failed')),
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO submissions (id, url, status, created_at, updated_at) VALUES ('abc', 'http://x', 'failed', 1, 1)"
            )
            conn.commit()
            conn.close()

            original = sessions.DB_PATH
            sessions.DB_PATH = path
            try:
                sessions.set_status("abc", "throttled")
                self.assertEqual(sessions.get("abc")["status"], "throttled")
            finally:
                sessions.DB_PATH = original
