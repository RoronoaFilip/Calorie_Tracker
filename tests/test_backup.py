import logging
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from calorie_tracker.bootstrap import build_services
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food
from calorie_tracker.infrastructure.backup import BackupService
from calorie_tracker.infrastructure.database import Database
from calorie_tracker.infrastructure.repositories import FoodRepository


class BackupServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.services = build_services(self.root / "data" / "tracker.sqlite3")
        self.addCleanup(self._close_log_handlers)
        self.services.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))
        self.backups = BackupService(self.services.database, self.root / "data" / "backups")

    def _close_log_handlers(self):
        logger = logging.getLogger("calorie_tracker")
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def test_export_and_restore_preserve_database_and_make_safety_copy(self):
        export_path = self.root / "export folder" / "daily-plate.sqlite3"
        self.backups.export(export_path)
        self.services.foods.archive("oats")
        self.assertFalse(self.services.foods.search())

        safety_path = self.backups.restore(export_path)

        self.assertEqual(self.services.foods.get("oats").name, "Oats")
        self.assertTrue(safety_path.is_file())
        self.assertTrue(self.services.foods.get("oats").active)
        self.assertFalse(FoodRepository(Database(safety_path)).get("oats").active)

    def test_invalid_backup_is_rejected_without_changing_live_database(self):
        invalid = self.root / "invalid.sqlite3"
        invalid.write_text("not a database", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "valid Calorie Tracker backup"):
            self.backups.restore(invalid)

        self.assertIsNotNone(self.services.foods.get("oats"))
        self.assertEqual(list((self.root / "data" / "backups").glob("*")), [])


if __name__ == "__main__":
    unittest.main()
