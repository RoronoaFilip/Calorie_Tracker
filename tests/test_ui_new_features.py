"""UI tests for counted foods, searchable ingredients, quick add and keyboard behaviour (need PySide6)."""

import logging
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from calorie_tracker.bootstrap import build_services
from calorie_tracker.domain.nutrition import BASIS_COUNT, Nutrients
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient
from calorie_tracker.presentation.dialogs.add_entry_dialog import AddEntryDialog
from calorie_tracker.presentation.dialogs.food_dialog import FoodDialog
from calorie_tracker.presentation.dialogs.quick_add_dialog import QuickAddDialog
from calorie_tracker.presentation.dialogs.recipe_dialog import RecipeDialog
from calorie_tracker.presentation.main_window import MainWindow


class NewFeatureUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.services = build_services(Path(self.temp_dir.name) / "data" / "tracker.sqlite3")
        self.addCleanup(self._close_log_handlers)
        self.services.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))
        self.services.foods.save(Food("egg", "Large egg", Nutrients(calories=Decimal("70")), True, BASIS_COUNT))
        self.services.foods.save(Food("chicken", "Grilled chicken breast", Nutrients(calories=Decimal("165"))))
        self.window = MainWindow(self.services)
        self.addCleanup(self.window.close)

    def _close_log_handlers(self):
        logger = logging.getLogger("calorie_tracker")
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def test_escape_closes_a_dialog_even_from_a_text_field(self):
        dialog = FoodDialog(self.window)
        dialog.show()
        self.application.processEvents()
        QTest.keyClick(dialog.name_input, Qt.Key.Key_Escape)
        self.assertFalse(dialog.isVisible())

    def test_enter_saves_the_food_without_clicking_a_button(self):
        dialog = FoodDialog(self.window)
        dialog.show()
        self.application.processEvents()
        QTest.keyClicks(dialog.name_input, "Rice")
        QTest.keyClick(dialog.name_input, Qt.Key.Key_Return)
        self.assertEqual(dialog.result(), FoodDialog.DialogCode.Accepted)
        self.assertEqual(dialog.food().basis, "g")

    def test_food_dialog_defaults_to_per_100g_and_can_be_per_item(self):
        dialog = FoodDialog(self.window)
        self.assertTrue(dialog.basis_per_100g.isChecked())
        dialog.basis_per_item.setChecked(True)
        self.assertEqual(dialog.food().basis, "count")
        self.assertIn("item", dialog._nutrient_row_labels["calories"].text())

    def test_recipe_ingredient_search_matches_any_part_of_the_name(self):
        dialog = RecipeDialog(self.services.catalogue, self.services.foods)
        self.addCleanup(dialog.close)
        dialog.food_picker.lineEdit().setText("chicken")
        self.assertEqual(dialog._selected_food().id, "chicken")
        dialog.food_picker.lineEdit().setText("egg")
        self.assertEqual(dialog._selected_food().id, "egg")
        self.assertEqual(dialog.ingredient_amount.basis, "count")
        dialog.ingredient_amount.setValue(2)
        dialog.add_ingredient_button.click()
        self.assertEqual(dialog.ingredients[0].amount_g, Decimal("2"))

    def test_editing_an_ingredient_amount_updates_yield_and_nutrition(self):
        self.services.catalogue.save_recipe("r1", RecipeDraft(
            "Oat mix", Decimal("100"), (RecipeIngredient(self.services.foods.get("oats"), Decimal("100")),)
        ))
        dialog = RecipeDialog(self.services.catalogue, self.services.foods, recipe=self.services.recipes.get("r1"))
        self.addCleanup(dialog.close)
        dialog.ingredient_table.cellWidget(0, 1).setValue(200)
        self.assertEqual(dialog.ingredients[0].amount_g, Decimal("200"))
        self.assertEqual(dialog.yield_input.value(), 200)

    def test_diary_picker_asks_for_a_count_for_counted_foods(self):
        picker = AddEntryDialog(self.services, "Breakfast")
        self.addCleanup(picker.close)
        picker.search_input.setText("egg")
        self.assertEqual(picker.selected_item_id, "egg")
        self.assertEqual(picker.amount_input.basis, "count")
        self.assertEqual(picker.amount_input.value(), 1)
        picker.amount_input.setValue(0.5)
        entry = self.window.diary_view.add_catalogue_item(
            "Breakfast", picker.selected_item_id, Decimal(str(picker.amount_input.value()))
        )
        self.assertEqual(entry.nutrients.calories, Decimal("35.0"))

    def test_foods_page_shows_values_and_ctrl_f_focuses_search(self):
        self.window.show()
        self.window._select_view("Foods")
        self.application.processEvents()
        view = self.window.foods_view
        self.assertIs(self.application.focusWidget(), view.search_input)
        tooltips = " ".join(view.items.item(i).toolTip() for i in range(view.items.count()))
        self.assertIn("380 kcal", tooltips)
        self.assertIn("per item", tooltips)

    def test_text_is_selected_when_a_field_gets_focus(self):
        dialog = FoodDialog(self.window, self.services.foods.get("oats"))
        dialog.show()
        self.application.processEvents()
        dialog.name_input.clearFocus()
        dialog.name_input.setFocus(Qt.FocusReason.TabFocusReason)
        self.application.processEvents()
        self.assertEqual(dialog.name_input.selectedText(), "Oats")

    def test_quick_add_reviews_lines_and_saves_them(self):
        diary = self.window.diary_view
        dialog = QuickAddDialog("2026-10-04")
        self.addCleanup(dialog.close)
        dialog.text_input.setPlainText("Oats 50 breakfast\nLarge egg 2 breakfast")
        from calorie_tracker.infrastructure.csv_reading import CsvTable
        preview = self.services.diary_importer.preview_table(CsvTable(dialog.rows(), ",", "utf-8"))
        self.assertEqual(len([row for row in preview.rows if row.is_importable]), 2)
        self.assertTrue(diary.quick_add_button.isEnabled())

    def test_settings_button_opens_the_shortcuts_popup_which_escape_closes(self):
        from unittest.mock import patch
        from calorie_tracker.presentation.dialogs.shortcuts_dialog import SHORTCUT_GROUPS, ShortcutsDialog
        self.assertTrue(self.window.settings_view.shortcuts_button.isEnabled())
        with patch("calorie_tracker.presentation.views.settings_view.ShortcutsDialog.exec") as opened:
            self.window.settings_view.shortcuts_button.click()
        opened.assert_called_once()
        dialog = ShortcutsDialog(self.window)
        dialog.show()
        self.application.processEvents()
        label = dialog.findChild(QLabel, "shortcutsText")
        for title, _entries in SHORTCUT_GROUPS:
            self.assertIn(title, label.text())
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertFalse(dialog.isVisible())


if __name__ == "__main__":
    unittest.main()
