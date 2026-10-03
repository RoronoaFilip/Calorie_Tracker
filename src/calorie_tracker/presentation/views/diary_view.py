from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, QTimer, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.application.diary import MEALS
from calorie_tracker.bootstrap import ApplicationServices
from calorie_tracker.domain.diary import DiaryEntry
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.presentation.control_styles import fit_button_text, style_calendar_arrows, style_chevron_button
from calorie_tracker.infrastructure.diary_csv_importer import DiaryCsvFormatError
from calorie_tracker.presentation.dialogs.csv_import_help_dialog import CsvImportHelpDialog
from calorie_tracker.presentation.dialogs.diary_csv_import_dialog import DiaryCsvReviewDialog
from calorie_tracker.presentation.dialogs.meal_split_dialog import MealSplitDialog
from calorie_tracker.domain.diary import MealPortion
from calorie_tracker.presentation.csv_drop import CsvDropMixin


def _amount(value: Decimal) -> str:
    return f"{value.normalize():f}"


class AddEntryDialog(QDialog):
    def __init__(self, services: ApplicationServices, meal: str, parent=None):
        super().__init__(parent)
        self.services = services
        self.setWindowTitle(f"Add to {meal}")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Add food or recipe to {meal}"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search foods and recipes")
        self.search_input.setAccessibleName("Search catalogue for diary entry")
        layout.addWidget(self.search_input)
        layout.addWidget(QLabel("Recently used"))
        self.recent_results = QListWidget()
        self.recent_results.setAccessibleName("Recently used foods and recipes")
        self.recent_results.setMaximumHeight(118)
        layout.addWidget(self.recent_results)
        layout.addWidget(QLabel("Matching foods and recipes"))
        self.results = QListWidget()
        self.results.setAccessibleName("Matching foods and recipes")
        layout.addWidget(self.results)
        amount_row = QHBoxLayout()
        amount_row.addWidget(QLabel("Amount (g)"))
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0.1, 100000)
        self.amount_input.setDecimals(1)
        self.amount_input.setValue(100)
        self.amount_input.setAccessibleName("Diary entry amount in grams")
        amount_row.addWidget(self.amount_input)
        layout.addLayout(amount_row)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.add_button = QPushButton("Add")
        self.add_button.setObjectName("primaryButton")
        self.add_button.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(self.add_button)
        layout.addLayout(actions)
        self.search_input.textChanged.connect(self.refresh)
        self.recent_results.itemSelectionChanged.connect(self._update_add_enabled)
        self.results.itemSelectionChanged.connect(self._update_add_enabled)
        self.results.itemDoubleClicked.connect(lambda _: self.accept())
        self.recent_results.itemDoubleClicked.connect(lambda _: self.accept())
        self.refresh()

    def refresh(self) -> None:
        query = self.search_input.text().strip().casefold()
        self.recent_results.clear()
        for item_id, name, kind in self.services.diary_repository.recent_items():
            item = QListWidgetItem(f"{name}  ·  {'Food' if kind == 'food' else 'Recipe'}")
            item.setData(Qt.ItemDataRole.UserRole, item_id)
            self.recent_results.addItem(item)
        self.results.clear()
        rows = [(food.name, "food", food.id) for food in self.services.foods.search(query)]
        rows.extend((item.draft.name, "recipe", item.id) for item in self.services.recipes.search(query))
        for name, kind, item_id in sorted(rows, key=lambda row: row[0].casefold()):
            entry = QListWidgetItem(f"{name}  ·  {'Food' if kind == 'food' else 'Recipe'}")
            entry.setData(Qt.ItemDataRole.UserRole, item_id)
            self.results.addItem(entry)
        if self.results.count():
            self.results.setCurrentRow(0)
        self._update_add_enabled()

    def _update_add_enabled(self) -> None:
        self.add_button.setEnabled(self.selected_item_id is not None)

    @property
    def selected_item_id(self) -> str | None:
        item = self.recent_results.currentItem() or self.results.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None


