import json
import unittest
from unittest.mock import Mock, patch

from gpu_worker.gemini_story_planner import GeminiPlannerError, generate_story_plan


class GeminiStoryPlannerTests(unittest.TestCase):
    def _response(self, plan):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [{
                "content": {"parts": [{"text": json.dumps(plan, ensure_ascii=False)}]}
            }]
        }
        return response

    def _valid_plan(self):
        return {
            "title_te": "యముడి కష్టం",
            "duration_seconds": 10,
            "aspect_ratio": "9:16",
            "scenes": [{
                "scene_number": 1,
                "start_seconds": 0,
                "end_seconds": 10,
                "visual_prompt_en": "A cinematic 3D CGI comedy scene",
                "camera": "medium shot",
                "characters": ["యముడు", "PJ Babu"],
                "action_te": "యముడు భయపడుతూ వస్తాడు",
                "dialogue_te": [{"speaker": "PJ Babu", "line": "ఏమైంది స్వామీ?"}],
                "audio_notes_te": "హాస్యభరిత నేపథ్య సంగీతం",
                "continuity_notes_te": "దుస్తులు మారకూడదు",
            }],
            "global_negative_prompt_en": "No text, no watermark",
        }

    def test_valid_plan_is_returned(self):
        with patch("gpu_worker.gemini_story_planner.requests.post", return_value=self._response(self._valid_plan())) as post:
            plan = generate_story_plan("యముడు భయపడుతూ వస్తాడు", api_key="test-key")
        self.assertEqual(plan["title_te"], "యముడి కష్టం")
        self.assertIn("x-goog-api-key", post.call_args.kwargs["headers"])

    def test_missing_key_is_rejected(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(GeminiPlannerError):
                generate_story_plan("యముడు వస్తాడు", api_key="")

    def test_invalid_plan_timing_is_rejected(self):
        plan = self._valid_plan()
        plan["scenes"][0]["end_seconds"] = 15
        with patch("gemini_story_planner.requests.post", return_value=self._response(plan)):
            with self.assertRaises(GeminiPlannerError):
                generate_story_plan("యముడు వస్తాడు", api_key="test-key")

    def test_markdown_json_fence_is_supported(self):
        from gpu_worker.gemini_story_planner import _extract_json
        parsed = _extract_json("```json\n{\"title_te\": \"సరే\"}\n```")
        self.assertEqual(parsed["title_te"], "సరే")


if __name__ == "__main__":
    unittest.main()
