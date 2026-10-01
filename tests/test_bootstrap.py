import importlib
import logging
import tempfile
import unittest
from pathlib import Path

from calorie_tracker.bootstrap import build_services


class BootstrapTests(unittest.TestCase):
    def test_build_services_creates_only_local_database_and_wires_empty_catalogue(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "data" / "calorie_tracker.sqlite3"
            try:
                services = build_services(database_path)
                self.assertTrue(database_path.is_file())
                self.assertEqual(services.foods.search(), ())
                self.assertEqual(services.recipes.search(), ())
            finally:
                logger = logging.getLogger("calorie_tracker")
                for handler in tuple(logger.handlers):
                    logger.removeHandler(handler)
                    handler.close()

    def test_importing_launcher_does_not_open_a_window_or_create_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            before = set(Path(temp_dir).iterdir())
            launcher = importlib.import_module("app")

            self.assertTrue(callable(launcher.main))
            self.assertEqual(set(Path(temp_dir).iterdir()), before)


if __name__ == "__main__":
    unittest.main()
