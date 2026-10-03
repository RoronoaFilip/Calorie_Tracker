import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from calorie_tracker import paths


class PathsTests(unittest.TestCase):
    def test_source_runs_keep_using_the_project_data_folder(self):
        self.assertFalse(paths.is_frozen())
        self.assertEqual(paths.default_database_path(), paths.project_root() / "data" / "calorie_tracker.sqlite3")
        self.assertTrue(paths.seed_csv_path().is_file())

    def test_frozen_build_uses_local_app_data_unless_a_data_folder_sits_next_to_the_exe(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "DailyPlate.exe"
            with patch.object(sys, "frozen", True, create=True), \
                    patch.object(sys, "executable", str(exe)), \
                    patch.object(sys, "_MEIPASS", folder, create=True), \
                    patch.dict("os.environ", {"LOCALAPPDATA": str(Path(folder) / "appdata")}):
                self.assertEqual(paths.resource_root(), Path(folder))
                self.assertEqual(
                    paths.default_database_path(),
                    Path(folder) / "appdata" / "DailyPlate" / "data" / "calorie_tracker.sqlite3",
                )
                (Path(folder) / "data").mkdir()
                self.assertEqual(
                    paths.default_database_path(), Path(folder).resolve() / "data" / "calorie_tracker.sqlite3"
                )


if __name__ == "__main__":
    unittest.main()
