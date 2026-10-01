import importlib
import logging
import tempfile
import unittest
from pathlib import Path

from calorie_tracker.bootstrap import build_services
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food


class BootstrapTests(unittest.TestCase):
    def tearDown(self):
        self._close_log_handlers()

    @staticmethod
    def _close_log_handlers():
        logger = logging.getLogger("calorie_tracker")
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

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

    def test_first_launch_seeds_only_basic_foods_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                database_path = Path(temp_dir) / "data" / "calorie_tracker.sqlite3"
                source = Path(__file__).resolve().parents[1] / "food_macros_seed.csv"
                services = build_services(database_path, seed_source_path=source)

                self.assertEqual(len(services.foods.search()), 26)
                self.assertNotIn("Cocoa Ice Cream", [food.name for food in services.foods.search()])
                self.assertNotIn("Vanilla ice cream", [food.name for food in services.foods.search()])
                self.assertEqual(services.recipes.search(), ())
                self.assertTrue(services.settings.get_json("initial_food_seed_v1"))

                services.foods.save(Food("custom", "My food", Nutrients()))
                second_services = build_services(database_path, seed_source_path=source)

                self.assertEqual(len(second_services.foods.search()), 27)
                self.assertIsNotNone(second_services.foods.get("custom"))
            finally:
                self._close_log_handlers()


if __name__ == "__main__":
    unittest.main()
