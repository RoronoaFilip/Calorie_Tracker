"""UI tests for barcode-photo import, file-type drop routing, the CSV repair popup and text fitting."""

import logging
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QFontMetrics
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QPushButton

from calorie_tracker.bootstrap import build_services
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.products import (
    BarcodeImageError, BarcodeReaderUnavailableError, LookupOfflineError, ProductInfo,
)
from calorie_tracker.domain.recipes import Food
from calorie_tracker.infrastructure.csv_reading import CsvTable
from calorie_tracker.presentation.dialogs.csv_import_help_dialog import CsvImportHelpDialog
from calorie_tracker.presentation.dialogs.csv_repair_dialog import CsvRepairDialog, column_letter
from calorie_tracker.presentation.dialogs.food_dialog import FoodDialog
from calorie_tracker.presentation.main_window import MainWindow

REPAIR_EXEC = "calorie_tracker.presentation.dialogs.csv_repair_dialog.CsvRepairDialog.exec"
FOOD_DIALOG_EXEC = "calorie_tracker.presentation.views.foods_view.FoodDialog.exec"
BARCODE = "5449000000996"
COLA = ProductInfo(
    BARCODE, "Cola", Nutrients(calories=Decimal("42"), carbohydrates=Decimal("10.6"), sugars=Decimal("10.6")),
    "Fizz Co", ("fiber", "omega_3", "omega_6"),
)


class FakeReader:
    def __init__(self):
        self.result: tuple[str, ...] | Exception = (BARCODE,)

    def read(self, path):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeLookup:
    def __init__(self):
        self.result: ProductInfo | Exception | None = COLA
        self.calls = 0

    def lookup(self, barcode):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def table(*rows: list[str]) -> CsvTable:
    return CsvTable([list(row) for row in rows], ",", "utf-8")


class ImportUiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.reader, self.lookup = FakeReader(), FakeLookup()
        self.services = build_services(
            Path(self.temp_dir.name) / "data" / "tracker.sqlite3",
            barcode_reader=self.reader, product_lookup=self.lookup,
        )
        self.addCleanup(self._close_log_handlers)
        self.services.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))
        self.window = MainWindow(self.services)
        self.addCleanup(self.window.close)
        self.photo = Path(self.temp_dir.name) / "barcode.png"
        Image.new("RGB", (60, 40), "white").save(self.photo)

    def _close_log_handlers(self):
        logger = logging.getLogger("calorie_tracker")
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)


