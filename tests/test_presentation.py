import logging
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QRect, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QToolButton

from calorie_tracker.bootstrap import build_services
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient
from calorie_tracker.presentation.dialogs.recipe_dialog import RecipeDialog
from calorie_tracker.presentation.dialogs.diary_csv_import_dialog import DiaryCsvReviewDialog, MealAssignmentDialog
from calorie_tracker.presentation.dialogs.food_dialog import FoodDialog
from calorie_tracker.presentation.main_window import MainWindow
from calorie_tracker.presentation.views.diary_view import AddEntryDialog
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

    def test_recipe_ingredient_picker_shows_seeded_basic_foods_without_ice_creams(self):
        source = Path(__file__).resolve().parents[1] / "food_macros_seed.csv"
        self.services.importer.apply(self.services.importer.preview(source))
        dialog = RecipeDialog(self.services.catalogue, self.services.foods)

        names = [dialog.food_picker.itemText(index) for index in range(dialog.food_picker.count())]
        self.assertEqual(len(names), 26)
        self.assertIn("Chia seeds", names)
        self.assertNotIn("Cocoa Ice Cream", names)
        self.assertNotIn("Vanilla ice cream", names)
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
        seeded_services = build_services(database_path)
        self.assertEqual(len(seeded_services.foods.search()), 26)
        self.assertEqual(seeded_services.recipes.search(), ())

    def test_diary_view_shows_meals_totals_and_adds_food_automatically(self):
        diary = self.window.diary_view
        self.assertEqual(diary.date_picker.date().toString("yyyy-MM-dd"), diary.selected_date)
        diary.set_date("2026-10-01")
        self.assertEqual(diary.day_total_label.text(), "0 kcal")
        self.assertEqual(len(diary.meal_panels), 4)

        diary.add_catalogue_item("Breakfast", "oats", Decimal("50"))

        entries = self.services.diary.entries_for_day("2026-10-01")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].display_name, "Oats")
        self.assertIn("190", diary.day_total_label.text())

    def test_diary_import_button_and_review_dialog_import_to_selected_day(self):
        source = Path(self.temp_dir.name) / "day.csv"
        source.write_text(
            "food_name,grams_eaten (all meals)\nOats,50\nOats,25\n",
            encoding="utf-8",
        )
        diary = self.window.diary_view
        diary.set_date("2026-09-30")
        preexisting = self.services.diary.add_item("2026-09-30", "Lunch", "oats", Decimal("10"))
        button = diary.findChild(QPushButton, "importDiaryCsvButton")
        self.assertIsNotNone(button)
        self.assertEqual(button.accessibleName(), "Import diary entries from CSV")

        preview = self.services.diary_importer.preview(source)
        dialog = DiaryCsvReviewDialog(self.services, diary.selected_date, preview, diary)
        self.assertEqual(dialog.import_button.text(), "Import 0 entries")
        dialog.all_snacks_button.click()
        self.assertEqual(dialog.import_button.text(), "Import 2 entries")
        self.assertTrue(dialog.import_button.isEnabled())
        dialog.import_button.click()

        entries = self.services.diary.entries_for_day("2026-09-30")
        self.assertEqual(tuple(entry.meal for entry in entries), ("Lunch", "Snacks", "Snacks"))
        self.assertEqual(tuple(entry.amount_g for entry in entries), (Decimal("10"), Decimal("50"), Decimal("25")))
        self.assertEqual(entries[0], preexisting)
        self.assertEqual(diary.selected_date, "2026-09-30")

    def test_missing_meal_prompt_offers_one_click_per_meal(self):
        row = self.services.diary_importer.preview
        source = Path(self.temp_dir.name) / "day.csv"
        source.write_text("food_name,grams_eaten (all meals)\nOats,50\n", encoding="utf-8")
        unresolved = row(source).needs_meal_assignment[0]
        dialog = MealAssignmentDialog(unresolved, self.window)

        for meal in ("Breakfast", "Lunch", "Dinner", "Snacks"):
            button = dialog.findChild(QPushButton, f"assignMeal{meal}")
            self.assertIsNotNone(button)
        dialog.findChild(QPushButton, "assignMealDinner").click()

        self.assertEqual(dialog.meal, "Dinner")

    def test_diary_csv_review_shows_bad_rows_and_does_not_save_them(self):
        source = Path(self.temp_dir.name) / "day.csv"
        source.write_text(
            "food_name,grams_eaten (all meals),meal\nOats,50,Breakfast\nMissing,30,Lunch\n",
            encoding="utf-8",
        )
        preview = self.services.diary_importer.preview(source)
        dialog = DiaryCsvReviewDialog(self.services, "2026-09-30", preview, self.window)

        self.assertIn("1 row will be skipped", dialog.summary_label.text())
        self.assertIn("not found", dialog.table.item(1, 4).text().casefold())
        self.assertTrue(dialog.import_button.isEnabled())
        self.assertEqual(self.services.diary.entries_for_day("2026-09-30"), ())

    def test_diary_csv_meal_column_imports_each_row_into_its_meal(self):
        source = Path(self.temp_dir.name) / "day.csv"
        source.write_text(
            "food_name,grams_eaten (all meals),meal\nOats,50,Breakfast\nOats,25,Dinner\n",
            encoding="utf-8",
        )
        preview = self.services.diary_importer.preview(source)
        dialog = DiaryCsvReviewDialog(self.services, "2026-09-30", preview, self.window)

        self.assertEqual(dialog.table.item(0, 3).text(), "Breakfast")
        self.assertEqual(dialog.table.item(1, 3).text(), "Dinner")
        dialog.import_button.click()

        self.assertEqual(
            tuple(entry.meal for entry in self.services.diary.entries_for_day("2026-09-30")),
            ("Breakfast", "Dinner"),
        )

    def test_invalid_diary_csv_shows_expected_format_without_writing(self):
        source = Path(self.temp_dir.name) / "wrong.csv"
        source.write_text("name,amount\nOats,50\n", encoding="utf-8")

        with patch("calorie_tracker.presentation.views.diary_view.QMessageBox.critical") as critical:
            self.window.diary_view.import_diary_csv(str(source))

        self.assertIn("Expected header", critical.call_args.args[2])
        self.assertIn("Example row", critical.call_args.args[2])
        self.assertEqual(self.services.diary.entries_for_day(self.window.diary_view.selected_date), ())

    def test_invalid_catalogue_csv_shows_expected_format_without_writing(self):
        source = Path(self.temp_dir.name) / "wrong-foods.csv"
        source.write_text("name,calories\nOats,100\n", encoding="utf-8")

        with patch("calorie_tracker.presentation.views.foods_view.QMessageBox.critical") as critical:
            self.window.foods_view.import_csv(source)

        self.assertIn("Expected header columns", critical.call_args.args[2])
        self.assertEqual(self.services.foods.search(), (self.services.foods.get("oats"),))

    def test_diary_picker_places_recent_foods_above_search_results(self):
        self.services.diary.add_item("2026-10-01", "Breakfast", "oats", Decimal("40"))
        picker = AddEntryDialog(self.services, "Lunch")
        self.addCleanup(picker.close)

        self.assertEqual(picker.recent_results.count(), 1)
        self.assertEqual(picker.recent_results.item(0).data(256), "oats")
        self.assertGreater(picker.results.count(), 0)
        self.assertTrue(picker.add_button.isEnabled())

    def test_diary_entry_edit_save_cancel_repeat_delete_and_undo(self):
        entry = self.services.diary.add_item("2026-10-01", "Lunch", "oats", Decimal("100"))
        diary = self.window.diary_view
        diary.set_date("2026-10-01")
        diary.begin_edit(entry.id)
        diary.edit_amount_input.setValue(150)
        diary.cancel_edit()
        self.assertEqual(self.services.diary.entries_for_day("2026-10-01")[0].amount_g, Decimal("100"))

        diary.begin_edit(entry.id)
        diary.edit_amount_input.setValue(150)
        diary.save_edit()
        self.assertEqual(self.services.diary.entries_for_day("2026-10-01")[0].amount_g, Decimal("150"))

        diary.repeat_entry(entry.id)
        self.assertEqual(len(self.services.diary.entries_for_day("2026-10-01")), 2)
        diary.delete_entry(entry.id, confirmed=True)
        self.assertEqual(len(self.services.diary.entries_for_day("2026-10-01")), 1)
        diary.undo_delete()
        self.assertEqual(len(self.services.diary.entries_for_day("2026-10-01")), 2)

    def test_calendar_marks_populated_days_and_routes_selected_day_to_diary(self):
        self.services.diary.add_item("2026-10-01", "Breakfast", "oats", Decimal("100"))
        calendar_page = self.window.calendar_view
        calendar_page.set_month(2026, 10)

        self.assertIn("2026-10-01", calendar_page.populated_dates)
        calendar_page.select_date("2026-10-01")

        self.assertEqual(self.window.diary_view.selected_date, "2026-10-01")
        self.assertEqual(self.window._stack.currentIndex(), 0)

    def test_calendar_marks_populated_days_without_filling_day_cells(self):
        self.services.diary.add_item("2026-10-01", "Breakfast", "oats", Decimal("100"))
        self.window.calendar_view.set_month(2026, 10)

        format_for_day = self.window.calendar_view.calendar.dateTextFormat(QDate(2026, 10, 1))
        self.assertTrue(format_for_day.fontUnderline())
        self.assertEqual(format_for_day.background().style(), Qt.BrushStyle.NoBrush)
        self.assertFalse(self.window.calendar_view.calendar.isGridVisible())
        self.assertGreater(self.window.calendar_view.calendar.maximumSize().width(), 500)
        self.assertGreater(self.window.calendar_view.calendar.maximumSize().height(), 360)

    def test_calendar_draws_a_red_dot_on_today(self):
        calendar = self.window.calendar_view.calendar
        image = QImage(100, 80, QImage.Format.Format_ARGB32)
        image.fill(QColor("#f1f5fb"))
        painter = QPainter(image)
        calendar.paintCell(painter, QRect(0, 0, 100, 80), QDate.currentDate())
        painter.end()

        red_pixels = sum(
            1 for y in range(image.height()) for x in range(image.width())
            if image.pixelColor(x, y).red() > 180
            and image.pixelColor(x, y).green() < 120
            and image.pixelColor(x, y).blue() < 120
        )
        self.assertGreater(red_pixels, 0)

    def test_form_controls_use_dark_text_on_light_backgrounds(self):
        dialog = FoodDialog(self.window)
        dialog.show()
        self.application.processEvents()
        field = dialog.findChild(QLineEdit)

        self.assertEqual(field.palette().color(field.foregroundRole()), QColor("#243041"))
        self.assertEqual(field.palette().color(field.backgroundRole()), QColor("#f1f5fb"))
        self.assertIn("QDialog", self.window.styleSheet())
        dialog.close()

    def test_all_dropdown_and_spin_arrows_have_clear_indicators_and_light_popups(self):
        stylesheet = self.window.styleSheet()

        self.assertIn("QMenu { background: #f1f5fb; color: #243041;", stylesheet)
        self.assertIn("QComboBox::down-arrow", stylesheet)
        self.assertIn("QDateEdit::down-arrow", stylesheet)
        self.assertIn("QSpinBox::up-arrow", stylesheet)
        self.assertIn("QDoubleSpinBox::down-arrow", stylesheet)
        self.assertIn("chevron-down.svg", stylesheet)
        self.assertIn("chevron-up.svg", stylesheet)
        self.assertNotIn('image: url("file:///', stylesheet)
        popup_calendar = self.window.diary_view.date_picker.calendarWidget()
        self.assertEqual(
            popup_calendar.findChild(QToolButton, "qt_calendar_prevmonth").toolTip(), "Previous month"
        )
        self.assertEqual(
            popup_calendar.findChild(QToolButton, "qt_calendar_nextmonth").toolTip(), "Next month"
        )
        self.assertEqual(
            popup_calendar.findChild(QToolButton, "qt_calendar_monthbutton").toolTip(), "Choose month"
        )
        self.assertEqual(
            popup_calendar.findChild(QToolButton, "qt_calendar_yearbutton").toolTip(), "Choose year"
        )

    def test_day_and_calendar_navigation_arrows_use_visible_icons(self):
        for button in (
            self.window.diary_view.previous_button,
            self.window.diary_view.next_button,
            self.window.calendar_view.calendar.findChild(QToolButton, "qt_calendar_prevmonth"),
            self.window.calendar_view.calendar.findChild(QToolButton, "qt_calendar_nextmonth"),
        ):
            self.assertFalse(button.icon().isNull())
            self.assertEqual(button.text(), "")

    def test_diary_meal_cards_have_distinct_tinted_backgrounds(self):
        colors = {
            self.window.diary_view.meal_panels[meal].styleSheet()
            for meal in self.window.diary_view.meal_panels
        }
        self.assertEqual(len(colors), 4)
        self.assertTrue(all("background: #" in value for value in colors))

    def test_settings_save_optional_targets_and_diary_shows_target_progress(self):
        settings = self.window.settings_view
        settings.set_target("calories", 2000)
        settings.set_target("protein", 120)
        settings.save_targets()
        self.assertEqual(self.services.settings.get_json("daily_targets"), {
            "calories": 2000.0, "protein": 120.0,
        })

        self.services.diary.add_item("2026-10-01", "Breakfast", "oats", Decimal("100"))
        self.window.diary_view.set_date("2026-10-01")
        self.assertEqual(self.window.diary_view.macro_cards["calories"][1].value(), 19)

        settings.set_target("protein", 0)
        settings.save_targets()
        self.assertEqual(self.services.settings.get_json("daily_targets"), {"calories": 2000.0})

    def test_settings_restore_refreshes_open_views_after_safety_backup(self):
        backup_path = Path(self.temp_dir.name) / "saved.sqlite3"
        self.services.backup.export(backup_path)
        self.services.foods.archive("oats")
        self.assertFalse(self.services.foods.get("oats").active)

        safety_copy = self.window.settings_view.restore_backup(str(backup_path))

        self.assertTrue(safety_copy.is_file())
        self.assertTrue(self.services.foods.get("oats").active)
        self.assertEqual(self.window.foods_view.items.count(), 1)


if __name__ == "__main__":
    unittest.main()
