import tempfile
import unittest
from pathlib import Path

from gpu_worker.scene_stitch import SceneStitchError, build_normalize_command


class SceneStitchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scene = self.root / "scene.mp4"
        self.scene.write_bytes(b"fake mp4 bytes")

    def tearDown(self):
        self.temp.cleanup()

    def test_portrait_scene_normalizes_to_720x1280(self):
        command = build_normalize_command(
            "ffmpeg", str(self.scene), str(self.root / "out.mp4")
        )
        vf = command[command.index("-vf") + 1]
        self.assertIn("scale=720:1280", vf)
        self.assertIn("fps=24", vf)
        self.assertIn("-an", command)
        self.assertIn("libx264", command)

    def test_square_and_landscape_dimensions(self):
        square = build_normalize_command(
            "ffmpeg", str(self.scene), str(self.root / "square.mp4"),
            aspect_ratio="1:1", fps=30,
        )
        landscape = build_normalize_command(
            "ffmpeg", str(self.scene), str(self.root / "wide.mp4"),
            aspect_ratio="16:9",
        )
        self.assertIn("scale=720:720", square[square.index("-vf") + 1])
        self.assertIn("scale=1280:720", landscape[landscape.index("-vf") + 1])

    def test_rejects_invalid_aspect_and_fps(self):
        with self.assertRaises(SceneStitchError):
            build_normalize_command(
                "ffmpeg", str(self.scene), str(self.root / "out.mp4"),
                aspect_ratio="4:3",
            )
        with self.assertRaises(SceneStitchError):
            build_normalize_command(
                "ffmpeg", str(self.scene), str(self.root / "out.mp4"), fps=29,
            )

    def test_rejects_missing_scene(self):
        with self.assertRaises(SceneStitchError):
            build_normalize_command(
                "ffmpeg", str(self.root / "missing.mp4"), str(self.root / "out.mp4"),
            )


if __name__ == "__main__":
    unittest.main()
