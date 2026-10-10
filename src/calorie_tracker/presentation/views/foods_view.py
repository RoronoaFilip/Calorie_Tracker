import math
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
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
from calorie_tracker.application.catalogue import RecipeValidationError
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.infrastructure.catalogue_query import KIND_ALL, KIND_FOOD, KIND_RECIPE, CatalogueRow
from calorie_tracker.infrastructure.repositories import BasisInUseError, RecipeRecord
from calorie_tracker.presentation.control_styles import fit_button_text
from calorie_tracker.application.product_import import FOUND, OFFLINE
from calorie_tracker.infrastructure.open_food_facts import ATTRIBUTION
from calorie_tracker.presentation.csv_repair_flow import preview_with_repair
from calorie_tracker.presentation.dialogs.food_csv_review_dialog import FoodCsvReviewDialog
from calorie_tracker.presentation.dialogs.food_dialog import FoodDialog
from calorie_tracker.presentation.dialogs.recipe_dialog import RecipeDialog
from calorie_tracker.presentation.import_help import make_help_button
from calorie_tracker.presentation.formatting import basis_phrase, format_macros


OFFLINE_NOTICE = (
    "No internet connection: the barcode could not be looked up. "
    "Enter the nutrients by hand or try again when you are online."
)


class FoodsView(QWidget):
    edit_archive_buttons_font = "font-size: 26px;"
    ROW_HEIGHT = 72  # one catalogue row incl. spacing; used to size pages to the window
    MIN_PAGE_SIZE = 15
    SEARCH_DELAY_MS = 300
    import_requested = Signal()  # the main window opens the shared import dialog

    def __init__(self, services: ApplicationServices, notify):
        super().__init__()
        self.services = services
        self.notify = notify
        self._selected: tuple[str, str] | None = None
        self._kind = KIND_ALL
        self._archived = False
        self._offset = 0  # rows of the current search already shown
        self._exhausted = False
        self._loading = False
        self.setObjectName("mainContent")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 34, 40, 34)
        layout.setSpacing(15)

        heading = QLabel("Foods & recipes")
        heading.setStyleSheet("font-size: 26px; font-weight: 650; color: #172538;")
        layout.addWidget(heading)
        self.description_label = QLabel(
            "Build your local catalogue. Recipe yield and nutrition are calculated from ingredients."
        )
        self.description_label.setStyleSheet("color: #738094;")
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        actions = QHBoxLayout()
        self.add_food_button = QPushButton("Add food")
        self.add_food_button.setObjectName("primaryButton")
        self.create_recipe_button = QPushButton("Create recipe")
        self.create_recipe_button.setObjectName("primaryButton")
        self.import_button = QPushButton("Import files…")
        self.import_button.setObjectName("importFoodCsvButton")
        self.import_button.setAccessibleName("Import foods, diary entries or recipes from files, photos or a zip")
        self.import_button.setToolTip(
            "Import CSV files, barcode photos or zip files (Ctrl+O). "
            "You can also drop them anywhere in the app."
        )
        self.import_help_button = make_help_button(self)
        self.add_food_button.clicked.connect(self._add_food)
        self.create_recipe_button.clicked.connect(self._create_recipe)
        self.import_button.clicked.connect(self._request_import)
        actions.addWidget(self.add_food_button)
        actions.addWidget(self.create_recipe_button)
        actions.addStretch(1)
        actions.addWidget(self.import_help_button)
        actions.addWidget(self.import_button)
        layout.addLayout(actions)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search foods and recipes  (Ctrl+F)")
        self.search_input.setAccessibleName("Search foods and recipes")
        self.search_input.setAcceptDrops(False)  # let dropped CSVs reach the page
        search_row.addWidget(self.search_input, 1)
        self.kind_filter = QComboBox()
        self.kind_filter.setObjectName("catalogueKindFilter")
        self.kind_filter.setAccessibleName("Show foods, recipes or both")
        self.kind_filter.addItem("Foods and recipes", KIND_ALL)
        self.kind_filter.addItem("Only foods", KIND_FOOD)
        self.kind_filter.addItem("Only recipes", KIND_RECIPE)
        self.kind_filter.setToolTip("Filter the list: the database is queried again")
        self.kind_filter.currentIndexChanged.connect(self._kind_changed)
        search_row.addWidget(self.kind_filter)
        self.archived_button = QPushButton("Show archived")
        self.archived_button.setObjectName("showArchivedButton")
        self.archived_button.setCheckable(True)
        self.archived_button.setToolTip("List archived foods and recipes so they can be restored (Ctrl+Shift+A)")
        self.archived_button.toggled.connect(self._archived_toggled)
        search_row.addWidget(self.archived_button)
        layout.addLayout(search_row)
        # A short pause after the last key press, then the database is queried with the text.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(self.SEARCH_DELAY_MS)
        self._search_timer.timeout.connect(self.refresh)
        self.search_input.textChanged.connect(lambda _: self._search_timer.start())

        self.items = QListWidget()
        self.items.setAccessibleName("Food and recipe catalogue")
        self.items.setSpacing(4)
        self.items.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.items.itemSelectionChanged.connect(self._on_selection_changed)
        self.items.itemDoubleClicked.connect(lambda _: self._edit_selected())
        self.items.verticalScrollBar().valueChanged.connect(self._on_scrolled)
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
            (QKeySequence("Ctrl+Shift+A"), self.archived_button.toggle),
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
            if watched is self.items and key == Qt.Key.Key_Delete and self._selected is not None and not self._archived:
                kind, item_id = self._selected
                name = self.items.currentItem().toolTip().split(",")[0]
                self._archive_catalogue_item(kind, item_id, name)
                return True
        return super().eventFilter(watched, event)

    # ---- paged loading ----------------------------------------------------------------------------------

    def page_size(self) -> int:
        """Rows to fetch at once: enough to fill the visible list (a tall monitor needs more), at least 15."""
        height = self.items.viewport().height()
        visible = math.ceil(height / self.ROW_HEIGHT) if height > 0 else 0
        return max(self.MIN_PAGE_SIZE, visible + 2)

    def refresh(self) -> None:
        """Start again from the first page for the current search and filters (the database is queried)."""
        if self._search_timer.isActive():
            self._search_timer.stop()
        self._loading = True  # clearing resets the scroll bar, which must not trigger a page load
        try:
            self.items.clear()
        finally:
            self._loading = False
        self._selected = None
        self._offset = 0
        self._exhausted = False
        self._load_next_page()
        self._fill_viewport_later()

    def _load_next_page(self) -> None:
        if self._exhausted or self._loading:
            return
        self._loading = True
        try:
            limit = self.page_size()
            query = self.search_input.text()
            fetch = self.services.catalogue_query.archived_page if self._archived else self.services.catalogue_query.page
            rows = fetch(query, self._kind, limit, self._offset)
            for row in rows:
                self._add_row(row)
            self._offset += len(rows)
            if len(rows) < limit:
                self._exhausted = True
        finally:
            self._loading = False

    def _fill_viewport(self) -> None:
        """Keep loading pages while the list is too short to scroll, so a big window is filled from the start."""
        if self._exhausted or self._loading:
            return
        self.items.doItemsLayout()  # make the scroll bar range current before asking whether it can scroll
        if self.items.verticalScrollBar().maximum() == 0:
            self._load_next_page()
            self._fill_viewport_later()

    def _fill_viewport_later(self) -> None:
        QTimer.singleShot(0, self._fill_viewport)

    def _on_scrolled(self, value: int) -> None:
        """Scrolling near the bottom fetches the next page."""
        if value >= self.items.verticalScrollBar().maximum() - 2 * self.ROW_HEIGHT:
            self._load_next_page()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fill_viewport_later()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fill_viewport_later()

    def _kind_changed(self, _index: int) -> None:
        self._kind = self.kind_filter.currentData()
        self.refresh()

    def _archived_toggled(self, archived: bool) -> None:
        self._archived = archived
        self.archived_button.setText("Back to catalogue" if archived else "Show archived")
        self.description_label.setText(
            "Archived foods and recipes. Restore one to use it again; a recipe whose ingredients changed "
            "meanwhile opens so you can check it first."
            if archived else
            "Build your local catalogue. Recipe yield and nutrition are calculated from ingredients."
        )
        self.refresh()

    def _add_row(self, row: CatalogueRow) -> None:
        if row.kind == "food":
            detail = f"Basic food · {basis_phrase(row.basis)} · {format_macros(row.nutrients)}"
        else:
            detail = f"Recipe · per 100 g · {format_macros(row.nutrients)}"
        if self._archived:
            detail = "Archived · " + detail
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, (row.kind, row.id))
        item.setToolTip(f"{row.name}, {detail}")
        self.items.addItem(item)
        widget = self._make_catalogue_row(row.name, detail, row.kind, row.id)
        self.items.setItemWidget(item, widget)
        item.setSizeHint(widget.sizeHint())

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

        if self._archived:
            restore = QPushButton("Restore")
            restore.setObjectName("catalogueRestoreButton")
            restore.setAccessibleName(f"Restore {name}")
            restore.setToolTip("Put it back in the catalogue")
            restore.setProperty("compact", True)
            restore.clicked.connect(
                lambda checked=False, item_kind=kind, catalogue_id=item_id: self._restore_item(item_kind, catalogue_id)
            )
            fit_button_text(restore)
            row.restore_button = restore
            layout.addWidget(restore)
            return row

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
        edit.setVisible(False)  # shown on the selected row only
        archive.setVisible(False)
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
        if self._archived:
            self._restore_item(kind, item_id)
            return
        if kind == "food":
            food = self.services.foods.get(item_id)
            if food is None:
                return
            dialog = FoodDialog(self, food)
            if dialog.exec() == FoodDialog.DialogCode.Accepted:
                try:
                    self.services.foods.save(dialog.food())
                except BasisInUseError as error:
                    QMessageBox.warning(self, "Cannot change per 100 g / per item", str(error))
                    return
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
            self, "Archive catalogue item",
            f"Archive {name}? It moves to the archive (Show archived) and can be restored later. "
            "Existing diary history will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        repository = self.services.foods if kind == "food" else self.services.recipes
        repository.archive(item_id)
        self.refresh()
        self.notify(f"{name} archived.")

    def _restore_item(self, kind: str, item_id: str) -> None:
        """Bring an archived food or recipe back. A recipe whose ingredients changed is opened for review first."""
        if kind == "food":
            self.services.foods.restore(item_id)
            self.refresh()
            self.notify("Food restored.")
            return
        plan = self.services.catalogue.prepare_restore(item_id)
        if plan is None:
            self.refresh()
            return
        problems = list(plan.problems)
        if not plan.needs_review:
            try:
                self.services.catalogue.restore_recipe(item_id, plan.draft)
            except RecipeValidationError as error:
                problems = [message.message for message in error.preview.errors]
            else:
                self.refresh()
                self.notify(f"{plan.draft.name} restored.")
                return
        reasons = "\n".join(f"• {text}" for text in problems)
        QMessageBox.information(
            self, "Review the recipe before restoring",
            f"“{plan.draft.name}” cannot simply be put back, because things it uses changed while it was archived:"
            f"\n\n{reasons}\n\nThe recipe opens now so you can adjust it. It is restored when you save.",
        )
        record = RecipeRecord(item_id, plan.draft, Nutrients(), True)
        dialog = RecipeDialog(
            self.services.catalogue, self.services.foods, self, record,
            title="Review and restore recipe", confirm_text="Restore recipe",
        )
        if dialog.exec() != RecipeDialog.DialogCode.Accepted:
            return
        try:
            self.services.catalogue.restore_recipe(item_id, dialog.draft())
        except RecipeValidationError as error:
            QMessageBox.warning(self, "Recipe not restored", "\n".join(m.message for m in error.preview.errors))
            return
        self.refresh()
        self.notify(f"{plan.draft.name} restored.")

    def _request_import(self) -> None:
        """Every import button opens the same dialog, owned by the main window."""
        self.import_requested.emit()

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

    def import_csv_text(self, text: str) -> None:
        """Import CSV that was pasted as raw text instead of chosen as a file."""
        try:
            table = self.services.importer.read_text(text)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Import preview failed", str(error))
            return
        self._import_table(table)

    def import_csv(self, filename: str | Path) -> None:
        try:
            table = self.services.importer.read(filename)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Import preview failed", str(error))
            return
        self._import_table(table)

    def _import_table(self, table) -> None:
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
