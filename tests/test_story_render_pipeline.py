import unittest

from gpu_worker.story_render_pipeline import (
    DEFAULT_VOICE,
    StoryRenderPlanError,
    build_story_render_manifest,
)


class StoryRenderPipelineTests(unittest.TestCase):
    def valid_plan(self):
        return {
            "title_te": "యముడి కష్టం",
            "duration_seconds": 10,
            "aspect_ratio": "9:16",
            "scenes": [
                {
                    "scene_number": 1,
                    "start_seconds": 0,
                    "end_seconds": 4,
                    "visual_prompt_en": "Yama rides a buffalo into a village, looking frightened",
                    "camera": "medium shot, gentle push in",
                    "characters": ["Yamudu", "PJ Babu"],
                    "action_te": "యముడు భయపడుతూ వస్తాడు",
                    "dialogue_te": [
                        {"speaker": "PJ Babu", "line": "ఏమైంది స్వామీ?"},
                    ],
                    "audio_notes_te": "",
                    "continuity_notes_te": "యముడి కిరీటం, దుస్తులు మారకూడదు",
                },
                {
                    "scene_number": 2,
                    "start_seconds": 4,
                    "end_seconds": 10,
                    "visual_prompt_en": "Yama explains with a comic embarrassed expression",
                    "camera": "close-up, slight orbit",
                    "characters": ["Yamudu"],
                    "action_te": "యముడు తన బాధ చెబుతాడు",
                    "dialogue_te": [
                        {"speaker": "Yamudu", "line": "గిన్నెలు నీట్‌గా తోమలేదని చీపురుతో కొట్టిందిరా!"},
                    ],
                    "audio_notes_te": "",
                    "continuity_notes_te": "అదే ముఖం, అదే దుస్తులు",
                },
            ],
        }

    def test_builds_scene_jobs_and_telugu_dialogue(self):
        manifest = build_story_render_manifest(self.valid_plan(), reference_image_name="pj-babu.png")
        self.assertEqual(manifest["scene_count"], 2)
        self.assertEqual(manifest["render_status"], "prepared_not_rendered")
        self.assertEqual(manifest["render_jobs"][0]["frame_num"] % 4, 1)
        self.assertEqual(manifest["render_jobs"][0]["reference_image_name"], "pj-babu.png")
        self.assertIn("ఏమైంది స్వామీ?", manifest["dialogue_script"])
        self.assertIn("గిన్నెలు నీట్‌గా", manifest["dialogue_script"])
        self.assertEqual(manifest["planned_scene_seconds"], 10)

    def test_voice_override_by_speaker(self):
        manifest = build_story_render_manifest(
            self.valid_plan(),
            speaker_voices={"Yamudu": "Shruti (స్త్రీ వాయిస్)"},
        )
        self.assertIn("Yamudu|Shruti (స్త్రీ వాయిస్)|", manifest["dialogue_script"])
        self.assertIn(f"PJ Babu|{DEFAULT_VOICE}|", manifest["dialogue_script"])

    def test_rejects_unsupported_ratio(self):
        with self.assertRaises(StoryRenderPlanError):
            build_story_render_manifest(self.valid_plan(), aspect_ratio="1:1")

    def test_rejects_invalid_telugu_dialogue(self):
        plan = self.valid_plan()
        plan["scenes"][0]["dialogue_te"][0]["line"] = "What happened?"
        with self.assertRaises(StoryRenderPlanError):
            build_story_render_manifest(plan)


if __name__ == "__main__":
    unittest.main()
