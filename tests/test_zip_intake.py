import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from calorie_tracker.infrastructure import zip_intake
from calorie_tracker.infrastructure.zip_intake import ZipIntakeError, extract_zip

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def make_zip(directory: Path, members: dict[str, bytes], name: str = "export.zip") -> Path:
    path = directory / name
    with zipfile.ZipFile(path, "w") as archive:
        for member, data in members.items():
            archive.writestr(member, data)
    return path


class ExtractZipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / "work"

    def origins(self, result):
        return sorted(item.origin.split("/", 1)[1] for item in result)

    def test_root_files_only(self):
        archive = make_zip(self.root, {"foods.csv": b"a", "a.jpg": JPEG, "notes.txt": b"x"})
        self.assertEqual(self.origins(extract_zip(archive, self.work)), ["a.jpg", "foods.csv"])

    def test_one_folder_only(self):
        archive = make_zip(self.root, {"data/foods.csv": b"a", "data/a.jpg": JPEG})
        self.assertEqual(self.origins(extract_zip(archive, self.work)), ["data/a.jpg", "data/foods.csv"])

    def test_root_files_and_one_folder_are_all_taken(self):
        archive = make_zip(self.root, {"foods.csv": b"a", "photos/a.jpg": JPEG, "photos/b.png": JPEG})
        self.assertEqual(
            self.origins(extract_zip(archive, self.work)), ["foods.csv", "photos/a.jpg", "photos/b.png"]
        )

    def test_folders_inside_the_single_folder_are_ignored(self):
        archive = make_zip(self.root, {"photos/a.jpg": JPEG, "photos/old/b.jpg": JPEG, "photos/old/c.csv": b"x"})
        self.assertEqual(self.origins(extract_zip(archive, self.work)), ["photos/a.jpg"])

    def test_two_folders_are_an_error(self):
        archive = make_zip(self.root, {"a/foods.csv": b"a", "b/diary.csv": b"b"})
        with self.assertRaisesRegex(ZipIntakeError, "more than one folder"):
            extract_zip(archive, self.work)

    def test_no_csv_or_photos_is_an_error(self):
        archive = make_zip(self.root, {"readme.txt": b"hello"})
        with self.assertRaisesRegex(ZipIntakeError, "no CSV files or photos"):
            extract_zip(archive, self.work)

    def test_mac_junk_does_not_count_as_a_folder(self):
        archive = make_zip(self.root, {
            "export/foods.csv": b"a", "__MACOSX/export/._foods.csv": b"junk", ".DS_Store": b"junk",
            "export/.hidden.csv": b"junk",
        })
        self.assertEqual(self.origins(extract_zip(archive, self.work)), ["export/foods.csv"])

    def test_unsafe_member_names_are_refused_and_nothing_escapes(self):
        for hostile in ("../evil.csv", "/abs.csv", "C:/win.csv", "ok/../../evil.csv"):
            with self.subTest(name=hostile):
                archive = make_zip(self.root, {hostile: b"x"}, name="hostile.zip")
                with self.assertRaisesRegex(ZipIntakeError, "unsafe"):
                    extract_zip(archive, self.work)
        self.assertFalse((self.root / "evil.csv").exists())

    def test_same_file_name_twice_keeps_both(self):
        archive = make_zip(self.root, {"foods.csv": b"root", "data/foods.csv": b"folder"})
        result = extract_zip(archive, self.work)
        self.assertEqual(sorted(item.path.read_bytes() for item in result), [b"folder", b"root"])
        self.assertEqual(len({item.path for item in result}), 2)

    def test_limits(self):
        archive = make_zip(self.root, {"a.csv": b"1", "b.csv": b"2", "c.csv": b"3"})
        with self.assertRaisesRegex(ZipIntakeError, "limit"):
            extract_zip(archive, self.work, max_files=2)
        big = make_zip(self.root, {"big.csv": b"0" * 4096}, name="big.zip")
        with self.assertRaisesRegex(ZipIntakeError, "too large"):
            extract_zip(big, self.work, max_total_bytes=1024)

    def test_declared_sizes_that_lie_are_caught_while_copying(self):
        big = make_zip(self.root, {"big.csv": b"0" * 4096}, name="big.zip")
        with mock.patch.object(zip_intake, "_declared_size", lambda info: 0):
            with self.assertRaisesRegex(ZipIntakeError, "too large"):
                extract_zip(big, self.work, max_total_bytes=1024)

    def test_not_a_zip(self):
        fake = self.root / "fake.zip"
        fake.write_bytes(b"this is not a zip")
        with self.assertRaisesRegex(ZipIntakeError, "not a readable zip"):
            extract_zip(fake, self.work)


if __name__ == "__main__":
    unittest.main()
