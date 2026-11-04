import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gpu_worker.story_render_runner import (
    StoryRenderPipelineError,
    render_story_to_mp4,
    validate_render_manifest,
)


class StoryRenderRunnerTests(unittest.TestCase):
    def manifest(self):
        return {
            "schema_version": 1,
            "aspect_ratio": "9:16",
            "fps": 24,
            "dialogue_script": "",
            "render_jobs": [
                {
                    "start_seconds": 0,
                    "end_seconds": 2,
                    "frame_num": 49,
                    "prompt_en": "A cinematic 3D shot of PJ Babu",
                    "output_filename": "scene_01.mp4",
                    "aspect_ratio": "9:16",
                }
            ],
        }

    def test_manifest_validation(self):
        self.assertEqual(len(validate_render_manifest(self.manifest())), 1)

    def test_rejects_bad_frame_count(self):
        data = self.manifest()
        data["render_jobs"][0]["frame_num"] = 48
        with self.assertRaises(StoryRenderPipelineError):
            validate_render_manifest(data)

    def test_rejects_path_traversal_filename(self):
        data = self.manifest()
        data["render_jobs"][0]["output_filename"] = "../../outside.mp4"
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "wan"
            repo.mkdir()
            (repo / "generate.py").write_text("# mock")
            checkpoint = Path(tmp) / "ckpt"
            checkpoint.mkdir()
            with patch("gpu_worker.story_render_runner.run_ti2v_job") as render:
                render.return_value = Path(tmp) / "scene.mp4"
                with patch("gpu_worker.story_render_runner.shutil.copy2"):
                    # Path.basename is applied, so traversal cannot escape output_dir.
                    result = render_story_to_mp4(
                        data, wan_repo=str(repo), checkpoint_dir=str(checkpoint),
                        output_dir=str(Path(tmp) / "out")
                    )
            self.assertTrue(str(result).startswith(str(Path(tmp) / "out")))

    def test_rejects_overlapping_scenes(self):
        data = self.manifest()
        second = dict(data["render_jobs"][0])
        second.update({"start_seconds": 1, "end_seconds": 3, "frame_num": 49})
        data["render_jobs"].append(second)
        with self.assertRaises(StoryRenderPipelineError):
            validate_render_manifest(data)


if __name__ == "__main__":
    unittest.main()
