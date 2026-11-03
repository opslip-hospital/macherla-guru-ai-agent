import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gpu_worker.ti2v_adapter import (
    TI2VSetupError,
    build_ti2v_command,
    run_ti2v_job,
)


class TI2VAdapterTests(unittest.TestCase):
    def setup_paths(self, root):
        repo = root / "Wan2.2"
        repo.mkdir()
        (repo / "generate.py").write_text("# placeholder", encoding="utf-8")
        checkpoint = root / "Wan2.2-TI2V-5B"
        checkpoint.mkdir()
        image = root / "pj-babu.png"
        image.write_bytes(b"image")
        return repo, checkpoint, image

    def test_builds_portrait_text_to_video_command(self):
        with tempfile.TemporaryDirectory() as temp:
            repo, checkpoint, _ = self.setup_paths(Path(temp))
            cmd = build_ti2v_command(
                wan_repo=str(repo), checkpoint_dir=str(checkpoint),
                prompt="A cinematic 3D village scene", output_file=str(Path(temp) / "scene.mp4"),
                aspect_ratio="9:16", frame_num=41,
            )
            self.assertIn("ti2v-5B", cmd)
            self.assertIn("704*1280", cmd)
            self.assertIn("--prompt", cmd)
            self.assertIn("--offload_model", cmd)
            self.assertNotIn("--image", cmd)

    def test_image_to_video_adds_reference_image(self):
        with tempfile.TemporaryDirectory() as temp:
            repo, checkpoint, image = self.setup_paths(Path(temp))
            cmd = build_ti2v_command(
                wan_repo=str(repo), checkpoint_dir=str(checkpoint),
                prompt="A character waves", output_file=str(Path(temp) / "scene.mp4"),
                reference_image=str(image),
            )
            self.assertIn("--image", cmd)
            self.assertIn(str(image.resolve()), cmd)

    def test_rejects_invalid_frame_count_and_ratio(self):
        with tempfile.TemporaryDirectory() as temp:
            repo, checkpoint, _ = self.setup_paths(Path(temp))
            args = dict(
                wan_repo=str(repo), checkpoint_dir=str(checkpoint),
                prompt="A scene", output_file=str(Path(temp) / "scene.mp4"),
            )
            with self.assertRaises(TI2VSetupError):
                build_ti2v_command(**args, frame_num=40)
            with self.assertRaises(TI2VSetupError):
                build_ti2v_command(**args, aspect_ratio="1:1")

    def test_runner_requires_valid_mp4(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo, checkpoint, _ = self.setup_paths(root)
            output = root / "scene.mp4"
            output.write_bytes(b"\x00\x00\x00\x18ftypisom")
            with patch("gpu_worker.ti2v_adapter.subprocess.run") as mocked:
                result = run_ti2v_job(
                    wan_repo=str(repo), checkpoint_dir=str(checkpoint),
                    prompt="A cinematic scene", output_file=str(output),
                )
            self.assertEqual(result, output)
            mocked.assert_called_once()
            self.assertTrue(mocked.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
