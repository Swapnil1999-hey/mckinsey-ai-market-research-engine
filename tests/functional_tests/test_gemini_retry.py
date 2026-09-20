import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from services import providers  # noqa: E402


class FakeResponse:
    def __init__(self, status_code, body=None, text=""):
        self.status_code = status_code
        self._body = body
        self.text = text
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._body


def success_response():
    return FakeResponse(
        200,
        {
            "candidates": [
                {"content": {"parts": [{"text": '{"ok": true}' }]}}
            ]
        },
    )


class GeminiRetryTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "GEMINI_API_KEY": "test-key",
            "GEMINI_MODEL": "gemini-primary",
            "GEMINI_FALLBACK_MODEL": "gemini-fallback",
            "GEMINI_MAX_RETRIES": "2",
            "GEMINI_RETRY_BASE_SECONDS": "0",
            "GEMINI_TIMEOUT_SECONDS": "5",
        }
        self.env_patch = patch.dict(os.environ, self.env, clear=False)
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()

    @patch("services.providers.time.sleep")
    @patch("services.providers.random.uniform", return_value=0)
    @patch("services.providers.requests.post")
    def test_retries_503_then_succeeds(self, post, _jitter, _sleep):
        post.side_effect = [
            FakeResponse(503, text="busy"),
            FakeResponse(503, text="busy"),
            success_response(),
        ]
        result = providers.gemini_json("test", {"type": "object"})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(post.call_count, 3)
        self.assertIn("gemini-primary", post.call_args_list[0].args[0])

    @patch("services.providers.time.sleep")
    @patch("services.providers.random.uniform", return_value=0)
    @patch("services.providers.requests.post")
    def test_primary_exhaustion_falls_back(self, post, _jitter, _sleep):
        post.side_effect = [
            FakeResponse(503, text="busy"),
            FakeResponse(503, text="busy"),
            FakeResponse(503, text="busy"),
            success_response(),
        ]
        result = providers.gemini_json("test", {"type": "object"})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(post.call_count, 4)
        self.assertIn("gemini-fallback", post.call_args_list[-1].args[0])


if __name__ == "__main__":
    unittest.main()
