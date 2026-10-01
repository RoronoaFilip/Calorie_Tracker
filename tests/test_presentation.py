import logging
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPushButton

from calorie_tracker.bootstrap import build_services
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient
from calorie_tracker.presentation.dialogs.recipe_dialog import RecipeDialog
from calorie_tracker.presentation.main_window import MainWindow
import app


class PresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.services = build_services(Path(self.temp_dir.name) / "data" / "tracker.sqlite3")
        self.addCleanup(self._close_log_handlers)
        self.services.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))
        self.window = MainWindow(self.services)
        self.addCleanup(self.window.close)

    def _close_log_handlers(self):
        logger = logging.getLogger("calorie_tracker")
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def test_navigation_has_four_labeled_accessible_buttons_and_switches_views(self):
        labels = ("Diary", "Calendar", "Foods", "Settings")
        for label in labels:
            button = self.window.findChild(QPushButton, f"nav{label}")
            self.assertIsNotNone(button)
            self.assertEqual(button.accessibleName(), label)
            self.assertTrue(button.toolTip())

        calendar = self.window.findChild(QPushButton, "navCalendar")
        calendar.click()
        self.assertTrue(calendar.isChecked())
        self.assertEqual(self.window._stack.currentIndex(), 1)

    def test_recipe_yield_warning_is_visible_without_blocking_valid_save(self):
        self.services.catalogue.save_recipe("recipe-1", RecipeDraft(
            "Oat mix", Decimal("100"), (RecipeIngredient(
                self.services.foods.get("oats"), Decimal("200")
            ),),
        ))
        dialog = RecipeDialog(
            self.services.catalogue, self.services.foods, recipe=self.services.recipes.get("recipe-1")
        )
        dialog.show()
        self.application.processEvents()

        self.assertTrue(dialog.warning_label.isVisible())
        self.assertIn("differs from", dialog.warning_label.text())
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.close()

    def test_invalid_recipe_inputs_show_field_error_and_disable_save(self):
        dialog = RecipeDialog(self.services.catalogue, self.services.foods)

        self.assertFalse(dialog.save_button.isEnabled())
        self.assertIn("recipe name", dialog.error_label.text().lower())
        self.assertIn("ingredient", dialog.error_label.text().lower())
        dialog.close()

    def test_documented_launcher_enters_and_exits_the_qt_event_loop(self):
        database_path = Path(self.temp_dir.name) / "launcher.sqlite3"
        with patch("calorie_tracker.bootstrap.default_database_path", return_value=database_path):
            QTimer.singleShot(0, self.application.quit)
            self.assertEqual(app.main(), 0)
        self.assertTrue(database_path.is_file())


if __name__ == "__main__":
    unittest.main()