class BarcodePhotoImportTests(ImportUiTestCase):
    def import_photo(self, accept=True):
        """Run the photo import with the food form auto-answered; returns what the form showed."""
        shown = {}

        def review(dialog):
            shown.update(
                title=dialog.windowTitle(),
                name=dialog.name_input.text(),
                calories=dialog.nutrient_inputs["calories"].value(),
                banner=dialog.banner_label.text() if dialog.banner_label else "",
                level=dialog.banner_frame.property("level") if dialog.banner_frame else None,
                has_photo=dialog.photo_label is not None,
                saved_before_save=len(self.services.foods.search(dialog.name_input.text() or "~none~")),
                status=self.window.statusBar().currentMessage(),
            )
            return FoodDialog.DialogCode.Accepted if accept else FoodDialog.DialogCode.Rejected

        with patch(FOOD_DIALOG_EXEC, new=review):
            self.window.foods_view.import_photo(self.photo)
        return shown

    def test_found_product_opens_a_prefilled_form_and_is_saved_only_on_save(self):
        shown = self.import_photo()

        self.assertEqual(shown["title"], "Review scanned product")
        self.assertEqual(shown["name"], "Cola (Fizz Co)")
        self.assertEqual(shown["calories"], 42)
        self.assertEqual(shown["level"], "success")
        self.assertTrue(shown["has_photo"])
        self.assertIn("Open Food Facts", shown["banner"])
        self.assertIn("fiber", shown["banner"])  # says what the database did not know
        self.assertEqual(shown["saved_before_save"], 0)
        self.assertEqual(self.services.foods.search("Cola")[0].nutrients_per_100g.calories, Decimal("42"))

    def test_cancelling_the_form_adds_nothing(self):
        self.import_photo(accept=False)
        self.assertEqual(self.services.foods.search("Cola"), ())
        self.assertIn("Nothing was added", self.window.statusBar().currentMessage())

    def test_offline_still_opens_the_form_and_shows_a_no_connection_notification(self):
        self.lookup.result = LookupOfflineError("down")
        with patch("calorie_tracker.presentation.views.foods_view.QMessageBox.warning") as warning:
            shown = self.import_photo(accept=False)

        warning.assert_not_called()  # the form IS the popup; no extra error box
        self.assertEqual(shown["name"], "")
        self.assertEqual(shown["calories"], 0)
        self.assertEqual(shown["level"], "warning")
        self.assertIn("No internet connection", shown["banner"])
        self.assertIn(BARCODE, shown["banner"])
        self.assertIn("No internet connection", shown["status"])

    def test_unknown_product_opens_a_blank_form_that_names_the_barcode(self):
        self.lookup.result = None
        shown = self.import_photo(accept=False)
        self.assertEqual(shown["level"], "warning")
        self.assertIn("not in the Open Food Facts database", shown["banner"])

    def test_photo_without_a_usable_barcode_explains_why_and_opens_no_form(self):
        cases = (
            ((), "No barcode was found"),
            (BarcodeImageError("not a picture"), "not a picture"),
            (BarcodeReaderUnavailableError("zxing-cpp is not installed"), "zxing-cpp is not installed"),
        )
        for outcome, expected in cases:
            with self.subTest(expected=expected):
                self.reader.result = outcome
                with patch("calorie_tracker.presentation.views.foods_view.QMessageBox.warning") as warning, patch(
                    FOOD_DIALOG_EXEC
                ) as form:
                    self.window.foods_view.import_photo(self.photo)
                form.assert_not_called()
                self.assertIn(expected, warning.call_args.args[2])
        self.assertEqual(self.lookup.calls, 0)  # nothing is sent anywhere without a barcode

    def test_saving_a_second_food_with_the_same_name_asks_first(self):
        self.services.foods.save(Food("cola-old", "Cola (Fizz Co)", Nutrients()))
        with patch(
            "calorie_tracker.presentation.views.foods_view.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Cancel,
        ) as ask:
            self.import_photo()
        ask.assert_called_once()
        self.assertEqual(len(self.services.foods.search("Cola")), 1)

        with patch(
            "calorie_tracker.presentation.views.foods_view.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            self.import_photo()
        self.assertEqual(len(self.services.foods.search("Cola")), 2)


class DropRoutingTests(ImportUiTestCase):
    def _drag(self, widget, *paths) -> QDragEnterEvent:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        event = QDragEnterEvent(
            QPoint(5, 5), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
        )
        widget.dragEnterEvent(event)
        return event

    def test_foods_page_takes_photos_of_any_format_and_csvs_but_not_other_files(self):
        csv_file = Path(self.temp_dir.name) / "foods.csv"
        csv_file.write_text("food_name\n")
        jpeg = Path(self.temp_dir.name) / "IMG_0042"  # no extension at all
        Image.new("RGB", (8, 8)).save(jpeg, "JPEG")
        other = Path(self.temp_dir.name) / "notes.txt"
        other.write_text("hi")
        for path in (self.photo, jpeg, csv_file):
            with self.subTest(path=path.name):
                self.assertTrue(self._drag(self.window.foods_view, path).isAccepted())
        self.assertFalse(self._drag(self.window.foods_view, other).isAccepted())

    def test_diary_page_still_takes_only_csv(self):
        csv_file = Path(self.temp_dir.name) / "day.csv"
        csv_file.write_text("food_name,grams\n")
        self.assertTrue(self._drag(self.window.diary_view, csv_file).isAccepted())
        self.assertFalse(self._drag(self.window.diary_view, self.photo).isAccepted())

    def test_dropped_files_go_to_the_matching_importer(self):
        csv_file = Path(self.temp_dir.name) / "foods.csv"
        csv_file.write_text("food_name\n")
        view = self.window.foods_view
        with patch.object(type(view), "import_photo") as photo, patch.object(type(view), "import_csv") as csv_import:
            view.handle_dropped_file(str(self.photo), "image")
            view.handle_dropped_file(str(csv_file), "csv")
        photo.assert_called_once_with(str(self.photo))
        csv_import.assert_called_once_with(str(csv_file))

    def test_import_dialog_offers_a_photo_and_remembers_what_was_dropped(self):
        dialog = CsvImportHelpDialog("t", "d", "food_name", "Oats", self.window, allow_photo=True)
        self.addCleanup(dialog.close)
        self.assertIsNotNone(dialog.photo_button)
        dialog.handle_dropped_image(str(self.photo))
        self.assertEqual((dialog.dropped_path, dialog.selected_kind), (str(self.photo), "photo"))
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

        csv_only = CsvImportHelpDialog("t", "d", "food_name", "Oats", self.window)
        self.addCleanup(csv_only.close)
        self.assertIsNone(csv_only.photo_button)

    def test_choosing_a_photo_in_the_import_dialog_opens_the_photo_picker_then_imports_it(self):
        def choose_photo(dialog):
            dialog.selected_kind = "photo"
            return QDialog.DialogCode.Accepted

        with patch("calorie_tracker.presentation.dialogs.csv_import_help_dialog.CsvImportHelpDialog.exec", new=choose_photo), patch(
            "calorie_tracker.presentation.views.foods_view.QFileDialog.getOpenFileName",
            return_value=(str(self.photo), ""),
        ) as picker, patch.object(type(self.window.foods_view), "import_photo") as import_photo:
            self.window.foods_view._choose_import()

        self.assertIn("Select barcode photo", picker.call_args.args)
        import_photo.assert_called_once_with(str(self.photo))


class CsvRepairDialogTests(ImportUiTestCase):
    def dialog(self, rows, importer=None):
        importer = importer or self.services.importer
        dialog = CsvRepairDialog(table(*rows), importer.issues_for, title="Fix", parent=self.window)
        self.addCleanup(dialog.close)
        return dialog

    FOOD_ROWS = (
        ["food_name", "calories / 100g", "protein / 100g", "fat / 100g", "carbohydrates / 100g"],
        ["Rice", "360", "7", "1", "80"],
        ["Barley", "lots", "5", "", "20"],
    )

    def test_shows_the_whole_file_editable_and_marks_problem_cells_with_more_than_colour(self):
        dialog = self.dialog(self.FOOD_ROWS)

        self.assertEqual((dialog.table.rowCount(), dialog.table.columnCount()), (3, 5))
        self.assertEqual(dialog.cell_text(1, 0), "Rice")
        self.assertTrue(dialog.table.item(2, 1).flags() & Qt.ItemFlag.ItemIsEditable)
        self.assertEqual({(i.row, i.column) for i in dialog.issues}, {(2, 1), (2, 3)})
        self.assertEqual(dialog.issue_list.count(), 2)
        self.assertEqual(dialog.table.verticalHeaderItem(2).text(), "⚠ 3")
        self.assertIn("“lots”", dialog.table.item(2, 1).toolTip())
        self.assertIn("2 problems", dialog.status_label.text())

    def test_editing_cells_revalidates_and_resubmit_accepts_only_a_clean_table(self):
        dialog = self.dialog(self.FOOD_ROWS)

        dialog.resubmit()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)  # still has problems

        dialog.set_cell(2, 1, "120")
        self.assertEqual(len(dialog.issues), 1)
        dialog.set_cell(2, 3, "4")
        self.assertEqual(dialog.issues, ())
        self.assertIn("No problems", dialog.status_label.text())
        self.assertEqual(dialog.issue_list.count(), 0)

        dialog.resubmit()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.repaired_table.rows[2][1], "120")

    def test_a_missing_column_is_fixed_by_renaming_a_header_cell(self):
        dialog = self.dialog([
            ["food_name", "calories", "protein", "fat", "sugar"],
            ["Rice", "360", "7", "1", "80"],
        ])
        self.assertTrue(dialog.issues)
        self.assertIsNone(dialog.issues[0].column)  # a header problem, not a bad value
        self.assertIn("carbohydrates", dialog.issues[0].message)
        self.assertFalse(dialog.skip_button.isEnabled())  # skipping rows cannot fix a missing column

        dialog.set_cell(0, 4, "carbohydrates")

        self.assertEqual(dialog.issues, ())
        dialog.resubmit()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_skip_problem_rows_continues_with_the_rest(self):
        dialog = self.dialog(self.FOOD_ROWS)
        self.assertTrue(dialog.skip_button.isEnabled())

        dialog.skip_problem_rows()

        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual([row[0] for row in dialog.repaired_table.rows], ["food_name", "Rice"])

    def test_editing_never_touches_the_source_table_or_file(self):
        source = table(*self.FOOD_ROWS)
        dialog = CsvRepairDialog(source, self.services.importer.issues_for, parent=self.window)
        self.addCleanup(dialog.close)
        dialog.set_cell(2, 1, "120")
        self.assertEqual(source.rows[2][1], "lots")

    def test_diary_amount_problem_is_pinned_to_its_cell(self):
        dialog = self.dialog(
            [["food_name", "grams"], ["Oats", "fifty"], ["Oats", "50"]], importer=self.services.diary_importer
        )
        self.assertEqual([(i.row, i.column) for i in dialog.issues], [(1, 1)])

    def test_column_names_are_spreadsheet_letters(self):
        self.assertEqual([column_letter(i) for i in (0, 25, 26, 27, 701, 702)], ["A", "Z", "AA", "AB", "ZZ", "AAA"])

    def test_repair_flow_is_skipped_for_a_clean_file_and_blocks_an_empty_one(self):
        clean = Path(self.temp_dir.name) / "clean.csv"
        clean.write_text(
            "food_name,calories / 100g,protein / 100g,fat / 100g,carbohydrates / 100g\nRice,360,7,1,80\n",
            encoding="utf-8",
        )
        empty = Path(self.temp_dir.name) / "empty.csv"
        empty.write_text("\n\n", encoding="utf-8")
        with patch(REPAIR_EXEC) as repair, patch(
            "calorie_tracker.presentation.views.foods_view.FoodCsvReviewDialog.exec",
            return_value=QDialog.DialogCode.Rejected,
        ):
            self.window.foods_view.import_csv(clean)
        repair.assert_not_called()

        with patch(REPAIR_EXEC) as repair, patch(
            "calorie_tracker.presentation.csv_repair_flow.QMessageBox.critical"
        ) as critical:
            self.window.foods_view.import_csv(empty)
        repair.assert_not_called()
        critical.assert_called_once()


