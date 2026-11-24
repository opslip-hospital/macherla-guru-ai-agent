"""Regression tests for the restored Nov 21 Gemini SEO request behavior."""
import ast
import json
import unittest
from pathlib import Path
from unittest.mock import Mock

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def load_gemini_helpers():
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "gemini_generate_content"
    ]
    assignments = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "GEMINI_TEXT_MODELS"
                for target in node.targets)
    ]
    assert len(nodes) == 1 and len(assignments) == 1
    module = ast.Module(body=assignments + nodes, type_ignores=[])

    class FakeResponse:
        def __init__(self, status_code, message=""):
            self.status_code = status_code
            self.ok = 200 <= status_code < 300
            self.text = message
            self.headers = {}
            self._message = message

        def json(self):
            return {"error": {"message": self._message}}

    class FakeRequests:
        RequestException = Exception

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
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace, FakeRequests, FakeResponse, clock


class GeminiRequestTests(unittest.TestCase):
    def setUp(self):
        self.ns, self.FakeRequests, self.Response, self.clock = load_gemini_helpers()
        self.contents = [{"parts": [{"text": "hello"}]}]
        self.config = {"temperature": 0.2, "thinkingConfig": {"thinkingLevel": "MINIMAL"}}

    def test_restores_nov_21_model_order(self):
        self.assertEqual(
            self.ns["GEMINI_TEXT_MODELS"],
            ("gemini-3.8-flash", "gemini-3.5-flash-lite"),
        )

    def test_primary_success_returns_without_backup(self):
        fake = self.FakeRequests([self.Response(200)])
        self.ns["requests"] = fake
        response, model = self.ns["gemini_generate_content"](self.contents, self.config)
        self.assertTrue(response.ok)
        self.assertEqual(model, "gemini-3.8-flash")
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("/models/gemini-3.8-flash:", fake.calls[0][0])
        self.assertEqual(fake.calls[0][1]["json"]["generationConfig"], self.config)

    def test_falls_back_after_configured_retries(self):
        fake = self.FakeRequests([
            self.Response(503, "busy"),
            self.Response(503, "still busy"),
            self.Response(200),
        ])
        self.ns["requests"] = fake
        response, model = self.ns["gemini_generate_content"](
            self.contents, self.config, retries_per_model=1
        )
        self.assertTrue(response.ok)
        self.assertEqual(model, "gemini-3.5-flash-lite")
        self.assertEqual(len(fake.calls), 3)
        self.assertIn("/models/gemini-3.8-flash:", fake.calls[0][0])
        self.assertIn("/models/gemini-3.8-flash:", fake.calls[1][0])
        self.assertIn("/models/gemini-3.5-flash-lite:", fake.calls[2][0])
        self.assertEqual(self.clock.sleep.call_args_list[0].args, (2,))

    def test_seo_call_restores_explicit_order_and_thinking_config(self):
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertIn('"thinkingConfig": {"thinkingLevel": "MINIMAL"}', source)
        self.assertIn('models=("gemini-3.5-flash-lite", "gemini-3.8-flash")', source)
        self.assertIn("retries_per_model=0", source)
        self.assertNotIn("_strip_gemini_thinking_settings", source)

    def test_bad_request_returns_without_retry_or_backup(self):
        fake = self.FakeRequests([self.Response(400, "invalid request")])
        self.ns["requests"] = fake
        response, model = self.ns["gemini_generate_content"](self.contents, self.config)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(model, "gemini-3.8-flash")
        self.assertEqual(len(fake.calls), 1)


if __name__ == "__main__":
    unittest.main()
