import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gpu_worker.wan_animate_adapter import (
    WanSetupError,
    build_wan_animate_commands,
    run_wan_animate_job,
)


class WanAnimateAdapterTests(unittest.TestCase):
    def make_setup(self, root):
        repo = root / "Wan2.2"
        (repo / "wan/modules/animate/preprocess").mkdir(parents=True)
        (repo / "generate.py").write_text("# placeholder", encoding="utf-8")
        (repo / "wan/modules/animate/preprocess/preprocess_data.py").write_text(
            "# placeholder", encoding="utf-8"
        )
        checkpoint = root / "Wan2.2-Animate-14B"
        (checkpoint / "process_checkpoint").mkdir(parents=True)
        video = root / "drive.mp4"
        video.write_bytes(b"video")
        image = root / "character.png"
        image.write_bytes(b"image")
        return repo, checkpoint, video, image

    def test_animation_command_has_official_flags_and_memory_offload(self):
        with tempfile.TemporaryDirectory() as temp:
            repo, checkpoint, video, image = self.make_setup(Path(temp))
            prep, generate = build_wan_animate_commands(
                wan_repo=str(repo), checkpoint_dir=str(checkpoint),
                video_path=str(video), reference_image=str(image),
                output_dir=str(Path(temp) / "out"),
            )
            self.assertIn("--retarget_flag", prep)
            self.assertIn("--use_flux", prep)
            self.assertIn("--task", generate)
            self.assertIn("animate-14B", generate)
            self.assertIn("--offload_model", generate)
            self.assertIn("True", generate)

    def test_replacement_adds_replacement_flags(self):
        with tempfile.TemporaryDirectory() as temp:
            repo, checkpoint, video, image = self.make_setup(Path(temp))
            prep, generate = build_wan_animate_commands(
                wan_repo=str(repo), checkpoint_dir=str(checkpoint),
                video_path=str(video), reference_image=str(image),
                output_dir=str(Path(temp) / "out"),
                mode="replace_character",
            )
            self.assertIn("--replace_flag", prep)
            self.assertIn("--use_relighting_lora", generate)

    def test_story_driven_mode_is_not_misrepresented_as_animate(self):
        with tempfile.TemporaryDirectory() as temp:
            repo, checkpoint, video, image = self.make_setup(Path(temp))
            with self.assertRaises(WanSetupError):
                build_wan_animate_commands(
                    wan_repo=str(repo), checkpoint_dir=str(checkpoint),
                    video_path=str(video), reference_image=str(image),
                    output_dir=str(Path(temp) / "out"),
                    mode="story_driven_new_scenes",
                )

    def test_missing_process_checkpoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            repo, checkpoint, video, image = self.make_setup(Path(temp))
            (checkpoint / "process_checkpoint").rmdir()
            with self.assertRaisesRegex(WanSetupError, "process_checkpoint"):
                build_wan_animate_commands(
                    wan_repo=str(repo), checkpoint_dir=str(checkpoint),
                    video_path=str(video), reference_image=str(image),
                    output_dir=str(Path(temp) / "out"),
                )

    def test_runner_verifies_mp4_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo, checkpoint, video, image = self.make_setup(root)
            out = root / "out"
            out.mkdir()
            mp4 = out / "wan_animate_output.mp4"
            mp4.write_bytes(b"\x00\x00\x00\x18ftypisom")
            with patch("gpu_worker.wan_animate_adapter.subprocess.run") as mocked:
                result = run_wan_animate_job(
                    wan_repo=str(repo), checkpoint_dir=str(checkpoint),
                    video_path=str(video), reference_image=str(image),
                    output_dir=str(out),
                )
            self.assertEqual(result, mp4)
            self.assertEqual(mocked.call_count, 2)
            self.assertTrue(all(call.kwargs["check"] for call in mocked.call_args_list))


if __name__ == "__main__":
    unittest.main()
