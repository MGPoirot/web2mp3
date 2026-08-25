import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from download_errors import classify_download_error


class ClassifyDownloadErrorTests(unittest.TestCase):
    def test_permanent_unavailable(self):
        kind, reason = classify_download_error("ERROR: [youtube] abc: Video unavailable")
        self.assertEqual(kind, "permanent")
        self.assertIn("unavailable", reason)

    def test_permanent_private(self):
        kind, _ = classify_download_error("Private video")
        self.assertEqual(kind, "permanent")

    def test_permanent_removed(self):
        kind, _ = classify_download_error("This video has been removed by the uploader")
        self.assertEqual(kind, "permanent")

    def test_permanent_copyright(self):
        kind, _ = classify_download_error("This video is no longer available due to a copyright claim")
        self.assertEqual(kind, "permanent")

    def test_permanent_not_available(self):
        kind, _ = classify_download_error("This video is not available")
        self.assertEqual(kind, "permanent")

    def test_retryable_bot_check(self):
        kind, _ = classify_download_error(
            "Sign in to confirm you're not a bot. This helps protect our community."
        )
        self.assertEqual(kind, "retryable")

    def test_retryable_age_gate(self):
        kind, _ = classify_download_error("Sign in to confirm your age")
        self.assertEqual(kind, "retryable")

    def test_retryable_cookies(self):
        kind, _ = classify_download_error("The provided cookies do not work")
        self.assertEqual(kind, "retryable")

    def test_retryable_http_429(self):
        kind, _ = classify_download_error("HTTP Error 429: Too Many Requests")
        self.assertEqual(kind, "retryable")

    def test_retryable_timeout(self):
        kind, _ = classify_download_error("The read operation timed out")
        self.assertEqual(kind, "retryable")

    def test_retryable_dns(self):
        kind, _ = classify_download_error("Failed to resolve 'www.youtube.com' [Errno -3] Temporary failure in name resolution DNS")
        self.assertEqual(kind, "retryable")

    def test_retryable_503(self):
        kind, _ = classify_download_error("HTTP Error 503: Service Unavailable")
        self.assertEqual(kind, "retryable")

    def test_retryable_deno_challenge(self):
        kind, _ = classify_download_error("Unable to solve JS challenge using deno")
        self.assertEqual(kind, "retryable")

    def test_unknown_defaults_to_retryable(self):
        kind, reason = classify_download_error("something completely unexpected")
        self.assertEqual(kind, "retryable")
        self.assertEqual(reason, "unknown")


if __name__ == "__main__":
    unittest.main()
