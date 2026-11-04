import tempfile
import unittest
from pathlib import Path
import subprocess

from gpu_worker.comedy_edit import ComedyEditError, build_comedy_filter, render_comedy_edit


class ComedyEditTests(unittest.TestCase):
    def test_vertical_filter_has_punch_zoom_and_delivery_size(self):
        value = build_comedy_filter("9:16", "High")
        self.assertIn("720x1280", value)
        self.assertIn("zoompan", value)
        self.assertIn("eq=contrast", value)

    def test_landscape_and_square_sizes(self):
        self.assertIn("1280x720", build_comedy_filter("16:9", "Medium"))
        self.assertIn("720x720", build_comedy_filter("1:1", "Extreme"))

    def test_scene_aware_zoom_is_added(self):
        value = build_comedy_filter("9:16", "High", punch_times=[1.25, 3.0])
        self.assertIn("between(on,37,43)", value)
        self.assertIn("between(on,90,96)", value)

    def test_invalid_ratio_rejected(self):
        with self.assertRaises(ComedyEditError):
            build_comedy_filter("4:3", "High")

    def test_invalid_intensity_rejected(self):
        with self.assertRaises(ComedyEditError):
            build_comedy_filter("9:16", "Ultra")

    def test_real_ffmpeg_render_smoke(self):
        try:
            from gpu_worker.comedy_edit import _ffmpeg_path
            ffmpeg = _ffmpeg_path()
        except Exception as exc:
            self.skipTest(f"imageio-ffmpeg not installed: {exc}")
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.mp4"
            output = Path(temp) / "edited.mp4"
            made = subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24",
                 "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                 "-t", "1.5", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", str(source)],
                capture_output=True, text=True, timeout=90,
            )
            self.assertEqual(made.returncode, 0, made.stderr[-1000:])
            result = render_comedy_edit(str(source), str(output), max_duration=2)
            self.assertTrue(Path(result).is_file())
            self.assertGreater(Path(result).stat().st_size, 1024)


if __name__ == "__main__":
    unittest.main()
