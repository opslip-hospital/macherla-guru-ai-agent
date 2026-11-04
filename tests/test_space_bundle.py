import tempfile
import unittest
from pathlib import Path

from gpu_worker.build_space_bundle import build_bundle


class SpaceBundleTests(unittest.TestCase):
    def test_builds_self_contained_gradio_space_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "app.py").write_text("from gradio_app import demo\n", encoding="utf-8")
            (source / "gradio_app.py").write_text("demo = None\n", encoding="utf-8")
            (source / "requirements.txt").write_text("gradio>=5,<6\n", encoding="utf-8")
            result = build_bundle(source, output)
            self.assertEqual(result, output.resolve())
            self.assertTrue((output / "app.py").is_file())
            self.assertTrue((output / "gradio_app.py").is_file())
            self.assertTrue((output / "requirements.txt").is_file())
            readme = (output / "README.md").read_text(encoding="utf-8")
            self.assertIn("sdk: gradio", readme)
            self.assertIn("app_file: app.py", readme)

    def test_rejects_missing_entrypoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "requirements.txt").write_text("gradio\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_bundle(root, root / "out")


if __name__ == "__main__":
    unittest.main()
