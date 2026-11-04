import tempfile
import unittest
import sys
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from gpu_worker.telugu_tts import (
    TELUGU_VOICES,
    TeluguTTSSetupError,
    synthesize_telugu_speech,
    validate_telugu_speech,
)


class TeluguTTSTests(unittest.TestCase):
    def test_telugu_male_voice_is_selected(self):
        text, voice = validate_telugu_speech(
            "గిన్నెలు నీట్‌గా తోమలేదని చీపురుతో కొట్టిందిరా!",
            "Mohan (పురుష వాయిస్)",
        )
        self.assertIn("గిన్నెలు", text)
        self.assertEqual(voice, "te-IN-MohanNeural")

    def test_telugu_female_voice_is_available(self):
        self.assertEqual(
            TELUGU_VOICES["Shruti (స్త్రీ వాయిస్)"],
            "te-IN-ShrutiNeural",
        )

    def test_rejects_non_telugu_text(self):
        with self.assertRaises(TeluguTTSSetupError):
            validate_telugu_speech("Hello world", "Mohan (పురుష వాయిస్)")

    def test_rejects_unknown_voice(self):
        with self.assertRaises(TeluguTTSSetupError):
            validate_telugu_speech("నమస్కారం", "Unknown")

    def test_rejects_long_dialogue(self):
        with self.assertRaises(TeluguTTSSetupError):
            validate_telugu_speech("అ" * 1501, "Mohan (పురుష వాయిస్)")

    def test_synthesis_saves_mp3_file(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "dialogue.mp3"

            async def fake_save(path):
                Path(path).write_bytes(b"x" * 500)

            class FakeCommunicate:
                def __init__(self, text, voice, rate):
                    self.text = text
                    self.voice = voice
                    self.rate = rate

                async def save(self, path):
                    await fake_save(path)

            fake_module = SimpleNamespace(Communicate=FakeCommunicate)
            with patch.dict(sys.modules, {"edge_tts": fake_module}):
                result = synthesize_telugu_speech(
                    text="నమస్కారం మావా",
                    voice="Mohan (పురుష వాయిస్)",
                    output_file=str(output),
                )
            self.assertTrue(result.is_file())
            self.assertGreater(result.stat().st_size, 256)


if __name__ == "__main__":
    unittest.main()
