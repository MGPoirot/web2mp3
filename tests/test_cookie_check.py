import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cookie_check
from cookie_check import assess_content, classify_probe, _rotation_message


def _row(name: str, value: str = "value") -> str:
    return f".youtube.com\tTRUE\t/\tTRUE\t2715301110\t{name}\t{value}\n"


BOTH_LOGIN = (
    "# Netscape HTTP Cookie File\n"
    + _row("__Secure-1PSID")
    + _row("__Secure-3PSID")
)
SIGNED_OUT = _row("__Secure-1PSIDTS") + _row("VISITOR_INFO1_LIVE")
HTTPONLY = (
    "# Netscape HTTP Cookie File\n"
    "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t2715301110\t__Secure-1PSID\tabc\n"
    + _row("__Secure-3PSID")
)


class AssessContentTests(unittest.TestCase):
    def test_both_login_cookies(self):
        status = assess_content(BOTH_LOGIN, path="/tmp/cookies.txt")
        self.assertTrue(status.ok)
        self.assertIn('looks valid: "/tmp/cookies.txt"', status.message)

    def test_signed_out_psidts_is_not_login(self):
        status = assess_content(SIGNED_OUT, path="/tmp/cookies.txt")
        self.assertFalse(status.ok)
        self.assertIn("missing __Secure-1PSID, __Secure-3PSID", status.message)
        self.assertIn("2 non-login cookies", status.message)
        self.assertIn("Get cookies.txt LOCALLY", status.message)

    def test_empty(self):
        status = assess_content("  \n\t")
        self.assertFalse(status.ok)
        self.assertTrue(status.message.startswith("Cookie file is empty"))
        self.assertIn("Get cookies.txt LOCALLY", status.message)

    def test_non_netscape(self):
        status = assess_content("this is just some text\nnot cookies\n")
        self.assertFalse(status.ok)
        self.assertIn("Netscape cookies.txt export", status.message)
        self.assertIn("no tab-separated cookie lines", status.message)

    def test_httponly_prefix(self):
        status = assess_content(HTTPONLY)
        self.assertTrue(status.ok)

    def test_rotated_when_youtube_clears_auth(self):
        self.assertEqual(classify_probe(True, False, True), 'rotated')
        self.assertEqual(classify_probe(True, False, False), 'rotated')

    def test_not_rotated_when_session_survives(self):
        self.assertEqual(classify_probe(True, True, False), 'ok')

    def test_rotation_message_explains_age_gate(self):
        message = _rotation_message('/tmp/cookies.txt')
        self.assertIn('rotated', message)
        self.assertIn('Sign in to confirm your age', message)
        self.assertNotIn('looks valid', message)


class UploadApiTests(unittest.TestCase):
    def setUp(self):
        self._password = os.environ.pop("GUI_PASSWORD", None)
        self._cookie_file = os.environ.get("COOKIE_FILE")
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self.tmp.name) / "cookies.txt"
        os.environ["COOKIE_FILE"] = str(self.dest)
        self._destination_path = cookie_check.destination_path
        self._first_cookie_file = cookie_check.first_cookie_file
        cookie_check.destination_path = lambda: self.dest
        cookie_check.first_cookie_file = lambda: None

    def tearDown(self):
        cookie_check.destination_path = self._destination_path
        cookie_check.first_cookie_file = self._first_cookie_file
        if self._cookie_file is None:
            os.environ.pop("COOKIE_FILE", None)
        else:
            os.environ["COOKIE_FILE"] = self._cookie_file
        if self._password is None:
            os.environ.pop("GUI_PASSWORD", None)
        else:
            os.environ["GUI_PASSWORD"] = self._password
        self.tmp.cleanup()

    def test_bad_upload_explains_and_does_not_write(self):
        from fastapi.testclient import TestClient
        from gui.server import app
        import runner

        # Lifespan reconciliation walks the live GUI session DB. Don't let a
        # unit test mark a real in-progress download as failed.
        list_all = runner.sessions.list_all
        runner.sessions.list_all = lambda: []
        try:
            with TestClient(app) as client:
                res = client.post(
                    "/api/cookies",
                    files={"file": ("cookies.txt", b"not a cookie file\n", "text/plain")},
                )
        finally:
            runner.sessions.list_all = list_all
        self.assertEqual(res.status_code, 400)
        body = res.json()
        self.assertFalse(body["ok"])
        self.assertIn("Netscape", body["message"])
        self.assertFalse(self.dest.exists())
        self.assertFalse(list(Path(self.tmp.name).glob("**/*cookies.txt")))
