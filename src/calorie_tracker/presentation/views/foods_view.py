from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
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
from calorie_tracker.domain.recipes import Food
from calorie_tracker.presentation.dialogs.csv_import_help_dialog import CsvImportHelpDialog
from calorie_tracker.presentation.dialogs.food_dialog import FoodDialog
from calorie_tracker.presentation.dialogs.recipe_dialog import RecipeDialog


class FoodsView(QWidget):
    def __init__(self, services: ApplicationServices, notify):
        super().__init__()
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
        self.import_button = QPushButton("CSV Import")
        self.add_food_button.clicked.connect(self._add_food)
        self.create_recipe_button.clicked.connect(self._create_recipe)
        self.import_button.clicked.connect(self._choose_import)
        actions.addWidget(self.add_food_button)
        actions.addWidget(self.create_recipe_button)
        actions.addStretch(1)
        actions.addWidget(self.import_button)
        layout.addLayout(actions)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search foods and recipes")
        self.search_input.setAccessibleName("Search foods and recipes")
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
        self.refresh()

    def refresh(self) -> None:
        query = self.search_input.text() if hasattr(self, "search_input") else ""
        self.items.clear()
        records: list[tuple[str, str, str]] = []
        records.extend((food.name, "food", food.id) for food in self.services.foods.search(query))
        records.extend((recipe.draft.name, "recipe", recipe.id) for recipe in self.services.recipes.search(query))
        for name, kind, item_id in sorted(records, key=lambda value: value[0].casefold()):
            label = "Basic food · per 100 g" if kind == "food" else "Recipe · per 100 g"
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
        row.setMinimumHeight(58)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(8)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        name_label = QLabel(name)
        name_label.setStyleSheet("font-weight: 600;")
        detail_label = QLabel(detail)
        detail_label.setStyleSheet("font-size: 12px; color: #536175;")
        text_layout.addWidget(name_label)
        text_layout.addWidget(detail_label)
        layout.addLayout(text_layout, 1)

        edit = QPushButton("✎")
        edit.setObjectName("catalogueEditButton")
        edit.setAccessibleName(f"Edit {name}")
        edit.setToolTip("Edit")
        edit.clicked.connect(lambda checked=False: self._edit_selected())
        archive = QPushButton("×")
        archive.setObjectName("catalogueArchiveButton")
        archive.setAccessibleName(f"Archive {name}")
        archive.setToolTip("Archive")
        archive.clicked.connect(
            lambda checked=False, item_kind=kind, catalogue_id=item_id, item_name=name:
            self._archive_catalogue_item(item_kind, catalogue_id, item_name)
        )
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
            "Food CSV columns can appear in any order. Include the food name, calories, protein, fat, and carbohydrates per 100 g. Fiber is optional.",
            "food_name,calories / 100g,protein / 100g,fat / 100g,carbohydrates / 100g,fiber / 100g",
            "Oats,120,6,4,20,8",
            self,
        )
        if help_dialog.exec() != CsvImportHelpDialog.DialogCode.Accepted:
            return
        default_source = Path(__file__).resolve().parents[4] / "food_macros_seed.csv"
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select food CSV", str(default_source), "CSV files (*.csv);;All files (*)"
        )
        if filename:
            self.import_csv(filename)

    def import_csv(self, filename: str | Path) -> None:
        try:
            preview = self.services.importer.preview(filename)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Import preview failed", str(error))
            return
        report = preview.report
        details = (
            f"Rows read: {report.rows_read}\nFoods ready to import: {report.importable}\n"
            f"Ice cream rows excluded: {report.excluded_ice_cream_rows}\nDuplicate names: {report.duplicate_names}\n"
            f"Blank names: {report.blank_names}\nMalformed rows: {report.malformed_rows}\n"
            f"Rows needing correction: {len(preview.invalid_foods)}\n"
            f"Ignored columns: {', '.join(report.ignored_headers)}"
        )
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Review food import")
        box.setText(details + "\n\nAdd these foods to the catalogue? Existing foods will not be overwritten.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        correction_errors = tuple(
            message for invalid_food in preview.invalid_foods for message in invalid_food.errors
        )
        if correction_errors:
            box.setDetailedText("\n".join(correction_errors))
        answer = box.exec()
        if answer != QMessageBox.StandardButton.Yes:
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