class DiaryView(CsvDropMixin, QWidget):
    _sixteen_pixel_font = "font-size: 16px;"

    def __init__(self, services: ApplicationServices, notify):
        super().__init__()
        self.init_csv_drop()
        self.services = services
        self.notify = notify
        self.selected_date = date.today().isoformat()
        self._undo_entry: DiaryEntry | None = None
        self._entry_widgets: dict[str, QWidget] = {}
        self.setObjectName("mainContent")
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 28, 36, 28)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Your diary")
        title.setStyleSheet("font-size: 26px; font-weight: 650; color: #172538;")
        header.addWidget(title)
        header.addStretch(1)
        self.previous_button = QPushButton()
        self.previous_button.setObjectName("previousDayButton")
        style_chevron_button(self.previous_button, "left", "Previous day")
        self.previous_button.clicked.connect(lambda: self.shift_date(-1))
        header.addWidget(self.previous_button)
        self.date_picker = QDateEdit()
        self.date_picker.setCalendarPopup(True)
        style_calendar_arrows(self.date_picker.calendarWidget())
        self.date_picker.setDisplayFormat("ddd, d MMM yyyy")
        self.date_picker.setDate(QDate.currentDate())
        self.date_picker.setAccessibleName("Selected diary date")
        self.date_picker.setToolTip("Choose the diary date")
        self.date_picker.lineEdit().setAcceptDrops(False)  # let dropped CSVs reach the page
        self.date_picker.dateChanged.connect(self._date_changed)
        header.addWidget(self.date_picker)
        self.next_button = QPushButton()
        self.next_button.setObjectName("nextDayButton")
        style_chevron_button(self.next_button, "right", "Next day")
        self.next_button.clicked.connect(lambda: self.shift_date(1))
        header.addWidget(self.next_button)
        today_button = QPushButton("Today")
        today_button.setObjectName("todayButton")
        today_button.clicked.connect(lambda: self.set_date(date.today().isoformat()))
        header.addWidget(today_button)
        self.import_csv_button = QPushButton("Import CSV")
        self.import_csv_button.setObjectName("importDiaryCsvButton")
        self.import_csv_button.setAccessibleName("Import diary entries from CSV")
        self.import_csv_button.setToolTip("Import foods and amounts for this selected day")
        self.import_csv_button.clicked.connect(self.choose_diary_csv)
        header.addWidget(self.import_csv_button)
        self.undo_button = QPushButton("Undo delete")
        self.undo_button.setObjectName("undoButton")
        self.undo_button.setToolTip("Restore the diary entry you just deleted")
        self.undo_button.setVisible(False)
        self.undo_button.clicked.connect(self.undo_delete)
        self._undo_timer = QTimer(self)
        self._undo_timer.setSingleShot(True)
        self._undo_timer.setInterval(5000)
        self._undo_timer.timeout.connect(self._expire_undo)
        header.addWidget(self.undo_button)
        root.addLayout(header)

        self.macro_cards: dict[str, tuple[QLabel, QProgressBar]] = {}
        card_row = QHBoxLayout()
        card_colors = {
            "calories": ("#fff0d8", "#eed8b5"),
            "protein": ("#e0f2e9", "#c6e3d3"),
            "carbohydrates": ("#e4ecff", "#cad8f4"),
            "fat": ("#f2e8f5", "#dfcde6"),
            "fiber": ("#edf2df", "#d8e1c1"),
        }
        for key, caption, unit in (("calories", "Calories", "kcal"), ("protein", "Protein", "g"),
                                   ("carbohydrates", "Carbs", "g"), ("fat", "Fat", "g"),
                                   ("fiber", "Fiber", "g")):
            card = QFrame()
            card.setObjectName("card")
            background, border = card_colors[key]
            card.setStyleSheet(
                f"QFrame#card {{ background: {background}; border: 1px solid {border}; border-radius: 13px; }}"
            )
            card_layout = QVBoxLayout(card)
            label = QLabel(caption)
            label.setStyleSheet("color: #738094; font-size: 18px;")
            value = QLabel(f"0 {unit}")
            value.setObjectName(f"total{key.title()}")
            value.setStyleSheet("font-size: 19px; font-weight: 650; color: #172538;")
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            bar.setAccessibleName(f"{caption} target progress")
            card_layout.addWidget(label)
            card_layout.addWidget(value)
            card_layout.addWidget(bar)
            card_row.addWidget(card)
            self.macro_cards[key] = value, bar
        root.addLayout(card_row)
        self.day_total_label = self.macro_cards["calories"][0]

        scroll = QScrollArea()
        scroll.setObjectName("diaryMealsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #edf2f9; border: 0; }")
        scroll.viewport().setStyleSheet("background: #edf2f9; border: 0;")
        content = QWidget()
        content.setStyleSheet("background: #edf2f9;")
        self.meal_layout = QVBoxLayout(content)
        self.meal_layout.setContentsMargins(0, 0, 8, 0)
        self.meal_layout.setSpacing(12)
        self.meal_panels: dict[str, QWidget] = {}
        self.meal_entries: dict[str, QVBoxLayout] = {}
        meal_colors = {
            "Breakfast": ("#fff5e5", "#eddfc8"),
            "Lunch": ("#e7f3eb", "#d0e4d6"),
            "Dinner": ("#e8effa", "#d1ddef"),
            "Snacks": ("#f1eafa", "#ded1ee"),
        }
        for meal in MEALS:
            panel = QFrame()
            panel.setObjectName("card")
            background, border = meal_colors[meal]
            panel.setStyleSheet(
                f"QFrame#card {{ background: {background}; border: 1px solid {border}; border-radius: 13px; }}"
            )
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(16, 12, 16, 12)
            heading = QHBoxLayout()
            label = QLabel(meal)
            label.setStyleSheet(
                "font-size: 18px; font-weight: 650;"
            )

            subtotal = QLabel("0 kcal")
            subtotal.setObjectName(f"subtotal{meal}")
            subtotal.setStyleSheet("font-size: 16px; color: #536d95;")
            heading.addWidget(label)
            heading.addStretch(1)
            heading.addWidget(subtotal)
            panel_layout.addLayout(heading)
            entries = QVBoxLayout()
            panel_layout.addLayout(entries)
            add = QPushButton(f"+ Add food to {meal}")
            add.setObjectName("addFoodButton")
            add.setAccessibleName(f"Add food to {meal}")
            add.setStyleSheet("font-size: 14px;")
            add.setToolTip(f"Search foods and recipes for {meal}")
            add.clicked.connect(lambda checked=False, category=meal: self.open_add_dialog(category))
            panel_layout.addWidget(add, alignment=Qt.AlignmentFlag.AlignLeft)
            self.meal_layout.addWidget(panel)
            self.meal_panels[meal] = panel
            self.meal_entries[meal] = entries
        self.meal_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self.refresh()

    def _date_changed(self, value: QDate) -> None:
        self.selected_date = value.toString("yyyy-MM-dd")
        self.refresh()

    def set_date(self, value: str) -> None:
        parsed = date.fromisoformat(value)
        self.selected_date = parsed.isoformat()
        self.date_picker.blockSignals(True)
        self.date_picker.setDate(QDate(parsed.year, parsed.month, parsed.day))
        self.date_picker.blockSignals(False)
        self.refresh()

    def shift_date(self, days: int) -> None:
        parsed = date.fromisoformat(self.selected_date).toordinal() + days
        self.set_date(date.fromordinal(parsed).isoformat())

    def open_add_dialog(self, meal: str) -> None:
        dialog = AddEntryDialog(self.services, meal, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_item_id:
            self.add_catalogue_item(meal, dialog.selected_item_id, Decimal(str(dialog.amount_input.value())))

    def add_catalogue_item(self, meal: str, item_id: str, amount_g: Decimal) -> DiaryEntry:
        entry = self.services.diary.add_item(self.selected_date, meal, item_id, amount_g)
        self.refresh()
        self.notify(f"Added {entry.display_name} to {meal}.")
        return entry

    def choose_diary_csv(self) -> None:
        help_dialog = CsvImportHelpDialog(
            "Import diary entries from CSV",
            "Match each row to a food already in your catalogue. Amounts are grams; meal/time is optional and can be assigned or split between meals during review. You can also drop a CSV anywhere on this page.",
            "food_name, grams_eaten, meal  (column order and common alternative names are fine)",
            "Oats,45.5,Breakfast",
            self,
        )
        if help_dialog.exec() != CsvImportHelpDialog.DialogCode.Accepted:
            return
        filename = getattr(help_dialog, "dropped_path", None)
        if not filename:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Select diary CSV", "", "CSV files (*.csv);;All files (*)"
            )
        if filename:
            self.import_diary_csv(filename)

    def handle_dropped_csv(self, path: str) -> None:
        """A .csv dropped on the Diary page goes straight to the review screen."""
        self.import_diary_csv(path)

    def import_diary_csv(self, filename: str) -> None:
        try:
            preview = self.services.diary_importer.preview(filename)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "CSV validation failed", str(error))
            return
        dialog = DiaryCsvReviewDialog(self.services, self.selected_date, preview, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.refresh()
        window = self.window()
        calendar_view = getattr(window, "calendar_view", None)
        if calendar_view is not None:
            calendar_view.refresh()
        count = len(dialog.imported_entries)
        self.notify(f"Imported {count} diary entr{'y' if count == 1 else 'ies'} for {self.selected_date}.")

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def refresh(self) -> None:
        entries = self.services.diary.entries_for_day(self.selected_date)
        totals = self.services.diary.totals_for_day(self.selected_date)
        self._entry_widgets.clear()
        for meal in MEALS:
            self._clear_layout(self.meal_entries[meal])
            meal_entries = tuple(entry for entry in entries if entry.meal == meal)
            meal_total_text = f"{totals.meals[meal].calories:.2f} kcal · " \
                              f"Protein {totals.meals[meal].protein:.2f}g · " \
                              f"Carbs {totals.meals[meal].carbohydrates:.2f}g · " \
                              f"Fat {totals.meals[meal].fat:.2f}g · " \
                              f"Fiber {totals.meals[meal].fiber:.2f}g"
            self.findChild(QLabel, f"subtotal{meal}").setText(meal_total_text)
            if not meal_entries:
                hint = QLabel("Nothing logged yet. Add a food or recipe to get started.")
                hint.setStyleSheet("color: #8994a3; padding: 7px 0; font-size: 14px;")
                self.meal_entries[meal].addWidget(hint)
            for entry in meal_entries:
                self.meal_entries[meal].addWidget(self._entry_row(entry))
        names = {
            "calories": "Calories", "protein": "Protein", "carbohydrates": "Carbohydrates",
            "fat": "Fat", "fiber": "Fiber",
        }
        for key, (value, bar) in self.macro_cards.items():
            nutrient = getattr(totals.total, key)
            unit = "kcal" if key == "calories" else "g"
            value.setText(f"{nutrient:.2f} {unit}")
            target = self._target_value(key)
            bar.setValue(min(100, int(nutrient * 100 / target)) if target else 0)
            bar.setToolTip(f"{names[key]} target: {target:g} {unit}" if target else "No daily target set")

    def _target_value(self, key: str) -> Decimal | None:
        targets = self.services.settings.get_json("daily_targets") or {}
        value = targets.get(key)
        try:
            number = Decimal(str(value)) if value is not None else None
            return number if number is not None and number > 0 else None
        except (TypeError, ValueError):
            return None

    def _entry_row(self, entry: DiaryEntry) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 4)
        label = QLabel(f"{entry.display_name}  ·  {_amount(entry.amount_g)}g")
        nutrients = entry.nutrients
        details = QLabel(
            f"{nutrients.calories:.2f} kcal · "
            f"Protein {nutrients.protein:.2f}g · "
            f"Carbs {nutrients.carbohydrates:.2f}g · "
            f"Fat {nutrients.fat:.2f}g · "
            f"Fiber {nutrients.fiber:.2f}g"
        )
        details.setStyleSheet("font-size: 16px; color: #536d95;")
        label.setStyleSheet("font-size: 16px; color: #172538;")
        layout.addWidget(label, 2)
        layout.addWidget(details, 3)
        edit = QPushButton("✎")
        edit.setStyleSheet("font-size: 26px;")
        edit.setToolTip("Edit amount; save or cancel your change")
        edit.clicked.connect(lambda checked=False, entry_id=entry.id: self.begin_edit(entry_id))
        delete = QPushButton("×")
        delete.setObjectName("dangerButton")
        delete.setToolTip("Delete this diary entry")
        delete.setStyleSheet("font-size: 26px;")
        delete.clicked.connect(lambda checked=False, entry_id=entry.id: self.delete_entry(entry_id))
        for button in (edit, delete):
            button.setAccessibleName(f"{button.text()} {entry.display_name}")
            button.setProperty("compact", True)
            fit_button_text(button)
            layout.addWidget(button)
        row.setObjectName(f"diaryEntry{entry.id}")
        self._entry_widgets[entry.id] = row
        return row

    def begin_edit(self, entry_id: str) -> None:
        entry = next((item for item in self.services.diary.entries_for_day(self.selected_date) if item.id == entry_id),
                     None)
        row = self._entry_widgets.get(entry_id)
        if entry is None or row is None:
            return
        layout = row.layout()
        while layout.count():
            widget = layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        edit_amount_widget = QLabel(f"Edit amount for {entry.display_name}")
        edit_amount_widget.setStyleSheet(self._sixteen_pixel_font)
        layout.addWidget(edit_amount_widget)
        self.edit_amount_input = QDoubleSpinBox()
        self.edit_amount_input.setObjectName("editDiaryAmount")
        self.edit_amount_input.setAccessibleName("Edit diary amount in grams")
        self.edit_amount_input.setRange(0.1, 100000)
        self.edit_amount_input.setDecimals(1)
        self.edit_amount_input.setValue(float(entry.amount_g))
        self.edit_amount_input.setStyleSheet(self._sixteen_pixel_font)
        layout.addWidget(self.edit_amount_input)
        self._editing_entry_id = entry_id
        save = QPushButton("Save")
        save.setObjectName("primaryButton")
        save.setProperty("compact", True)
        save.clicked.connect(self.save_edit)
        save.setStyleSheet(self._sixteen_pixel_font)
        cancel = QPushButton("Cancel")
        cancel.setProperty("compact", True)
        cancel.clicked.connect(self.cancel_edit)
        cancel.setStyleSheet(self._sixteen_pixel_font)
        for button in (save, cancel):
            fit_button_text(button)
            layout.addWidget(button)
        self.edit_amount_input.lineEdit().returnPressed.connect(self.save_edit)
        # Ready to type: focus the grams field with its value selected.
        self._focus_edit_amount()
        QTimer.singleShot(0, self._focus_edit_amount)

    def _focus_edit_amount(self) -> None:
        field = getattr(self, "edit_amount_input", None)
        if field is None:
            return
        try:
            field.setFocus(Qt.FocusReason.OtherFocusReason)
            field.selectAll()
        except RuntimeError:  # the row was rebuilt before the deferred call ran
            pass

    def split_entry(self, entry_id: str) -> None:
        entry = self.services.diary.diary.get(entry_id)
        if entry is None:
            return
        dialog = MealSplitDialog(
            entry.display_name, entry.amount_g, (MealPortion(entry.meal, entry.amount_g),), self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.portions:
            return
        try:
            self.services.diary.split_entry(entry_id, dialog.portions)
        except (ValueError, KeyError) as error:
            QMessageBox.critical(self, "Could not split entry", str(error))
            return
        self.refresh()
        self.notify(f"Split {entry.display_name} between {len(dialog.portions)} meal"
                    f"{'s' if len(dialog.portions) != 1 else ''}.")

    def save_edit(self) -> None:
        self.services.diary.edit_amount(self._editing_entry_id, Decimal(str(self.edit_amount_input.value())))
        self.refresh()
        self.notify("Diary entry saved.")

    def cancel_edit(self) -> None:
        self.refresh()

    def repeat_entry(self, entry_id: str) -> None:
        self.services.diary.repeat_entry(entry_id)
        self.refresh()
        self.notify("Entry repeated in the same meal.")

    def delete_entry(self, entry_id: str, confirmed: bool | None = None) -> None:
        entry = self.services.diary.diary.get(entry_id)
        if entry is None:
            return
        if confirmed is None:
            answer = QMessageBox.question(
                self, "Delete diary entry", f"Delete {entry.display_name} from {entry.meal}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            confirmed = answer == QMessageBox.StandardButton.Yes
        if not confirmed:
            return
        self._undo_entry = self.services.diary.delete_entry(entry_id)
        self.undo_button.setVisible(True)
        self._undo_timer.start()
        self.refresh()
        self.notify("Entry deleted. Use Undo to restore it.", 5000)

    def undo_delete(self) -> None:
        if self._undo_entry is None:
            return
        self.services.diary.restore_entry(self._undo_entry)
        self._undo_entry = None
        self._undo_timer.stop()
        self.undo_button.setVisible(False)
        self.refresh()
        self.notify("Deleted entry restored.")

    def _expire_undo(self) -> None:
        self._undo_entry = None
        self.undo_button.setVisible(False)
