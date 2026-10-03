import logging
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QToolButton,
)

from calorie_tracker.bootstrap import build_services
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient
from calorie_tracker.presentation.dialogs.recipe_dialog import RecipeDialog
from calorie_tracker.presentation.dialogs.diary_csv_import_dialog import DiaryCsvReviewDialog, MealAssignmentDialog
from calorie_tracker.domain.diary import MealPortion
from calorie_tracker.presentation.control_styles import CLOSE_DIALOG_SHORTCUT, install_close_shortcut
from calorie_tracker.presentation.csv_drop import csv_paths
from calorie_tracker.presentation.dialogs.csv_import_help_dialog import CsvImportHelpDialog
from calorie_tracker.presentation.dialogs.food_csv_review_dialog import FoodCsvReviewDialog
from calorie_tracker.presentation.dialogs.food_dialog import FoodDialog
from calorie_tracker.presentation.dialogs.meal_split_dialog import MealSplitDialog
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

    def test_recipe_yield_and_per_100g_preview_follow_ingredient_totals(self):
        self.services.catalogue.save_recipe("recipe-1", RecipeDraft(
            "Oat mix", Decimal("100"), (RecipeIngredient(
                self.services.foods.get("oats"), Decimal("200")
            ),),
        ))
        self.services.foods.save(Food(
            "milk", "Milk", Nutrients(calories=Decimal("100"))
        ))
        dialog = RecipeDialog(
            self.services.catalogue, self.services.foods, recipe=self.services.recipes.get("recipe-1")
        )
        dialog.show()
        self.application.processEvents()

        self.assertTrue(dialog.yield_input.isReadOnly())
        self.assertEqual(dialog.yield_input.value(), 200)
        self.assertFalse(dialog.warning_label.isVisible())
        self.assertEqual(
            'Per 100g: 380.00 kcal · Protein 0.00g · Carbs 0.00g · Fat 0.00g · Fiber 0.00g',
            dialog.preview_label.text()
        )

        milk_index = dialog.food_picker.findData("milk")
        dialog.food_picker.setCurrentIndex(milk_index)
        dialog.ingredient_amount.setValue(100)
        dialog.add_ingredient_button.click()

        self.assertEqual(dialog.yield_input.value(), 300)
        self.assertIn("Per 100g: 286.67 kcal", dialog.preview_label.text())

        dialog.ingredient_table.cellWidget(1, 2).click()

        self.assertEqual(dialog.yield_input.value(), 200)
        self.assertIn("Per 100g: 380.00 kcal", dialog.preview_label.text())
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.close()

    def test_catalogue_archive_button_names_and_archives_its_food(self):
        view = self.window.foods_view
        item = next(
            view.items.item(index)
            for index in range(view.items.count())
            if view.items.item(index).data(Qt.ItemDataRole.UserRole) == ("food", "oats")
        )
        view.items.setCurrentItem(item)
        row = view.items.itemWidget(item)
        self.assertFalse(row.archive_button.isHidden())

        with patch("calorie_tracker.presentation.views.foods_view.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes) as confirm:
            row.archive_button.click()

        self.assertNotIn("oats", {food.id for food in self.services.foods.search()})
        self.assertIn("Oats", confirm.call_args.args[2])

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
        self.assertEqual(diary.day_total_label.text(), "0.00 kcal")
        self.assertEqual(len(diary.meal_panels), 4)

        diary.add_catalogue_item("Breakfast", "oats", Decimal("50"))

        entries = self.services.diary.entries_for_day("2026-10-01")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].display_name, "Oats")
        self.assertIn("190", diary.day_total_label.text())

    def test_diary_displays_fiber_in_daily_totals_and_entry_details(self):
        self.services.foods.save(Food(
            "oats", "Oats", Nutrients(calories=Decimal("380"), fiber=Decimal("2.5"))
        ))
        diary = self.window.diary_view
        entry = diary.add_catalogue_item("Breakfast", "oats", Decimal("50"))

        self.assertEqual(diary.macro_cards["fiber"][0].text(), "1.25 g")
        self.assertEqual(diary.findChild(QLabel, "subtotalBreakfast").text(), "190.00 kcal · Protein 0.00g · Carbs 0.00g · Fat 0.00g · Fiber 1.25g")
        details = diary._entry_widgets[entry.id].findChildren(QLabel)
        self.assertTrue(any("Fiber 1.25g" in label.text() for label in details))

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
        source.write_text("description,serving\nOats,50\n", encoding="utf-8")

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
        self.assertTrue(self.window.calendar_view.calendar.isGridVisible())
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

    def test_calendar_has_framed_hoverable_larger_days_without_tooltip(self):
        self.window._select_view("Calendar")
        self.window.show()
        self.application.processEvents()
        calendar = self.window.calendar_view.calendar
        table = calendar.findChild(QTableView)
        calendar.setCurrentPage(2026, 10)
        table.ensurePolished()

        self.assertTrue(calendar.isGridVisible())
        self.assertEqual(calendar.toolTip(), "")
        self.assertTrue(table.hasMouseTracking())
        self.assertEqual(table.font().pixelSize(), 16)
        self.assertIn("QCalendarWidget { background: #f1f5fb; border: 1px solid #c2cede;", self.window.styleSheet())
        target = QDate(2026, 10, 3)
        first_day = QDate(2026, 10, 1)
        offset = (first_day.dayOfWeek() - calendar.firstDayOfWeek().value + 7) % 7
        cell_number = target.day() - 1 + offset
        row = 1 + cell_number // 7
        column = table.model().columnCount() - 7 + cell_number % 7
        cell = table.model().index(row, column)
        QTest.mouseMove(table.viewport(), table.visualRect(cell).center())
        self.application.processEvents()
        self.assertEqual(
            calendar.dateTextFormat(target).background().color(), QColor("#cbd9ee")
        )

    def test_interactive_controls_use_pointing_hand_cursor(self):
        pointer = Qt.CursorShape.PointingHandCursor
        calendar_table = self.window.calendar_view.calendar.findChild(QAbstractItemView)
        recipe_dialog = RecipeDialog(self.services.catalogue, self.services.foods)
        self.addCleanup(recipe_dialog.close)

        for widget in (
            self.window.diary_view.previous_button,
            self.window.foods_view.add_food_button,
            self.window.diary_view.date_picker,
            recipe_dialog.food_picker,
            calendar_table,
            calendar_table.viewport(),
        ):
            widget.ensurePolished()
            self.assertEqual(widget.cursor().shape(), pointer, type(widget).__name__)

    def test_form_controls_use_dark_text_on_light_backgrounds(self):
        dialog = FoodDialog(self.window)
        dialog.show()
        self.application.processEvents()
        field = dialog.findChild(QLineEdit)

        self.assertEqual(field.palette().color(field.foregroundRole()), QColor("#243041"))
        self.assertEqual(field.palette().color(field.backgroundRole()), QColor("#f1f5fb"))
        self.assertIn("QDialog", self.window.styleSheet())
        dialog.close()

    def test_food_dialog_prefills_and_clears_import_correction_field(self):
        imported_food = Food(
            "csv-food", "Oats", Nutrients(protein=Decimal("5"), fiber=Decimal("3"))
        )
        dialog = FoodDialog(
            self.window,
            imported_food=imported_food,
            correction_fields=("calories",),
            correction_errors=("Row 6: invalid value in calories / 100g",),
        )
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.windowTitle(), "Correct imported food")
        self.assertEqual(dialog.name_input.text(), "Oats")
        self.assertEqual(dialog.nutrient_inputs["protein"].value(), 5)
        self.assertIn("calories", dialog.nutrient_inputs["calories"].accessibleDescription().casefold())
        self.assertEqual(dialog.nutrient_inputs["calories"].styleSheet(), "border: 1px solid #b53d48;")

        dialog.nutrient_inputs["calories"].setValue(120)
        dialog._validate_and_accept()

        self.assertEqual(dialog.result(), FoodDialog.DialogCode.Accepted)
        self.assertEqual(dialog.food().nutrients_per_100g.calories, Decimal("120"))

    def test_food_dialog_allows_zero_when_correcting_a_required_nutrient(self):
        dialog = FoodDialog(
            self.window,
            imported_food=Food("csv-zero", "Food with zero calories", Nutrients()),
            correction_fields=("calories",),
        )
        self.addCleanup(dialog.close)
        dialog.show()
        field = dialog.nutrient_inputs["calories"]
        field.lineEdit().selectAll()
        QTest.keyClicks(field.lineEdit(), "0")

        dialog._validate_and_accept()

        self.assertEqual(field.value(), 0)
        self.assertEqual(dialog.result(), FoodDialog.DialogCode.Accepted)

    def test_both_csv_import_buttons_show_schema_before_opening_file_picker(self):
        events = []

        def inspect_schema(dialog):
            schema = dialog.findChild(QLabel, "csvImportSchema")
            example = dialog.findChild(QLabel, "csvImportExample")
            self.assertIsNotNone(schema)
            self.assertIsNotNone(example)
            self.assertIn("food_name", schema.text())
            self.assertIn("Oats", example.text())
            events.append(("schema", schema.text()))
            return QDialog.DialogCode.Accepted

        def choose_file(*_args):
            events.append(("picker", ""))
            return "", ""

        with patch("PySide6.QtWidgets.QDialog.exec", new=inspect_schema), patch(
            "calorie_tracker.presentation.views.foods_view.QFileDialog.getOpenFileName",
            side_effect=choose_file,
        ), patch(
            "calorie_tracker.presentation.views.diary_view.QFileDialog.getOpenFileName",
            side_effect=choose_file,
        ):
            self.window.foods_view._choose_import()
            self.window.diary_view.choose_diary_csv()

        self.assertEqual([event[0] for event in events], ["schema", "picker", "schema", "picker"])

    def test_food_csv_import_saves_corrected_invalid_row_without_overwriting_existing_food(self):
        source = Path(self.temp_dir.name) / "correction.csv"
        source.write_text(
            "food_name,calories / 100g,protein / 100g,fat / 100g,carbohydrates / 100g,fiber / 100g\n"
            "Barley,invalid,5,4,20,3\n",
            encoding="utf-8",
        )
        opened_fields = []

        def correct(dialog):
            opened_fields.extend(dialog._correction_fields)
            self.assertEqual(dialog.name_input.text(), "Barley")
            dialog.nutrient_inputs["calories"].setValue(120)
            return FoodDialog.DialogCode.Accepted

        with patch(
            "calorie_tracker.presentation.views.foods_view.FoodCsvReviewDialog.exec",
            return_value=QDialog.DialogCode.Accepted,
        ), patch(
            "calorie_tracker.presentation.views.foods_view.FoodDialog.exec",
            new=correct,
        ):
            self.window.foods_view.import_csv(source)

        self.assertEqual(opened_fields, ["calories"])
        self.assertEqual(self.services.foods.search("Barley")[0].nutrients_per_100g.calories, Decimal("120"))
        self.assertEqual(self.services.foods.get("oats").nutrients_per_100g.calories, Decimal("380"))

    def test_corrected_food_csv_row_with_existing_name_is_not_saved(self):
        source = Path(self.temp_dir.name) / "conflict.csv"
        source.write_text(
            "food_name,calories / 100g,protein / 100g,fat / 100g,carbohydrates / 100g,fiber / 100g\n"
            "Oats,invalid,5,4,20,3\n",
            encoding="utf-8",
        )

        def correct(dialog):
            dialog.nutrient_inputs["calories"].setValue(120)
            return FoodDialog.DialogCode.Accepted

        with patch(
            "calorie_tracker.presentation.views.foods_view.FoodCsvReviewDialog.exec",
            return_value=QDialog.DialogCode.Accepted,
        ), patch(
            "calorie_tracker.presentation.views.foods_view.FoodDialog.exec",
            new=correct,
        ), patch(
            "calorie_tracker.presentation.views.foods_view.QMessageBox.warning",
        ) as warning:
            self.window.foods_view.import_csv(source)

        oats = self.services.foods.search("Oats")
        self.assertEqual(len(oats), 1)
        self.assertEqual(oats[0].nutrients_per_100g.calories, Decimal("380"))
        warning.assert_called_once()

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

    # ----- new behaviour -------------------------------------------------------------------

    def _write_diary_csv(self, text: str) -> Path:
        source = Path(self.temp_dir.name) / "day.csv"
        source.write_text(text, encoding="utf-8")
        return source

    def test_review_dialog_splits_one_row_between_meals_and_can_be_edited_again(self):
        source = self._write_diary_csv("food_name,grams eaten,meal\nOats,500,Lunch\n")
        preview = self.services.diary_importer.preview(source)
        dialog = DiaryCsvReviewDialog(self.services, "2026-09-30", preview, self.window)
        row = preview.rows[0]

        split = MealSplitDialog(row.food_name, row.amount_g, dialog.portions[row.source_row], self.window)
        split.amount_inputs["Lunch"].setValue(200)
        self.assertFalse(split.apply_button.isEnabled())  # 300 g still unplaced
        split.findChild(QPushButton, "splitRestDinner").click()
        self.assertEqual(split.amount_inputs["Dinner"].value(), 300)
        self.assertTrue(split.apply_button.isEnabled())
        split.apply_button.click()
        dialog.portions[row.source_row] = split.portions
        dialog._refresh_rows()

        self.assertEqual(dialog.table.item(0, 3).text(), "Lunch 200 g · Dinner 300 g")
        self.assertEqual(dialog.import_button.text(), "Import 2 entries")
        # editing again: switch the whole amount to Breakfast
        dialog.portions[row.source_row] = (MealPortion("Breakfast", row.amount_g),)
        dialog._refresh_rows()
        self.assertEqual(dialog.table.item(0, 3).text(), "Breakfast")
        self.assertEqual(dialog.import_button.text(), "Import 1 entry")

        dialog.portions[row.source_row] = (MealPortion("Lunch", Decimal("200")), MealPortion("Dinner", Decimal("300")))
        dialog._refresh_rows()
        dialog.import_button.click()
        entries = self.services.diary.entries_for_day("2026-09-30")
        self.assertEqual([(e.meal, e.amount_g) for e in entries], [("Lunch", Decimal("200")), ("Dinner", Decimal("300"))])

    def test_meal_assignment_dialog_offers_split_and_keeps_one_click_meals(self):
        source = self._write_diary_csv("food_name,grams\nOats,500\n")
        row = self.services.diary_importer.preview(source).rows[0]
        dialog = MealAssignmentDialog(row, self.window)
        self.assertIsNotNone(dialog.findChild(QPushButton, "assignSplit"))
        dialog.findChild(QPushButton, "assignMealLunch").click()
        self.assertEqual(dialog.portions, (MealPortion("Lunch", Decimal("500")),))

    def test_split_dialog_rejects_amounts_that_do_not_add_up(self):
        split = MealSplitDialog("Potatoes", Decimal("500"), parent=self.window)
        split.amount_inputs["Lunch"].setValue(200)
        split.amount_inputs["Dinner"].setValue(200)
        self.assertFalse(split.apply_button.isEnabled())
        self.assertIn("100", split.status_label.text())

    def test_existing_diary_entry_can_be_split_between_meals(self):
        entry = self.services.diary.add_item("2026-09-30", "Lunch", "oats", Decimal("500"))
        self.window.diary_view.set_date("2026-09-30")

        def accept_split(dialog):
            dialog.amount_inputs["Lunch"].setValue(200)
            dialog.amount_inputs["Dinner"].setValue(300)
            dialog.apply()
            return QDialog.DialogCode.Accepted

        with patch("calorie_tracker.presentation.views.diary_view.MealSplitDialog.exec", new=accept_split):
            self.window.diary_view.split_entry(entry.id)

        entries = self.services.diary.entries_for_day("2026-09-30")
        self.assertEqual([(e.meal, e.amount_g) for e in entries], [("Lunch", Decimal("200")), ("Dinner", Decimal("300"))])

    def test_review_dialog_colours_problem_rows_and_filters_to_them(self):
        source = self._write_diary_csv("food_name,grams,meal\nOats,50,Breakfast\nOat,30,Lunch\n")
        preview = self.services.diary_importer.preview(source)
        dialog = DiaryCsvReviewDialog(self.services, "2026-09-30", preview, self.window)

        self.assertIn("Did you mean 'Oats'", dialog.table.item(1, 4).text())
        self.assertNotEqual(dialog.table.item(0, 4).background().color(), dialog.table.item(1, 4).background().color())
        dialog.only_problems.setChecked(True)
        self.assertTrue(dialog.table.isRowHidden(0))
        self.assertFalse(dialog.table.isRowHidden(1))
        self.assertIn("Amount (g)", dialog.findChild(QLabel, "csvMappingSummary").text())

    def test_food_review_dialog_lists_every_row_with_status(self):
        source = Path(self.temp_dir.name) / "foods.csv"
        source.write_text(
            "name;kcal;protein;fat;carbs;fibre\nBarley;120,5;5;4;20;3\nBroken;abc;5;4;20;3\nBarley;1;1;1;1;1\n",
            encoding="utf-8",
        )
        preview = self.services.importer.preview(source)
        dialog = FoodCsvReviewDialog(preview, self.window)

        self.assertEqual(dialog.table.rowCount(), 3)
        self.assertIn("Ready", dialog.table.item(0, 7).text())
        self.assertIn("Needs correction", dialog.table.item(1, 7).text())
        self.assertIn("Skipped", dialog.table.item(2, 7).text())
        self.assertEqual(dialog.import_button.text(), "Import 1 food and correct 1 row")
        self.assertIn("semicolon", dialog.findChild(QLabel, "csvMappingSummary").text())

    def test_csv_drop_accepts_only_csv_files_and_help_dialog_returns_the_dropped_path(self):
        from PySide6.QtCore import QMimeData, QUrl
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile("/tmp/day.CSV"), QUrl.fromLocalFile("/tmp/photo.png")])
        self.assertEqual(csv_paths(mime), ["/tmp/day.CSV"])
        self.assertTrue(self.window.diary_view.acceptDrops())
        self.assertTrue(self.window.foods_view.acceptDrops())

        help_dialog = CsvImportHelpDialog("t", "d", "food_name", "Oats", self.window)
        help_dialog.handle_dropped_csv("/tmp/day.csv")
        self.assertEqual(help_dialog.dropped_path, "/tmp/day.csv")
        self.assertEqual(help_dialog.result(), QDialog.DialogCode.Accepted)

    def test_dropped_csv_opens_the_matching_review_without_a_file_picker(self):
        source = self._write_diary_csv("food_name,grams\nOats,50\n")
        with patch("calorie_tracker.presentation.views.diary_view.DiaryCsvReviewDialog.exec",
                   return_value=QDialog.DialogCode.Rejected) as review:
            self.window.diary_view.handle_dropped_csv(str(source))
        review.assert_called_once()

    def test_every_popup_dialog_closes_with_ctrl_w_but_main_window_has_no_shortcut(self):
        dialog = FoodDialog(self.window)
        dialog.ensurePolished()
        install_close_shortcut(dialog)
        shortcuts = [
            child for child in dialog.children()
            if child.objectName() == "closeDialogShortcut"
        ]
        self.assertEqual(len(shortcuts), 1)
        self.assertEqual(shortcuts[0].key().toString(), CLOSE_DIALOG_SHORTCUT)
        dialog.show()
        shortcuts[0].activated.emit()
        self.assertFalse(dialog.isVisible())
        self.assertFalse([c for c in self.window.children() if c.objectName() == "closeDialogShortcut"])

    def test_buttons_never_shrink_below_their_text(self):
        dialog = MealSplitDialog("Potatoes", Decimal("500"), parent=self.window)
        dialog.show()
        self.application.processEvents()
        for button in dialog.findChildren(QPushButton):
            if button.text():
                self.assertGreaterEqual(
                    button.minimumWidth(), button.fontMetrics().horizontalAdvance(button.text()), button.text()
                )
        dialog.close()

    def test_editing_a_diary_entry_focuses_the_grams_field(self):
        entry = self.services.diary.add_item("2026-09-30", "Lunch", "oats", Decimal("80"))
        diary = self.window.diary_view
        self.window.show()
        diary.set_date("2026-09-30")
        diary.begin_edit(entry.id)
        self.application.processEvents()
        self.assertIn(
            self.window.focusWidget(), (diary.edit_amount_input, diary.edit_amount_input.lineEdit())
        )
        self.assertEqual(diary.edit_amount_input.lineEdit().selectedText().replace(",", "."), "80.0")

    def test_calendar_shows_tick_for_logged_past_days_and_cross_for_missed_ones(self):
        today = QDate.currentDate()
        logged_day = today.addDays(-3)
        self.services.diary.add_item(logged_day.toString("yyyy-MM-dd"), "Lunch", "oats", Decimal("50"))
        calendar_page = self.window.calendar_view
        calendar_page.set_month(logged_day.year(), logged_day.month())
        calendar = calendar_page.calendar

        self.assertEqual(calendar.day_status(logged_day), "logged")
        for offset in (-2, -1):
            day = today.addDays(offset)
            if (day.year(), day.month()) == (logged_day.year(), logged_day.month()):
                self.assertEqual(calendar.day_status(day), "missed")
        before = logged_day.addDays(-1)
        if (before.year(), before.month()) == (logged_day.year(), logged_day.month()):
            self.assertIsNone(calendar.day_status(before))  # before tracking began
        self.assertIsNone(calendar.day_status(today))

    def test_calendar_paints_green_tick_and_red_cross(self):
        calendar = self.window.calendar_view.calendar
        for status, check in (("logged", lambda c: c.green() > 140 and c.red() < 100), ("missed", lambda c: c.red() > 180 and c.green() < 120)):
            image = QImage(100, 80, QImage.Format.Format_ARGB32)
            image.fill(QColor("#f1f5fb"))
            painter = QPainter(image)
            calendar._draw_status(painter, QRect(0, 0, 100, 80), status)
            painter.end()
            hits = sum(
                1 for y in range(80) for x in range(100) if check(image.pixelColor(x, y))
            )
            self.assertGreater(hits, 0, status)

    def test_settings_offer_fiber_target_data_folder_and_diary_export(self):
        settings = self.window.settings_view
        self.assertIn("fiber", settings.target_inputs)
        self.assertIn(str(Path(self.temp_dir.name)), settings.data_folder_label.text())
        self.services.diary.add_item("2026-10-01", "Lunch", "oats", Decimal("100"))
        target = Path(self.temp_dir.name) / "export.csv"
        self.assertEqual(settings.export_diary(str(target)), 1)
        self.assertIn("2026-10-01,Lunch,Oats,100", target.read_text(encoding="utf-8-sig"))

    def test_primary_secondary_and_danger_buttons_have_distinct_styles(self):
        sheet = self.window.styleSheet()
        for selector in ("QPushButton#primaryButton", "QPushButton#dangerButton", "QPushButton#importDiaryCsvButton",
                         "QPushButton#addFoodButton", "QPushButton#undoButton"):
            self.assertIn(selector, sheet)


if __name__ == "__main__":
    unittest.main()