class TextFitTests(ImportUiTestCase):
    def assert_buttons_fit(self, dialog):
        dialog.show()
        self.application.processEvents()
        for button in dialog.findChildren(QPushButton):
            if not button.text():
                continue
            needed = QFontMetrics(button.font()).horizontalAdvance(button.text())
            with self.subTest(dialog=type(dialog).__name__, button=button.text()):
                self.assertGreaterEqual(button.width(), needed + 16)

    def test_buttons_are_wide_enough_for_their_text_in_every_new_dialog(self):
        food = FoodDialog(
            self.window, imported_food=Food("n", "A very long product name " * 4, Nutrients()),
            title="Review scanned product", banner=("warning", "x " * 120), image_path=str(self.photo),
        )
        repair = CsvRepairDialog(
            table(["food_name", "calories"], ["Rice", "x"]), self.services.importer.issues_for, parent=self.window
        )
        chooser = CsvImportHelpDialog("t", "d", "s", "e", self.window, allow_photo=True)
        for dialog in (food, repair, chooser):
            self.addCleanup(dialog.close)
            self.assert_buttons_fit(dialog)

    def test_banner_text_is_never_clipped_and_number_fields_are_wide_enough(self):
        long_text = "Barcode 5449000000996 was read, but there is no internet connection. " * 4
        dialog = FoodDialog(self.window, imported_food=Food("n", "Cola", Nutrients()), banner=("warning", long_text),
                            image_path=str(self.photo))
        self.addCleanup(dialog.close)
        dialog.show()
        self.application.processEvents()

        label = dialog.banner_label
        self.assertGreaterEqual(label.height() + 2, label.heightForWidth(label.width()))
        for key, field in dialog.nutrient_inputs.items():
            with self.subTest(field=key):
                self.assertGreaterEqual(field.width(), 150)
        self.assertGreaterEqual(dialog.name_input.width(), 300)

    def test_repair_table_cells_are_tall_enough_for_the_editor(self):
        dialog = CsvRepairDialog(
            table(["food_name", "calories"], ["Rice", "x"]), self.services.importer.issues_for, parent=self.window
        )
        self.addCleanup(dialog.close)
        self.assertGreaterEqual(dialog.table.rowHeight(0), 36)
        for column in range(dialog.table.columnCount()):
            self.assertGreaterEqual(dialog.table.columnWidth(column), 90)


if __name__ == "__main__":
    unittest.main()
