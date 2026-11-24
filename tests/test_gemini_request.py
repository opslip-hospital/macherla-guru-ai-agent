"""Regression tests for Gemini primary/backup retry behavior in the YT Manager."""
import ast
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, call

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def load_gemini_helpers():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    wanted = {"_strip_gemini_thinking_settings", "gemini_generate_content", "gemini_failure_message"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assignments = [n for n in tree.body if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id in {"GEMINI_PRIMARY_MODEL", "GEMINI_BACKUP_MODEL", "GEMINI_TEXT_MODELS"}
        for t in n.targets)]
    assert {n.name for n in nodes} == wanted and len(assignments) == 3
    module = ast.Module(body=assignments + nodes, type_ignores=[])

    class FakeResponse:
        def __init__(self, status_code, message=""):
            self.status_code, self.ok, self.text = status_code, 200 <= status_code < 300, message
            self._message = message
        def json(self):
            return {"error": {"message": self._message}}

    class FakeRequests:
        RequestException = Exception
        def __init__(self, responses):
            self.responses, self.calls = list(responses), []
        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            value = self.responses.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

    fake_time = Mock()
    ns = {"requests": None, "time": fake_time, "re": __import__("re"), "GEMINI_KEY": "test-key"}
    exec(compile(module, str(APP_PATH), "exec"), ns)
    return ns, FakeRequests, FakeResponse, fake_time


class GeminiRequestTests(unittest.TestCase):
    def setUp(self):
        self.ns, self.FakeRequests, self.Response, self.clock = load_gemini_helpers()
        self.contents = [{"parts": [{"text": "hello"}]}]
        self.config = {"temperature": 0.2, "thinkingConfig": {"thinkingLevel": "MINIMAL"},
                       "nested": [{"thinking_level": "MINIMAL"}]}

    def test_primary_backup_constants_and_secret_override_ignored(self):
        self.assertEqual(self.ns["GEMINI_PRIMARY_MODEL"], "gemini-3.5-flash-lite")
        self.assertEqual(self.ns["GEMINI_BACKUP_MODEL"], "gemini-3.8-flash")
        self.assertEqual(self.ns["GEMINI_TEXT_MODELS"], ["gemini-3.5-flash-lite", "gemini-3.8-flash"])
        self.assertNotIn('st.secrets.get("GEMINI_TEXT_MODELS"', APP_PATH.read_text(encoding="utf-8"))

    def test_thinking_controls_removed_from_nested_request_payload(self):
        clean = self.ns["_strip_gemini_thinking_settings"]({"contents": self.contents, "generationConfig": self.config})
        for key in ("thinkingConfig", "thinkingLevel", "thinking_level"):
            self.assertNotIn(key, json.dumps(clean))

    def test_primary_success_does_not_use_backup(self):
        fake = self.FakeRequests([self.Response(200)])
        self.ns["requests"] = fake
        response, model = self.ns["gemini_generate_content"](self.contents, self.config, models=["ignored"])
        self.assertTrue(response.ok)
        self.assertEqual(model, "gemini-3.5-flash-lite")
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("/models/gemini-3.5-flash-lite:", fake.calls[0][0])
        self.assertNotIn("thinkingConfig", json.dumps(fake.calls[0][1]["json"]))

    def test_primary_503_four_retries_then_backup(self):
        fake = self.FakeRequests([self.Response(503, "busy")] * 5 + [self.Response(200)])
        self.ns["requests"] = fake
        messages = []
        response, model = self.ns["gemini_generate_content"](self.contents, self.config, status_callback=messages.append)
        self.assertTrue(response.ok)
        self.assertEqual(model, "gemini-3.8-flash")
        self.assertEqual(len(fake.calls), 6)
        self.assertEqual([c.args[0] for c in self.clock.sleep.call_args_list], [3, 6, 12, 20, 3])
        self.assertTrue(any("(1/4)" in msg for msg in messages))
        self.assertIn("Backup model tho try chesthunna...", messages)

    def test_backup_gets_two_retries(self):
        fake = self.FakeRequests([self.Response(502)] * 5 + [self.Response(500)] * 3)
        self.ns["requests"] = fake
        response, model = self.ns["gemini_generate_content"](self.contents, self.config)
        self.assertEqual(model, "gemini-3.8-flash")
        self.assertEqual(response.status_code, 500)
        self.assertTrue(response._gemini_server_busy)
        self.assertEqual(len(fake.calls), 8)
        self.assertEqual([c.args[0] for c in self.clock.sleep.call_args_list], [3, 6, 12, 20, 3, 6, 3])

    def test_429_waits_from_error_once_and_never_switches_to_backup(self):
        fake = self.FakeRequests([self.Response(429, "Quota; retry in 45s"), self.Response(429, "still limited")])
        self.ns["requests"] = fake
        response, model = self.ns["gemini_generate_content"](self.contents, self.config)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(model, "gemini-3.5-flash-lite")
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(self.clock.sleep.call_args_list, [call(30)])
        self.assertTrue(all("gemini-3.8-flash" not in url for url, _ in fake.calls))

    def test_429_short_delay_and_30_second_cap(self):
        for message, expected in [("retry in 7s", 7), ("retry in 90s", 30)]:
            fake = self.FakeRequests([self.Response(429, message), self.Response(200)])
            self.ns["requests"] = fake
            self.clock.reset_mock()
            response, model = self.ns["gemini_generate_content"](self.contents, self.config)
            self.assertTrue(response.ok)
            self.assertEqual(model, "gemini-3.5-flash-lite")
            self.assertEqual(self.clock.sleep.call_args_list, [call(expected)])

    def test_400_401_403_do_not_retry_or_fallback(self):
        for status in (400, 401, 403):
            fake = self.FakeRequests([self.Response(status, "bad request")])
            self.ns["requests"] = fake
            response, model = self.ns["gemini_generate_content"](self.contents, self.config)
            self.assertEqual(response.status_code, status)
            self.assertEqual(model, "gemini-3.5-flash-lite")
            self.assertEqual(len(fake.calls), 1)

    def test_final_server_failure_message(self):
        fake = self.FakeRequests([self.Response(503)] * 5 + [self.Response(503)] * 3)
        self.ns["requests"] = fake
        response, model = self.ns["gemini_generate_content"](self.contents, self.config)
        self.assertEqual(self.ns["gemini_failure_message"](response, model),
            "Google server busy undi. 1–2 nimishాలు aagi malli button nokku. Video malli upload avvadu.")


if __name__ == "__main__":
    unittest.main()
