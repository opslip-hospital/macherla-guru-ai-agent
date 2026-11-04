import tempfile
import unittest
from pathlib import Path

from gpu_worker.auto_director import make_comedy_edit_decision
from gpu_worker.comedy_edit import ComedyEditError


class AutoDirectorTests(unittest.TestCase):
    def test_scene_changes_become_punch_moments(self):
        plan = make_comedy_edit_decision([1.2, 3.5, 3.5, 22], duration=10)
        self.assertEqual(plan["scene_changes"], [1.2, 3.5])
        self.assertEqual(len(plan["punch_moments"]), 2)
        self.assertEqual(plan["punch_moments"][0]["action"], "punch_zoom")

    def test_out_of_range_duration_rejected(self):
        with self.assertRaises(ComedyEditError):
            make_comedy_edit_decision([], duration=25)


if __name__ == "__main__":
    unittest.main()
