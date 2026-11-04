import tempfile
import unittest
from pathlib import Path

from gpu_worker.video_mux import VideoMuxError, build_mux_command


class VideoMuxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.video = root / "scene.mp4"
        self.audio = root / "dialogue.wav"
        self.output = root / "final.mp4"
        self.video.write_bytes(b"video")
        self.audio.write_bytes(b"audio")

    def tearDown(self):
        self.temp.cleanup()

    def test_replaces_original_audio_by_default(self):
        command = build_mux_command(
            "ffmpeg", str(self.video), str(self.audio), str(self.output)
        )
        self.assertIn("0:v:0", command)
        self.assertIn("1:a:0", command)
        self.assertIn("-shortest", command)
        self.assertIn("copy", command)

    def test_mixes_original_audio_when_requested(self):
        command = build_mux_command(
            "ffmpeg", str(self.video), str(self.audio), str(self.output),
            keep_original_audio=True, original_volume=0.2, dialogue_volume=1.0,
        )
        graph = command[command.index("-filter_complex") + 1]
        self.assertIn("amix=inputs=2", graph)
        self.assertIn("volume=0.200", graph)
        self.assertIn("[aout]", command)

    def test_rejects_original_mix_when_source_is_silent(self):
        with self.assertRaises(VideoMuxError):
            build_mux_command(
                "ffmpeg", str(self.video), str(self.audio), str(self.output),
                keep_original_audio=True, source_has_audio=False,
            )

    def test_rejects_invalid_volume(self):
        with self.assertRaises(VideoMuxError):
            build_mux_command(
                "ffmpeg", str(self.video), str(self.audio), str(self.output),
                dialogue_volume=3,
            )

    def test_rejects_missing_video(self):
        with self.assertRaises(VideoMuxError):
            build_mux_command(
                "ffmpeg", str(self.output), str(self.audio), str(self.output),
            )


if __name__ == "__main__":
    unittest.main()
