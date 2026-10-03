import tempfile
import unittest
from pathlib import Path

from PIL import Image

from calorie_tracker.domain.products import BarcodeImageError
from calorie_tracker.infrastructure.barcode_reader import ZxingBarcodeReader


class ZxingBarcodeReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "photo.png"
        Image.new("RGB", (40, 30), "white").save(self.path)

    def test_returns_only_valid_barcodes_without_duplicates(self):
        reader = ZxingBarcodeReader(decode=lambda _picture: ["5449000000996", "5449000000997", "5 449000000996", "abc"])
        self.assertEqual(reader.read(self.path), ("5449000000996",))

    def test_tries_easier_versions_of_the_picture_when_the_original_fails(self):
        seen = []

        def decode(picture):
            seen.append(picture.mode)
            return ["4006381333931"] if picture.mode == "L" else []

        self.assertEqual(ZxingBarcodeReader(decode=decode).read(self.path), ("4006381333931",))
        self.assertEqual(seen[0], "RGB")
        self.assertIn("L", seen)

    def test_big_photos_are_also_tried_downscaled(self):
        big = Path(self.temp.name) / "big.png"
        Image.new("RGB", (3200, 2400), "white").save(big)
        sizes = []

        def decode(picture):
            sizes.append(picture.size)
            return []

        self.assertEqual(ZxingBarcodeReader(decode=decode).read(big), ())
        self.assertEqual(sizes[0], (3200, 2400))
        self.assertIn((1600, 1200), sizes)

    def test_no_barcode_gives_an_empty_result(self):
        self.assertEqual(ZxingBarcodeReader(decode=lambda _picture: []).read(self.path), ())

    def test_a_file_that_is_not_a_picture_raises_a_friendly_error(self):
        broken = Path(self.temp.name) / "broken.png"
        broken.write_bytes(b"this is not a picture")
        with self.assertRaises(BarcodeImageError) as caught:
            ZxingBarcodeReader(decode=lambda _picture: []).read(broken)
        self.assertIn("could not be opened as a picture", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
