"""The diary review screen's handling of guessed foods (needs the Qt test environment)."""

import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from calorie_tracker.bootstrap import build_services
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food
from calorie_tracker.presentation.dialogs.diary_csv_import_dialog import DiaryCsvReviewDialog
from calorie_tracker.presentation.main_window import MainWindow


class GuessReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.services = build_services(Path(self.temp.name) / "data" / "tracker.sqlite3")
        self.services.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))
        self.services.foods.save(Food("milk", "Milk", Nutrients(calories=Decimal("60"))))
        self.window = MainWindow(self.services)
        self.addCleanup(self.window.close)

    def dialog(self, text):
        table = self.services.diary_importer.read_text(text)
        preview = self.services.diary_importer.preview_table(table)
        dialog = DiaryCsvReviewDialog(self.services, "2026-09-30", preview, self.window)
        self.addCleanup(dialog.close)
        return dialog

    def test_a_confident_guess_is_preselected_flagged_and_counted(self):
        dialog = self.dialog("food_name,grams,meal\neggs,50,Breakfast\nOat,30,Lunch\n")
        self.assertIn("Ready with Oats", dialog.table.item(1, 4).text())
        self.assertIn("guessed", dialog.table.item(1, 4).text())
        self.assertIn("1 row use", dialog.summary_label.text().replace("rows", "row"))
        self.assertIn("Import 1 entry", dialog.import_button.text())
        dialog.import_button.click()
        entries = self.services.diary.entries_for_day("2026-09-30")
        self.assertEqual([entry.display_name for entry in entries], ["Oats"])

    def test_a_weak_suggestion_is_not_preselected_and_prefills_the_picker(self):
        dialog = self.dialog("food_name,grams,meal\nskim milk,200,Breakfast\n")
        self.assertIn("Did you mean 'Milk'", dialog.table.item(0, 4).text())
        self.assertNotIn("Ready", dialog.table.item(0, 4).text())
        row = dialog.preview.rows[0]
        searched = []

        def picker(picker_dialog):
            searched.append(picker_dialog.search_input.text())
            return QDialog.DialogCode.Rejected

        with patch("calorie_tracker.presentation.dialogs.add_entry_dialog.AddEntryDialog.exec", new=picker):
            dialog.choose_food(row)
        self.assertEqual(searched, ["Milk"])

    def test_choosing_a_food_yourself_confirms_the_guess(self):
        dialog = self.dialog("food_name,grams,meal\nOat,30,Lunch\n")
        row = dialog.preview.rows[0]
        self.assertTrue(dialog._is_guess_active(row))
        dialog.select_food(row, "oats")
        self.assertFalse(dialog._is_guess_active(row))
        self.assertNotIn("guessed", dialog.table.item(0, 4).text())


if __name__ == "__main__":
    unittest.main()
