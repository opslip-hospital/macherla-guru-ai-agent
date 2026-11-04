import unittest

from gpu_worker.comedy_edit import ComedyEditError, build_comedy_filter


class ComedyEditTests(unittest.TestCase):
    def test_vertical_filter_has_punch_zoom_and_delivery_size(self):
        value = build_comedy_filter("9:16", "High")
        self.assertIn("720x1280", value)
        self.assertIn("zoompan", value)
        self.assertIn("eq=contrast", value)

    def test_landscape_and_square_sizes(self):
        self.assertIn("1280x720", build_comedy_filter("16:9", "Medium"))
        self.assertIn("720x720", build_comedy_filter("1:1", "Extreme"))

    def test_invalid_ratio_rejected(self):
        with self.assertRaises(ComedyEditError):
            build_comedy_filter("4:3", "High")

    def test_invalid_intensity_rejected(self):
        with self.assertRaises(ComedyEditError):
            build_comedy_filter("9:16", "Ultra")


if __name__ == "__main__":
    unittest.main()
