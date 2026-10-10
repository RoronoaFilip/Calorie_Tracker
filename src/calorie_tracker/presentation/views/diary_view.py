from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, QElapsedTimer, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.bootstrap import ApplicationServices
from calorie_tracker.domain.diary import DiaryEntry
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.application.diary import MEALS
from calorie_tracker.application.targets import is_on_track, load_drift, percent_of_target
from calorie_tracker.domain.nutrition import BASIS_GRAMS
from calorie_tracker.infrastructure.csv_reading import CsvTable
from calorie_tracker.presentation.amount_input import AmountSpinBox
from calorie_tracker.presentation.control_styles import fit_button_text, style_calendar_arrows, style_chevron_button
from calorie_tracker.presentation.dialogs.add_entry_dialog import AddEntryDialog  # noqa: F401  (re-exported)
from calorie_tracker.presentation.dialogs.quick_add_dialog import QuickAddDialog
from calorie_tracker.presentation.formatting import format_entry_amount
from calorie_tracker.infrastructure.diary_csv_importer import DiaryCsvFormatError
from calorie_tracker.presentation.dialogs.diary_csv_import_dialog import DiaryCsvReviewDialog
from calorie_tracker.presentation.dialogs.meal_split_dialog import MealSplitDialog
from calorie_tracker.domain.diary import MealPortion
from calorie_tracker.presentation.import_help import make_help_button
from calorie_tracker.presentation.csv_repair_flow import preview_with_repair


UNDO_MS = 5000  # how long a deleted entry can be brought back
UNDO_LINE_COLOUR = "#b85c6b"


