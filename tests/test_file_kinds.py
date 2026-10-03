import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from calorie_tracker.infrastructure.file_kinds import CSV, IMAGE, UNSUPPORTED, classify_file


class ClassifyFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def _picture(self, name: str, fmt: str) -> Path:
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "white").save(buffer, fmt)
        path = self.directory / name
        path.write_bytes(buffer.getvalue())
        return path

    def test_common_photo_formats_are_images(self):
        for name, fmt in (("a.jpg", "JPEG"), ("b.png", "PNG"), ("c.webp", "WEBP"), ("d.bmp", "BMP"),
                          ("e.gif", "GIF"), ("f.tiff", "TIFF")):
            with self.subTest(name=name):
                self.assertEqual(classify_file(self._picture(name, fmt)), IMAGE)

    def test_content_wins_over_a_missing_or_wrong_extension(self):
        self.assertEqual(classify_file(self._picture("IMG_0001", "JPEG")), IMAGE)
        self.assertEqual(classify_file(self._picture("scan.csv", "PNG")), IMAGE)
        self.assertEqual(classify_file(self._picture("photo.dat", "PNG")), IMAGE)

    def test_csv_is_recognised_by_name_case_insensitively(self):
        path = self.directory / "DAY.CSV"
        path.write_text("food_name,grams\nOats,50\n")
        self.assertEqual(classify_file(path), CSV)

    def test_other_files_and_missing_files_are_unsupported(self):
        text = self.directory / "notes.txt"
        text.write_text("hello")
        self.assertEqual(classify_file(text), UNSUPPORTED)
        self.assertEqual(classify_file(self.directory / "gone.bin"), UNSUPPORTED)

    def test_unreadable_file_with_an_image_extension_is_still_treated_as_an_image(self):
        # e.g. HEIC from a phone: recognised as a photo so the reader can explain what it cannot open
        self.assertEqual(classify_file(self.directory / "missing.heic"), IMAGE)
        empty = self.directory / "empty.jpeg"
        empty.write_bytes(b"")
        self.assertEqual(classify_file(empty), IMAGE)


if __name__ == "__main__":
    unittest.main()
