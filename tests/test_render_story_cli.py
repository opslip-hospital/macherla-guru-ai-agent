import unittest
from unittest.mock import patch

from gpu_worker.render_story import build_parser, main


class RenderStoryCliTests(unittest.TestCase):
    def test_parser_accepts_manifest_and_output(self):
        args = build_parser().parse_args([
            "--manifest", "plan.json", "--output-dir", "out"
        ])
        self.assertEqual(args.manifest, "plan.json")
        self.assertEqual(args.output_dir, "out")

    def test_missing_model_paths_fails_without_starting_gpu(self):
        with patch.dict("os.environ", {}, clear=True):
            result = main(["--manifest", "does-not-need-to-exist.json"])
        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
