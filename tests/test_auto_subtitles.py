import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import patch

from gpu_worker.auto_subtitles import SubtitleError, transcribe_to_srt


class AutoSubtitleTests(unittest.TestCase):
    def test_creates_srt_with_timestamps_and_telugu_text(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.mp4"
            source.write_bytes(b"video")
            output = Path(temp) / "captions.srt"
            fake_model = SimpleNamespace(transcribe=lambda *a, **k: (
                iter([SimpleNamespace(start=0.2, end=1.4, text=" నమస్కారం మావా ")]), None
            ))
            fake_module = SimpleNamespace(WhisperModel=lambda *a, **k: fake_model)
            with patch.dict(sys.modules, {"faster_whisper": fake_module}):
                result = transcribe_to_srt(str(source), str(output), language="te")
            content = Path(result).read_text(encoding="utf-8")
            self.assertIn("00:00:00,200 --> 00:00:01,400", content)
            self.assertIn("నమస్కారం మావా", content)

    def test_rejects_missing_input(self):
        with self.assertRaises(SubtitleError):
            transcribe_to_srt("/missing/video.mp4", "/tmp/out.srt")

    def test_rejects_invalid_language(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "x.mp4"
            source.write_bytes(b"x")
            with self.assertRaises(SubtitleError):
                transcribe_to_srt(str(source), str(Path(temp) / "x.srt"), language="xx")


if __name__ == "__main__":
    unittest.main()
