"""Tests for the hardcoded Gemini primary/backup retry policy."""
import ast
import unittest
from pathlib import Path
from unittest.mock import Mock

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def load_helpers():
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted_assignments = {"GEMINI_PRIMARY_MODEL", "GEMINI_BACKUP_MODEL", "GEMINI_TEXT_MODELS"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in wanted_assignments
            for target in node.targets
        ):
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in {
            "_strip_gemini_thinking_settings", "gemini_generate_content"
        }:
            nodes.append(node)

    class FakeResponse:
        def __init__(self, status_code, message=""):
            self.status_code = status_code
            self.ok = 200 <= status_code < 300
            self.text = message
            self.headers = {}

        def json(self):
            return {"error": {"message": self.text}}

    class FakeRequests:
        class RequestException(Exception):
            pass

        def __init__(self, responses):
            self.responses = list(responses)
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            value = self.responses.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

    clock = Mock()
    namespace = {"requests": None, "time": clock, "GEMINI_KEY": "test-key"}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    return namespace, FakeRequests, FakeResponse, clock


class GeminiRetryTests(unittest.TestCase):
    def setUp(self):
        self.ns, self.FakeRequests, self.Response, self.clock = load_helpers()
        self.contents = [{"parts": [{"text": "hello", "thinkingLevel": "MINIMAL"}]}]
        self.config = {"temperature": 0.2, "thinkingConfig": {"thinkingLevel": "MINIMAL"}}

    def test_hardcoded_model_order(self):
        self.assertEqual(self.ns["GEMINI_PRIMARY_MODEL"], "gemini-3.5-flash-lite")
        self.assertEqual(self.ns["GEMINI_BACKUP_MODEL"], "gemini-3.8-flash")
        self.assertEqual(
            self.ns["GEMINI_TEXT_MODELS"],
            ("gemini-3.5-flash-lite", "gemini-3.8-flash"),
        )

    def test_secrets_override_is_not_used_and_thinking_keys_are_stripped(self):
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn('st.secrets.get("GEMINI_TEXT_MODELS"', source)
        clean = self.ns["_strip_gemini_thinking_settings"]({
            "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            "nested": [{"thinking_level": "LOW", "ok": True}],
        })
        self.assertEqual(clean, {"nested": [{"ok": True}]})

    def test_primary_success_does_not_call_backup(self):
        fake = self.FakeRequests([self.Response(200)])
        self.ns["requests"] = fake
        response, model = self.ns["gemini_generate_content"](self.contents, self.config)
        self.assertTrue(response.ok)
        self.assertEqual(model, "gemini-3.5-flash-lite")
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("/models/gemini-3.5-flash-lite:", fake.calls[0][0])
        body = fake.calls[0][1]["json"]
        self.assertEqual(body["generationConfig"], {"temperature": 0.2})
        self.assertEqual(body["contents"], [{"parts": [{"text": "hello"}]}])

    def test_primary_four_retries_then_backup(self):
        fake = self.FakeRequests([
            self.Response(503, "busy 1"), self.Response(503, "busy 2"),
            self.Response(503, "busy 3"), self.Response(503, "busy 4"),
            self.Response(503, "busy 5"), self.Response(200),
        ])
        self.ns["requests"] = fake
        messages = []
        response, model = self.ns["gemini_generate_content"](
            self.contents, self.config, status_callback=messages.append
        )
        self.assertTrue(response.ok)
        self.assertEqual(model, "gemini-3.8-flash")
        self.assertEqual(len(fake.calls), 6)
        self.assertEqual(
            [call.args[0] for call in self.clock.sleep.call_args_list],
            [3, 6, 12, 20],
        )
        self.assertTrue(any("(1/4)" in message for message in messages))
        self.assertTrue(any("Backup model tho try chesthunna..." in message for message in messages))
        self.assertTrue(all("/models/gemini-3.5-flash-lite:" in fake.calls[i][0] for i in range(5)))
        self.assertIn("/models/gemini-3.8-flash:", fake.calls[5][0])

    def test_backup_gets_two_retries(self):
        fake = self.FakeRequests([
            self.Response(503), self.Response(503), self.Response(503),
            self.Response(503), self.Response(503), self.Response(503),
            self.Response(503), self.Response(503),
        ])
        self.ns["requests"] = fake
        response, model = self.ns["gemini_generate_content"](self.contents, self.config)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(model, "gemini-3.8-flash")
        self.assertEqual(len(fake.calls), 8)
        self.assertEqual(
            [call.args[0] for call in self.clock.sleep.call_args_list],
            [3, 6, 12, 20, 3, 6],
        )

    def test_429_waits_once_and_never_switches_to_backup(self):
        fake = self.FakeRequests([
            self.Response(429, "Please retry in 45s"),
            self.Response(200),
        ])
        self.ns["requests"] = fake
        response, model = self.ns["gemini_generate_content"](self.contents, self.config)
        self.assertTrue(response.ok)
        self.assertEqual(model, "gemini-3.5-flash-lite")
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(self.clock.sleep.call_args.args, (30,))
        self.assertTrue(all("/models/gemini-3.5-flash-lite:" in call[0] for call in fake.calls))

    def test_400_401_403_do_not_retry_or_use_backup(self):
        for status in (400, 401, 403):
            with self.subTest(status=status):
                fake = self.FakeRequests([self.Response(status, "bad request")])
                self.ns["requests"] = fake
                response, model = self.ns["gemini_generate_content"](self.contents, self.config)
                self.assertEqual(response.status_code, status)
                self.assertEqual(model, "gemini-3.5-flash-lite")
                self.assertEqual(len(fake.calls), 1)


if __name__ == "__main__":
    unittest.main()
