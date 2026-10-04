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

    def test_quick_add_table_builds_csv_rows_from_the_inputs(self):
        dialog = QuickAddDialog(self.services, "2026-10-04")
        self.addCleanup(dialog.close)
        self.assertFalse(dialog.review_button.isEnabled())
        dialog.food_combo(0).lineEdit().setText("Oats")
        dialog.amount_input(0).setValue(50)
        dialog.meal_combo(0).setCurrentText("Lunch")
        dialog.food_combo(1).lineEdit().setText("Large egg")
        self.assertEqual(dialog.amount_input(1).basis, "count")  # counted food: the amount is a number of items
        dialog.amount_input(1).setValue(0.5)
        self.assertTrue(dialog.review_button.isEnabled())
        self.assertEqual(dialog.rows(), [
            ["food_name", "grams_eaten", "meal"], ["Oats", "50", "Lunch"], ["Large egg", "0.5", dialog.meal_combo(1).currentText()],
        ])
        completer = dialog.food_combo(0).completer()
        self.assertEqual(completer.filterMode(), Qt.MatchFlag.MatchContains)

    def test_quick_add_enter_moves_through_the_row_and_adds_rows(self):
        dialog = QuickAddDialog(self.services, "2026-10-04")
        dialog.show()
        self.application.processEvents()
        start = dialog.row_count()
        dialog.food_combo(0).lineEdit().setText("Oats")
        dialog.handle_enter(dialog.food_combo(0).lineEdit())
        self.assertTrue(dialog.amount_input(0).lineEdit().hasFocus() or dialog.amount_input(0).hasFocus())
        last = start - 1
        dialog.food_combo(last).lineEdit().setText("Oats")
        dialog.handle_enter(dialog.amount_input(last).lineEdit())
        self.assertEqual(dialog.row_count(), start + 1)
        dialog.close()

    def test_quick_add_ctrl_plus_adds_a_row(self):
        dialog = QuickAddDialog(self.services, "2026-10-04")
        dialog.show()
        self.application.processEvents()
        start = dialog.row_count()
        QTest.keyClick(dialog.food_combo(0).lineEdit(), Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(dialog.row_count(), start + 1)
        dialog.close()

    def test_quick_add_shift_enter_deletes_the_current_row_and_ctrl_enter_submits(self):
        dialog = QuickAddDialog(self.services, "2026-10-04")
        dialog.show()
        self.application.processEvents()
        start = dialog.row_count()
        dialog.food_combo(1).lineEdit().setText("Oats")
        dialog.food_combo(1).setFocus()
        self.application.processEvents()
        QTest.keyClick(dialog.food_combo(1).lineEdit(), Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(dialog.row_count(), start - 1)
        self.assertEqual(dialog.entries(), [])
        dialog.food_combo(0).lineEdit().setText("Oats")
        QTest.keyClick(dialog.food_combo(0).lineEdit(), Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(dialog.result(), QuickAddDialog.DialogCode.Accepted)

    def test_escape_still_works_from_a_widget_placed_in_a_table_cell(self):
        dialog = QuickAddDialog(self.services, "2026-10-04")
        dialog.show()
        self.application.processEvents()
        QTest.keyClick(dialog.food_combo(0).lineEdit(), Qt.Key.Key_Escape)
        self.assertFalse(dialog.isVisible())

    def test_help_page_lists_the_shortcuts_and_f1_opens_it(self):
        from calorie_tracker.presentation.shortcuts_content import SHORTCUT_GROUPS
        self.window.show()
        self.assertEqual(self.window._help_shortcut.key().toString(), "F1")
        self.window._help_shortcut.activated.emit()  # what pressing F1 does
        self.application.processEvents()
        self.assertIs(self.window._stack.currentWidget(), self.window.help_view)
        for title, _entries in SHORTCUT_GROUPS:
            self.assertIn(title, self.window.help_view.shortcuts_label.text())

    def test_navigation_has_manage_data_above_settings_and_help_below_it(self):
        keys = [key for key, _icon, _tip in self.window.NAV_ITEMS]
        self.assertEqual(keys, ["Diary", "Calendar", "Foods", "Data", "Settings", "Help"])
        self.assertEqual(self.window._nav_buttons["Data"].text(), "Manage your data")
        self.assertFalse(self.window._nav_buttons["Data"].icon().isNull())
        self.assertFalse(self.window._nav_buttons["Help"].icon().isNull())
        self.window._select_view("Data")
        self.assertIs(self.window._stack.currentWidget(), self.window.data_view)
        # the backup/export cards moved off the Settings page
        self.assertFalse(hasattr(self.window.settings_view, "export_foods_button"))
        self.assertTrue(hasattr(self.window.data_view, "export_foods_button"))

    def test_new_navigation_entries_use_the_same_style_as_the_old_ones(self):
        sheet = self.window.styleSheet()
        self.assertIn('QPushButton[navButton="true"]:checked', sheet)
        for key, button in self.window._nav_buttons.items():
            self.assertTrue(button.property("navButton"), key)

    def test_settings_autosave_without_a_button_and_empty_means_not_set(self):
        settings = self.window.settings_view
        self.assertFalse(any(button.text() == "Save targets" for button in settings.findChildren(type(self.window._nav_buttons["Data"]))))
        settings.target_inputs["calories"].setText("2000")
        settings.drift_low_inputs["calories"].setText("85")
        settings.drift_high_inputs["calories"].setText("110")
        settings._save_timer.timeout.emit()  # what the 400 ms timer does
        self.assertEqual(self.services.settings.get_json("daily_targets"), {"calories": 2000.0})
        self.assertEqual(self.services.settings.get_json("target_drift"), {"calories": [85, 110]})
        settings.target_inputs["calories"].setText("")
        settings._save_timer.timeout.emit()
        self.assertEqual(self.services.settings.get_json("daily_targets"), {})
        self.assertIn("Acceptable drift", settings.findChild(QLabel, "driftExplanation").text())

    def test_percent_is_green_only_inside_the_acceptable_drift(self):
        settings = self.window.settings_view
        settings.set_target("calories", 200)
        settings.save_targets()
        self.services.diary.add_item("2026-10-01", "Breakfast", "oats", Decimal("50"))  # 190 kcal = 95%
        diary = self.window.diary_view
        diary.set_date("2026-10-01")
        label = diary.macro_percents["calories"]
        self.assertEqual(label.text(), "95%")
        self.assertIn("#b23b45", label.styleSheet())  # default: only 100% is green
        settings.drift_low_inputs["calories"].setText("90")
        settings.drift_high_inputs["calories"].setText("110")
        settings.save_targets()
        self.assertIn("#2f7a4d", label.styleSheet())

    def test_diary_shows_percent_of_target_which_can_exceed_100(self):
        self.window.settings_view.set_target("calories", 100)
        self.window.settings_view.save_targets()
        self.services.diary.add_item("2026-10-01", "Breakfast", "oats", Decimal("50"))  # 190 kcal
        self.window.diary_view.set_date("2026-10-01")
        self.assertEqual(self.window.diary_view.macro_percents["calories"].text(), "190%")
        self.assertEqual(self.window.diary_view.macro_percents["protein"].text(), "")  # no protein target

    def test_calendar_dims_other_months_but_keeps_them_clickable_and_headers_not(self):
        from PySide6.QtCore import QDate
        from calorie_tracker.presentation.views.calendar_view import OTHER_MONTH_BACKGROUND, OTHER_MONTH_OPACITY
        calendar = self.window.calendar_view.calendar
        calendar.setCurrentPage(2026, 10)  # 1 October 2026 is a Thursday
        self.window.calendar_view.show()
        self.application.processEvents()
        self.assertFalse(calendar._in_shown_month(QDate(2026, 9, 30)))
        self.assertTrue(calendar._in_shown_month(QDate(2026, 10, 1)))
        view = calendar._day_grid
        # The Monday before 1 October is 28 September: a real, clickable date, drawn dimmed.
        first_row_monday = view.visualRect(view.model().index(1, 1)).center()
        self.assertEqual(calendar._date_at(first_row_monday), QDate(2026, 9, 28))
        header_cell = view.visualRect(view.model().index(0, 1)).center()
        week_number = view.visualRect(view.model().index(1, 0)).center()
        self.assertIsNone(calendar._date_at(header_cell))  # weekday names are not dates
        self.assertIsNone(calendar._date_at(week_number))  # neither are week numbers
        self.assertLess(OTHER_MONTH_OPACITY, 1)
        self.assertNotEqual(OTHER_MONTH_BACKGROUND, "#a5b8d8")  # a different shade than the headers
        from calorie_tracker.presentation.views.calendar_view import HEADER_BACKGROUND
        self.assertEqual(calendar.headerTextFormat().background().color().name(), HEADER_BACKGROUND)

    def test_foods_list_loads_pages_filters_and_restores_archived_recipes(self):
        for number in range(40):
            self.services.foods.save(Food(f"x{number:02d}", f"Zed {number:02d}", Nutrients(calories=Decimal(number))))
        view = self.window.foods_view
        self.window.show()
        view.refresh()
        self.application.processEvents()
        loaded = view.items.count()
        self.assertGreaterEqual(loaded, 15)
        self.assertLess(loaded, 43)  # not everything at once
        bar = view.items.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.application.processEvents()
        self.assertGreater(view.items.count(), loaded)
        view.kind_filter.setCurrentIndex(view.kind_filter.findData("recipe"))
        self.assertEqual(view.items.count(), 0)  # no recipes yet
        view.kind_filter.setCurrentIndex(0)
        self.services.catalogue.save_recipe("r1", RecipeDraft("Zed bowl", Decimal("100"), (
            RecipeIngredient(self.services.foods.get("oats"), Decimal("100")),
        )))
        self.services.recipes.archive("r1")
        view.archived_button.setChecked(True)
        self.assertEqual(view.items.count(), 1)
        view._restore_item("recipe", "r1")  # unchanged ingredients: restored straight away
        self.assertIsNotNone(self.services.recipes.get("r1"))

    def test_quick_add_raw_input_starts_with_only_the_header_and_feeds_the_import(self):
        dialog = QuickAddDialog(self.services, "2026-10-04")
        self.addCleanup(dialog.close)
        dialog.raw_toggle.setChecked(True)
        self.assertEqual(dialog.raw_input.toPlainText().strip(), "food_name,amount/count,meal")
        self.assertFalse(dialog.review_button.isEnabled())
        dialog.raw_input.setPlainText("food_name,amount/count,meal\nOats,50,Lunch\nLarge egg,0.5,Dinner\n")
        self.assertTrue(dialog.review_button.isEnabled())
        preview = self.services.diary_importer.preview_table(dialog.csv_table())
        self.assertTrue(all(row.is_importable for row in preview.rows))
        self.assertEqual(preview.rows[1].basis, "count")

    def test_settings_and_data_pages_scroll_instead_of_squeezing_their_cards(self):
        self.window.resize(1040, 680)
        self.window.show()
        for page, view in (("Settings", self.window.settings_view), ("Data", self.window.data_view)):
            self.window._select_view(page)
            view.scroll_area.setFixedHeight(120)  # smaller than the content, whatever the screen
            self.application.processEvents()
            self.assertTrue(view.scroll_area.widgetResizable(), page)
            self.assertGreater(view.scroll_area.verticalScrollBar().maximum(), 0, page)
        self.assertIn("QScrollBar::handle:vertical", self.window.styleSheet())

    def test_undo_button_sits_next_to_the_meal_add_button_and_its_line_winds_down(self):
        diary = self.window.diary_view
        self.window.show()
        entry = self.services.diary.add_item(diary.selected_date, "Lunch", "oats", Decimal("50"))
        diary.refresh()
        diary.delete_entry(entry.id, confirmed=True)
        row = diary.meal_add_rows["Lunch"]
        self.assertGreaterEqual(row.indexOf(diary.undo_button), 0)
        self.assertEqual(diary.meal_add_rows["Breakfast"].indexOf(diary.undo_button), -1)
        self.assertTrue(diary.undo_button.isVisible())
        self.assertEqual(diary.undo_button.countdown_fraction, 1.0)
        QTest.qWait(250)
        self.assertLess(diary.undo_button.countdown_fraction, 1.0)
        diary.undo_delete()
        self.assertFalse(diary.undo_button.isVisible())
        self.assertEqual(len(self.services.diary.entries_for_day(diary.selected_date)), 1)


if __name__ == "__main__":
    unittest.main()