class CountdownButton(QPushButton):
    """A button with a thin line along its bottom edge that winds down from full to empty, like the target bars."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.countdown_fraction = 0.0  # 1.0 = full line, 0.0 = no line

    def set_countdown(self, fraction: float) -> None:
        self.countdown_fraction = max(0.0, min(1.0, fraction))
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.countdown_fraction <= 0:
            return
        margin = 12
        width = max(0.0, (self.width() - 2 * margin) * self.countdown_fraction)
        y = self.height() - 7
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = QPen(QColor("#e8cdd2"), 3)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        painter.drawLine(margin, y, self.width() - margin, y)
        line = QPen(QColor(UNDO_LINE_COLOUR), 3)
        line.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(line)
        painter.drawLine(margin, y, int(margin + width), y)
        painter.end()


class DiaryView(QWidget):
    _sixteen_pixel_font = "font-size: 16px;"
    import_requested = Signal()  # the main window opens the shared import dialog

    def __init__(self, services: ApplicationServices, notify):
        super().__init__()
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
        self.date_picker.lineEdit().setAcceptDrops(False)  # let dropped files reach the main window
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
        self.import_help_button = make_help_button(self)
        header.addWidget(self.import_help_button)
        self.import_csv_button = QPushButton("Import files…")
        self.import_csv_button.setObjectName("importDiaryCsvButton")
        self.import_csv_button.setAccessibleName("Import diary entries, foods or recipes from files, photos or a zip")
        self.import_csv_button.setToolTip(
            "Import CSV files, barcode photos or zip files (Ctrl+O). Diary rows go to the selected day "
            "unless the file is named diary-YYYY-MM-DD.csv."
        )
        self.import_csv_button.clicked.connect(self._request_import)
        header.addWidget(self.import_csv_button)
        self.quick_add_button = QPushButton("Quick add")
        self.quick_add_button.setObjectName("quickAddButton")
        self.quick_add_button.setAccessibleName("Quick add several entries")
        self.quick_add_button.setToolTip(
            "Add several foods to several meals at once in a table (Ctrl+Shift+A)"
        )
        self.quick_add_button.clicked.connect(self.open_quick_add)
        header.addWidget(self.quick_add_button)
        # The undo button appears next to the "Add food" button of the meal the entry was deleted from.
        self.undo_button = CountdownButton("Undo delete")
        self.undo_button.setObjectName("undoButton")
        self.undo_button.setToolTip("Restore the diary entry you just deleted")
        self.undo_button.setVisible(False)
        self.undo_button.clicked.connect(self.undo_delete)
        self.meal_add_rows: dict[str, QHBoxLayout] = {}
        self._undo_timer = QTimer(self)
        self._undo_timer.setSingleShot(True)
        self._undo_timer.setInterval(UNDO_MS)
        self._undo_timer.timeout.connect(self._expire_undo)
        self._undo_clock = QElapsedTimer()
        self._undo_tick = QTimer(self)
        self._undo_tick.setInterval(40)
        self._undo_tick.timeout.connect(self._update_undo_line)
        root.addLayout(header)

        self.macro_cards: dict[str, tuple[QLabel, QProgressBar]] = {}
        self.macro_percents: dict[str, QLabel] = {}
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
            percent = QLabel("")
            percent.setObjectName(f"percent{key.title()}")
            percent.setAccessibleName(f"{caption} share of the daily target")
            percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            percent.setStyleSheet("font-size: 18px; font-weight: 650; color: #536175;")
            value_row = QHBoxLayout()
            value_row.setContentsMargins(0, 0, 0, 0)
            value_row.addWidget(value)
            value_row.addStretch(1)
            value_row.addWidget(percent)
            card_layout.addWidget(label)
            card_layout.addLayout(value_row)
            card_layout.addWidget(bar)
            card_row.addWidget(card)
            self.macro_cards[key] = value, bar
            self.macro_percents[key] = percent
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
            add.setStyleSheet("font-size: 16px;")
            add.setToolTip(f"Search foods and recipes for {meal}")
            add.clicked.connect(lambda checked=False, category=meal: self.open_add_dialog(category))
            add_row = QHBoxLayout()
            add_row.setSpacing(10)
            add_row.addWidget(add)
            add_row.addStretch(1)
            panel_layout.addLayout(add_row)
            self.meal_add_rows[meal] = add_row
            self.meal_layout.addWidget(panel)
            self.meal_panels[meal] = panel
            self.meal_entries[meal] = entries
        self.meal_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self._install_shortcuts()
        self.refresh()

    def _install_shortcuts(self) -> None:
        """Keyboard navigation for the diary (active while the Diary page is showing)."""
        bindings = [
            ("Alt+Left", lambda: self.shift_date(-1)),
            ("Alt+Right", lambda: self.shift_date(1)),
            ("Ctrl+T", lambda: self.set_date(date.today().isoformat())),
            ("Ctrl+Shift+A", self.open_quick_add),
        ]
        bindings += [
            (f"Alt+{number}", lambda checked=False, category=meal: self.open_add_dialog(category))
            for number, meal in enumerate(MEALS, start=1)
        ]
        self._shortcuts = []
        for keys, action in bindings:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)
            self._shortcuts.append(shortcut)
        meals = ", ".join(f"Alt+{number} {meal}" for number, meal in enumerate(MEALS, start=1))
        self.date_picker.setToolTip(
            f"Choose the diary date. Alt+←/→ change day, Ctrl+T goes to today. Add food: {meals}"
        )

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

    def open_quick_add(self) -> None:
        """Type several entries, fix what was not understood on the review screen, then save them all."""
        dialog = QuickAddDialog(self.services, self.selected_date, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._review_table(dialog.csv_table(), quick=True)

    def add_catalogue_item(self, meal: str, item_id: str, amount_g: Decimal) -> DiaryEntry:
        entry = self.services.diary.add_item(self.selected_date, meal, item_id, amount_g)
        self.refresh()
        self.notify(f"Added {entry.display_name} to {meal}.")
        return entry

    def _request_import(self) -> None:
        """Every import button opens the same dialog, owned by the main window."""
        self.import_requested.emit()

    def import_diary_csv_text(self, text: str) -> None:
        """Import diary rows from CSV text that was pasted instead of chosen as a file."""
        try:
            table = self.services.diary_importer.read_text(text)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "CSV validation failed", str(error))
            return
        self._review_table(table)

    def import_diary_csv(self, filename: str) -> None:
        try:
            table = self.services.diary_importer.read(filename)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "CSV validation failed", str(error))
            return
        self._review_table(table)

    def _review_table(self, table: CsvTable, quick: bool = False) -> None:
        preview = preview_with_repair(
            self, table, self.services.diary_importer,
            error_title="Fix the quick add lines" if quick else "Fix the diary CSV",
            intro="Each row needs a food name and an amount; the meal is optional.",
        )
        if preview is None:
            return
        dialog = DiaryCsvReviewDialog(self.services, self.selected_date, preview, self, quick=quick)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.refresh()
        window = self.window()
        calendar_view = getattr(window, "calendar_view", None)
        if calendar_view is not None:
            calendar_view.refresh()
        count = len(dialog.imported_entries)
        self.notify(f"Added {count} diary entr{'y' if count == 1 else 'ies'} for {self.selected_date}.")

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
                hint.setStyleSheet("color: #8994a3; padding: 7px 0; font-size: 16px;")
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
            percent = self.macro_percents[key]
            if target:
                share = percent_of_target(nutrient, target)  # may be above 100 when the target is exceeded
                drift = load_drift(self.services.settings, key)
                on_track = is_on_track(share, drift)
                percent.setText(f"{share}%")
                percent.setProperty("onTrack", on_track)
                percent.setStyleSheet(
                    "font-size: 18px; font-weight: 650; color: " + ("#2f7a4d;" if on_track else "#b23b45;")
                )
                low, high = drift
                range_text = f"{low}%" if low == high else f"{low}% to {high}%"
                percent.setToolTip(
                    f"{share}% of the {names[key].lower()} target ({target:g} {unit}). "
                    f"Acceptable drift: {range_text}."
                )
            else:
                percent.setText("")
                percent.setToolTip("")

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
        label = QLabel(f"{entry.display_name}  ·  {format_entry_amount(entry)}")
        label.setWordWrap(True)
        nutrients = entry.nutrients
        details = QLabel(
            f"{nutrients.calories:.2f} kcal · "
            f"Protein {nutrients.protein:.2f}g · "
            f"Carbs {nutrients.carbohydrates:.2f}g · "
            f"Fat {nutrients.fat:.2f}g · "
            f"Fiber {nutrients.fiber:.2f}g"
        )
        details.setWordWrap(True)
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
        self.edit_amount_input = AmountSpinBox(entry.basis, float(entry.amount_g))
        self.edit_amount_input.setObjectName("editDiaryAmount")
        self.edit_amount_input.setAccessibleName(
            "Edit number of items" if entry.basis != BASIS_GRAMS else "Edit diary amount in grams"
        )
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
            entry.display_name, entry.amount_g, (MealPortion(entry.meal, entry.amount_g),), self, entry.unit
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
        self._show_undo(self._undo_entry.meal)
        self.refresh()
        self.notify("Entry deleted. Use Undo to restore it.", 5000)

    def undo_delete(self) -> None:
        if self._undo_entry is None:
            return
        self.services.diary.restore_entry(self._undo_entry)
        self._undo_entry = None
        self._hide_undo()
        self.refresh()
        self.notify("Deleted entry restored.")

    def _expire_undo(self) -> None:
        self._undo_entry = None
        self._hide_undo()

    def _show_undo(self, meal: str) -> None:
        """Put the undo button beside the meal's "Add food" button and start the winding-down line."""
        for row in self.meal_add_rows.values():
            row.removeWidget(self.undo_button)
        self.meal_add_rows[meal].insertWidget(1, self.undo_button)
        self.undo_button.set_countdown(1.0)
        self.undo_button.setVisible(True)
        self._undo_clock.start()
        self._undo_timer.start()
        self._undo_tick.start()

    def _hide_undo(self) -> None:
        self._undo_timer.stop()
        self._undo_tick.stop()
        self.undo_button.set_countdown(0.0)
        self.undo_button.setVisible(False)

    def _update_undo_line(self) -> None:
        remaining = 1.0 - self._undo_clock.elapsed() / UNDO_MS
        self.undo_button.set_countdown(remaining)
        if remaining <= 0:
            self._undo_tick.stop()
