from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.bootstrap import ApplicationServices
from calorie_tracker.paths import seed_csv_path
from calorie_tracker.presentation.control_styles import fit_button_text
from calorie_tracker.application.product_import import FOUND, OFFLINE
from calorie_tracker.infrastructure.file_kinds import CSV, IMAGE, IMAGE_FILTER
from calorie_tracker.infrastructure.open_food_facts import ATTRIBUTION
from calorie_tracker.presentation.csv_repair_flow import preview_with_repair
from calorie_tracker.presentation.dialogs.csv_import_help_dialog import CsvImportHelpDialog
from calorie_tracker.presentation.dialogs.food_csv_review_dialog import FoodCsvReviewDialog
from calorie_tracker.presentation.dialogs.food_dialog import FoodDialog
from calorie_tracker.presentation.dialogs.recipe_dialog import RecipeDialog
from calorie_tracker.presentation.file_drop import FileDropMixin
from calorie_tracker.presentation.formatting import basis_phrase, format_macros


OFFLINE_NOTICE = (
    "No internet connection: the barcode could not be looked up. "
    "Enter the nutrients by hand or try again when you are online."
)


class FoodsView(FileDropMixin, QWidget):
    edit_archive_buttons_font = "font-size: 26px;"
    drop_kinds = frozenset({CSV, IMAGE})  # a CSV imports many foods, a barcode photo imports one

    def __init__(self, services: ApplicationServices, notify):
        super().__init__()
        self.init_file_drop()
        self.services = services
        self.notify = notify
        self._selected: tuple[str, str] | None = None
        self.setObjectName("mainContent")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 34, 40, 34)
        layout.setSpacing(15)

        heading = QLabel("Foods & recipes")
        heading.setStyleSheet("font-size: 26px; font-weight: 650; color: #172538;")
        layout.addWidget(heading)
        description = QLabel("Build your local catalogue. Recipe yield and nutrition are calculated from ingredients.")
        description.setStyleSheet("color: #738094;")
        layout.addWidget(description)

        actions = QHBoxLayout()
        self.add_food_button = QPushButton("Add food")
        self.add_food_button.setObjectName("primaryButton")
        self.create_recipe_button = QPushButton("Create recipe")
        self.create_recipe_button.setObjectName("primaryButton")
        self.import_button = QPushButton("Import CSV or photo")
        self.import_button.setObjectName("importFoodCsvButton")
        self.import_button.setAccessibleName("Import foods from a CSV file or a barcode photo")
        self.import_button.setToolTip(
            "Import foods from a CSV file, or one food from a photo of its barcode. "
            "You can also drop a CSV or a photo anywhere on this page."
        )
        self.add_food_button.clicked.connect(self._add_food)
        self.create_recipe_button.clicked.connect(self._create_recipe)
        self.import_button.clicked.connect(self._choose_import)
        actions.addWidget(self.add_food_button)
        actions.addWidget(self.create_recipe_button)
        actions.addStretch(1)
        actions.addWidget(self.import_button)
        layout.addLayout(actions)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search foods and recipes  (Ctrl+F)")
        self.search_input.setAccessibleName("Search foods and recipes")
        self.search_input.setAcceptDrops(False)  # let dropped CSVs reach the page
        layout.addWidget(self.search_input)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self.refresh)
        self.search_input.textChanged.connect(lambda _: self._search_timer.start())

        self.items = QListWidget()
        self.items.setAccessibleName("Food and recipe catalogue")
        self.items.setSpacing(4)
        self.items.itemSelectionChanged.connect(self._on_selection_changed)
        self.items.itemDoubleClicked.connect(lambda _: self._edit_selected())
        layout.addWidget(self.items, 1)
        self._install_shortcuts()
        self.refresh()

    # ---- keyboard ---------------------------------------------------------------------------------------

    def _install_shortcuts(self) -> None:
        """Ctrl+F (Cmd+F on macOS) searches; Ctrl+N adds a food; Ctrl+Shift+N creates a recipe; Enter edits."""
        bindings = (
            (QKeySequence(QKeySequence.StandardKey.Find), self.focus_search),
            (QKeySequence("Ctrl+N"), self._add_food),
            (QKeySequence("Ctrl+Shift+N"), self._create_recipe),
        )
        self._shortcuts = []
        for keys, action in bindings:
            shortcut = QShortcut(keys, self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)
            self._shortcuts.append(shortcut)
        self.items.installEventFilter(self)
        self.search_input.installEventFilter(self)

    def focus_search(self) -> None:
        """Put the cursor in the search box with its text selected, so typing starts a new search."""
        self.search_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_input.selectAll()

    def on_page_shown(self) -> None:
        """Called when the user navigates to this page: the search box is ready to type in."""
        self.focus_search()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if watched is self.search_input and key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.items.count():
                self.items.setFocus()
                if self.items.currentRow() < 0:
                    self.items.setCurrentRow(0)
                return True
            if watched is self.items and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._edit_selected()
                return True
            if watched is self.items and key == Qt.Key.Key_Delete and self._selected is not None:
                kind, item_id = self._selected
                name = self.items.currentItem().toolTip().split(",")[0]
                self._archive_catalogue_item(kind, item_id, name)
                return True
        return super().eventFilter(watched, event)

    def refresh(self) -> None:
        query = self.search_input.text() if hasattr(self, "search_input") else ""
        self.items.clear()
        records: list[tuple[str, str, str, str]] = []
        for food in self.services.foods.search(query):
            detail = f"Basic food · {basis_phrase(food.basis)} · {format_macros(food.nutrients_per_100g)}"
            records.append((food.name, "food", food.id, detail))
        for recipe in self.services.recipes.search(query):
            detail = f"Recipe · per 100 g · {format_macros(recipe.per_100g)}"
            records.append((recipe.draft.name, "recipe", recipe.id, detail))
        for name, kind, item_id, label in sorted(records, key=lambda value: value[0].casefold()):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, (kind, item_id))
            item.setToolTip(f"{name}, {label}")
            self.items.addItem(item)
            row = self._make_catalogue_row(name, label, kind, item_id)
            self.items.setItemWidget(item, row)
            item.setSizeHint(row.sizeHint())
        self._on_selection_changed()

    def _make_catalogue_row(self, name: str, detail: str, kind: str, item_id: str) -> QWidget:
        row = QWidget()
        row.setObjectName("catalogueRow")
        row.setMinimumHeight(64)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(8)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        name_label = QLabel(name)
        name_label.setStyleSheet("font-weight: 600; font-size: 18px;")
        detail_label = QLabel(detail)
        detail_label.setStyleSheet("font-size: 16px; color: #536175;")
        text_layout.addWidget(name_label)
        text_layout.addWidget(detail_label)
        layout.addLayout(text_layout, 1)

        edit = QPushButton("✎")
        edit.setStyleSheet(self.edit_archive_buttons_font)
        edit.setObjectName("catalogueEditButton")
        edit.setAccessibleName(f"Edit {name}")
        edit.setToolTip("Edit")
        edit.clicked.connect(lambda checked=False: self._edit_selected())
        archive = QPushButton("×")
        archive.setStyleSheet(self.edit_archive_buttons_font)
        archive.setObjectName("catalogueArchiveButton")
        archive.setAccessibleName(f"Archive {name}")
        archive.setToolTip("Archive")
        archive.clicked.connect(
            lambda checked=False, item_kind=kind, catalogue_id=item_id, item_name=name:
            self._archive_catalogue_item(item_kind, catalogue_id, item_name)
        )
        for button in (edit, archive):
            button.setProperty("compact", True)
            fit_button_text(button)
        row.edit_button = edit
        row.archive_button = archive
        layout.addWidget(edit)
        layout.addWidget(archive)
        return row

    def _on_selection_changed(self) -> None:
        item = self.items.currentItem()
        self._selected = item.data(Qt.ItemDataRole.UserRole) if item else None
        for index in range(self.items.count()):
            current = self.items.item(index)
            row = self.items.itemWidget(current)
            if row is None:
                continue
            selected = current is item
            row.setProperty("selected", selected)
            row.setStyleSheet(
                "QWidget#catalogueRow { background: #dce6fb; border-radius: 7px; }"
                if selected else "QWidget#catalogueRow { background: transparent; }"
            )
            for name in ("edit_button", "archive_button"):
                button = getattr(row, name, None)
                if button is not None:
                    button.setVisible(selected)

    def _add_food(self) -> None:
        dialog = FoodDialog(self)
        if dialog.exec() == FoodDialog.DialogCode.Accepted:
            self.services.foods.save(dialog.food())
            self.refresh()
            self.notify("Food saved.")

    def _create_recipe(self) -> None:
        dialog = RecipeDialog(self.services.catalogue, self.services.foods, self)
        if dialog.exec() == RecipeDialog.DialogCode.Accepted:
            self.services.catalogue.save_recipe(dialog.recipe_id, dialog.draft())
            self.refresh()
            self.notify("Recipe saved.")

    def _edit_selected(self) -> None:
        if self._selected is None:
            return
        kind, item_id = self._selected
        if kind == "food":
            food = self.services.foods.get(item_id)
            if food is None:
                return
            dialog = FoodDialog(self, food)
            if dialog.exec() == FoodDialog.DialogCode.Accepted:
                self.services.foods.save(dialog.food())
                self.refresh()
                self.notify("Food changes saved. Diary history keeps its original snapshot.")
            return
        recipe = self.services.recipes.get(item_id)
        if recipe is None:
            return
        dialog = RecipeDialog(self.services.catalogue, self.services.foods, self, recipe)
        if dialog.exec() == RecipeDialog.DialogCode.Accepted:
            self.services.catalogue.save_recipe(item_id, dialog.draft())
            self.refresh()
            self.notify("Recipe changes saved. Diary history keeps its original snapshot.")

    def _archive_catalogue_item(self, kind: str, item_id: str, name: str) -> None:
        answer = QMessageBox.question(
            self, "Archive catalogue item", f"Archive {name}? Existing diary history will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        repository = self.services.foods if kind == "food" else self.services.recipes
        repository.archive(item_id)
        self.refresh()
        self.notify(f"{name} archived.")

    def _choose_import(self) -> None:
        help_dialog = CsvImportHelpDialog(
            "Import foods from CSV",
            "Import many foods from a CSV: columns can appear in any order, with ',' ';' or tab separators. "
            "Include the food name, calories, protein, fat, and carbohydrates per 100 g. Fiber is optional.\n\n"
            "Or import one food from a photo of its barcode (JPEG, PNG, WebP…): the barcode is read on this "
            "computer, then the nutrients are looked up online and shown for you to check before saving. "
            "You can also drop a CSV or a photo anywhere on the Foods page.",
            "food_name, calories/100g, protein/100g, fat/100g, carbohydrates/100g, fiber/100g",
            "Oats,120,6,4,20,8",
            self,
            allow_photo=True,
        )
        if help_dialog.exec() != CsvImportHelpDialog.DialogCode.Accepted:
            return
        filename = getattr(help_dialog, "dropped_path", None)
        photo = getattr(help_dialog, "selected_kind", "csv") == "photo"
        if not filename and photo:
            filename, _ = QFileDialog.getOpenFileName(self, "Select barcode photo", "", IMAGE_FILTER)
        elif not filename:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Select food CSV", str(seed_csv_path()), "CSV files (*.csv);;All files (*)"
            )
        if not filename:
            return
        if photo:
            self.import_photo(filename)
        else:
            self.import_csv(filename)

    def handle_dropped_csv(self, path: str) -> None:
        """A .csv dropped on the Foods page goes straight to the review screen."""
        self.import_csv(path)

    def handle_dropped_image(self, path: str) -> None:
        """A photo dropped on the Foods page is read for a barcode and opens the food form to check."""
        self.import_photo(path)

    def import_photo(self, filename: str | Path) -> None:
        """Photo → barcode (offline) → product lookup (online) → food form. Nothing is saved until Save."""
        self.notify("Reading barcode…", 10_000)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self.services.product_import.import_photo(filename)
        finally:
            QApplication.restoreOverrideCursor()
        draft = result.draft_food()
        if draft is None:  # no usable barcode: there is nothing to prefill, so say why
            QMessageBox.warning(self, "Barcode photo", result.message)
            return
        message = f"{result.message}\n{ATTRIBUTION}" if result.status == FOUND else result.message
        if result.status == OFFLINE:
            self.notify(OFFLINE_NOTICE, 9_000)
            message = f"{OFFLINE_NOTICE}\n{result.message}"
        dialog = FoodDialog(
            self, imported_food=draft, title="Review scanned product",
            banner=("success" if result.found else "warning", message), image_path=str(filename),
        )
        if dialog.exec() != FoodDialog.DialogCode.Accepted:
            self.notify("Nothing was added.")
            return
        food = dialog.food()
        wanted = food.name.strip().casefold()
        if any(existing.name.strip().casefold() == wanted for existing in self.services.foods.search(food.name)):
            answer = QMessageBox.question(
                self, "Food already exists",
                f"A food named “{food.name}” is already in your catalogue. Add this one as well?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.notify("Nothing was added.")
                return
        self.services.foods.save(food)
        self.refresh()
        self.notify(f"{food.name} added to your foods.")

    def import_csv(self, filename: str | Path) -> None:
        try:
            table = self.services.importer.read(filename)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Import preview failed", str(error))
            return
        preview = preview_with_repair(
            self, table, self.services.importer, error_title="Fix the food CSV",
            intro="Each food needs a name plus calories, protein, fat and carbohydrates per 100 g.",
        )
        if preview is None:
            return
        review = FoodCsvReviewDialog(preview, self)
        if review.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.services.importer.apply(preview)
        corrected = 0
        skipped_conflicts = 0
        already_corrected = 0
        for invalid_food in preview.invalid_foods:
            dialog = FoodDialog(
                self,
                imported_food=invalid_food.food,
                correction_fields=invalid_food.fields_to_correct,
                correction_errors=invalid_food.errors,
            )
            if dialog.exec() != FoodDialog.DialogCode.Accepted:
                continue
            food = dialog.food()
            try:
                imported, already_present, name_conflicts = self.services.foods.seed_foods((
                    (food, invalid_food.source_key, invalid_food.source_row),
                ))
            except Exception as error:
                QMessageBox.critical(self, "Could not save corrected food", str(error))
                continue
            corrected += imported
            already_corrected += already_present
            skipped_conflicts += name_conflicts
            if name_conflicts:
                QMessageBox.warning(
                    self, "Food already exists",
                    f"{food.name} was not saved because a food with that name already exists.",
                )
        self.refresh()
        self.notify(
            f"Imported {result.imported} foods and saved {corrected} corrected rows; "
            f"{result.already_present + already_corrected} already present; "
            f"{result.name_conflicts + skipped_conflicts} name conflicts."
        )
