import unittest

from gpu_worker.story_plan import build_story_planner_prompt, validate_story_plan


class StoryPlanTests(unittest.TestCase):
    def test_prompt_keeps_telugu_story_and_schema(self):
        prompt = build_story_planner_prompt(
            "యముడు దున్నపోతు మీద భయపడుతూ వస్తాడు. PJ Babu ఏమైందని అడుగుతాడు.",
            duration_seconds=10,
        )
        self.assertIn("తెలుగు మాత్రమే", prompt)
        self.assertIn("visual_prompt_en", prompt)
        self.assertIn("యముడు", prompt)

    def test_rejects_empty_story_and_bad_ratio(self):
        with self.assertRaises(ValueError):
            build_story_planner_prompt(" ")
        with self.assertRaises(ValueError):
            build_story_planner_prompt("కథ", aspect_ratio="4:3")

    def test_validates_scene_timing_and_required_visual(self):
        plan = {
            "scenes": [
                {"start_seconds": 0, "end_seconds": 3, "visual_prompt_en": "Yama on buffalo", "dialogue_te": []},
                {"start_seconds": 3, "end_seconds": 7, "visual_prompt_en": "PJ asks", "dialogue_te": []},
            ]
        }
        self.assertEqual(validate_story_plan(plan, expected_duration=10), [])
        plan["scenes"][1]["start_seconds"] = 2
        self.assertTrue(any("ఓవర్‌ల్యాప్" in error for error in validate_story_plan(plan)))


if __name__ == "__main__":
    unittest.main()
