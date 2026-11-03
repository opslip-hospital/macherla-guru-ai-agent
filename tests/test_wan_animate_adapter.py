import tempfile
import unittest
from pathlib import Path

from gpu_worker.wan_animate_adapter import (
    WanSetupError,
    build_wan_animate_commands,
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

    def test_animation_command_has_official_retarget_flags(self):
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


if __name__ == "__main__":
    unittest.main()
