import unittest

from gpu_worker.dialogue_audio import DialogueAudioError, parse_dialogue_script


class DialogueAudioTests(unittest.TestCase):
    def test_parses_two_telugu_speakers(self):
        lines = parse_dialogue_script(
            "PJ Babu|Mohan (పురుష వాయిస్)|ఏమైంది స్వామీ?\n"
            "యముడు|Shruti (స్త్రీ వాయిస్)|నన్ను కొట్టిందిరా!"
        )
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["speaker"], "PJ Babu")
        self.assertEqual(lines[1]["voice"], "Shruti (స్త్రీ వాయిస్)")

    def test_rejects_bad_format(self):
        with self.assertRaises(DialogueAudioError):
            parse_dialogue_script("ఏమైంది స్వామీ?")

    def test_rejects_non_telugu_dialogue(self):
        with self.assertRaises(DialogueAudioError):
            parse_dialogue_script("PJ|Mohan (పురుష వాయిస్)|Hello")

    def test_rejects_unknown_voice(self):
        with self.assertRaises(DialogueAudioError):
            parse_dialogue_script("PJ|Unknown|నమస్కారం")

    def test_rejects_empty_script(self):
        with self.assertRaises(DialogueAudioError):
            parse_dialogue_script("")


if __name__ == "__main__":
    unittest.main()
