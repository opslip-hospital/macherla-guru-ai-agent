"""Regression tests for the YouTube Manager Gemini request wrapper.

The app is a Streamlit script, so extract only the pure/request helper definitions
to avoid executing the dashboard while testing.
"""
import ast
import json
import unittest
from pathlib import Path
from unittest.mock import Mock

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def load_gemini_helpers():
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"_strip_gemini_thinking_settings", "gemini_generate_content"}
    nodes = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    ]
    assignments = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "GEMINI_TEXT_MODELS"
                for target in node.targets)
    ]
    assert {node.name for node in nodes} == wanted
    assert len(assignments) == 1
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
            return self.responses.pop(0)

    namespace = {
        "requests": None,
        "time": Mock(),
        "GEMINI_KEY": "test-key",
    }
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace, FakeRequests, FakeResponse


class GeminiRequestTests(unittest.TestCase):
    def setUp(self):
        self.ns, self.FakeRequests, self.Response = load_gemini_helpers()

    def test_only_flash_lite_is_configured(self):
        self.assertEqual(self.ns["GEMINI_TEXT_MODELS"], ["gemini-3.5-flash-lite"])

    def test_nested_thinking_controls_are_removed(self):
        value = {
            "temperature": 0.4,
            "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            "nested": [{"thinking_level": "MINIMAL", "thinking_config": {"x": 1}}],
        }
        cleaned = self.ns["_strip_gemini_thinking_settings"](value)
        self.assertEqual(cleaned, {"temperature": 0.4, "nested": [{}]})

    def test_model_override_argument_is_ignored_and_payload_is_clean(self):
        fake = self.FakeRequests([self.Response(200)])
        self.ns["requests"] = fake
        response, model = self.ns["gemini_generate_content"](
            [{"parts": [{"text": "hello"}]}],
            {"temperature": 0.2, "thinkingConfig": {"thinkingLevel": "MINIMAL"}},
            models=["gemini-3.8-flash"],
        )
        self.assertTrue(response.ok)
        self.assertEqual(model, "gemini-3.5-flash-lite")
        url, kwargs = fake.calls[0]
        self.assertIn("/models/gemini-3.5-flash-lite:generateContent", url)
        self.assertNotIn("thinkingConfig", json.dumps(kwargs["json"]))
        self.assertNotIn("thinkingLevel", json.dumps(kwargs["json"]))

    def test_thinking_related_400_retries_once_without_thinking_settings(self):
        fake = self.FakeRequests([
            self.Response(400, "Thinking level MINIMAL is not supported for this model"),
            self.Response(200),
        ])
        self.ns["requests"] = fake
        response, model = self.ns["gemini_generate_content"](
            [{"parts": [{"text": "hello"}]}],
            {"temperature": 0.2, "thinkingConfig": {"thinkingLevel": "MINIMAL"}},
            retries_per_model=0,
        )
        self.assertTrue(response.ok)
        self.assertEqual(model, "gemini-3.5-flash-lite")
        self.assertEqual(len(fake.calls), 2)
        for _, kwargs in fake.calls:
            payload = json.dumps(kwargs["json"])
            self.assertNotIn("thinkingConfig", payload)
            self.assertNotIn("thinkingLevel", payload)

    def test_non_thinking_400_does_not_retry(self):
        fake = self.FakeRequests([self.Response(400, "Invalid request")])
        self.ns["requests"] = fake
        response, _ = self.ns["gemini_generate_content"](
            [{"parts": [{"text": "hello"}]}], {"temperature": 0.2},
            retries_per_model=0,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(fake.calls), 1)


if __name__ == "__main__":
    unittest.main()
