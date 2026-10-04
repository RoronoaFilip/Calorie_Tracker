from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QLabel,
    QFileDialog,
    QScrollArea,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.bootstrap import ApplicationServices
from PySide6.QtWidgets import QDialog

from calorie_tracker.infrastructure.catalogue_csv_exporter import export_foods_csv, export_recipes_csv
from calorie_tracker.infrastructure.diary_csv_exporter import export_diary_csv
from calorie_tracker.infrastructure.recipe_csv_importer import RecipeCsvFormatError
from calorie_tracker.presentation.csv_repair_flow import preview_with_repair
from calorie_tracker.presentation.dialogs.csv_import_help_dialog import CsvImportHelpDialog
from calorie_tracker.presentation.dialogs.recipe_csv_review_dialog import RecipeCsvReviewDialog


class DataView(QWidget):
    """Manage your data: backups, the data folder, and CSV export/import of the diary, foods and recipes."""

    def __init__(self, services: ApplicationServices, notify):
        super().__init__()
        self.services = services
        self.notify = notify
        self.setObjectName("mainContent")
        # The whole page scrolls, so nothing is squeezed when the window is small.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("dataScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("settingsContent")
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 34, 40, 36)
        layout.setSpacing(15)
        heading = QLabel("Manage your data")
        heading.setStyleSheet("font-size: 26px; font-weight: 650; color: #172538;")
        layout.addWidget(heading)
        description = QLabel("Back up, move or share your diary, foods and recipes. Everything stays on this computer.")
        description.setStyleSheet("color: #738094;")
        description.setWordWrap(True)
        layout.addWidget(description)
        backup_card = QFrame()
        backup_card.setObjectName("card")
        backup_layout = QVBoxLayout(backup_card)
        backup_layout.addWidget(QLabel("Backup and restore"))
        backup_layout.addWidget(QLabel(
            "Backups contain your local foods, recipes, settings, and diary. Restoring creates a safety copy first."
        ))
        actions = QHBoxLayout()
        export = QPushButton("Export backup")
        export.clicked.connect(self._choose_export)
        restore = QPushButton("Restore backup")
        restore.clicked.connect(self._choose_restore)
        actions.addWidget(export)
        actions.addWidget(restore)
        actions.addStretch(1)
        backup_layout.addLayout(actions)
        layout.addWidget(backup_card)
        data_card = QFrame()
        data_card.setObjectName("card")
        data_layout = QVBoxLayout(data_card)
        data_layout.addWidget(QLabel("Your data"))
        self.data_folder = Path(self.services.database.path).parent
        self.data_folder_label = QLabel(f"Everything is stored on this computer in:\n{self.data_folder}")
        self.data_folder_label.setObjectName("dataFolderLabel")
        self.data_folder_label.setWordWrap(True)
        self.data_folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        data_layout.addWidget(self.data_folder_label)
        data_actions = QHBoxLayout()
        open_folder = QPushButton("Open data folder")
        open_folder.setObjectName("openDataFolderButton")
        open_folder.clicked.connect(self._open_data_folder)
        export_csv = QPushButton("Export diary to CSV")
        export_csv.setObjectName("exportDiaryCsvButton")
        export_csv.setToolTip("Save every diary entry with its nutrition to a spreadsheet-friendly CSV")
        export_csv.clicked.connect(self._choose_diary_export)
        data_actions.addWidget(open_folder)
        data_actions.addWidget(export_csv)
        data_actions.addStretch(1)
        data_layout.addLayout(data_actions)
        layout.addWidget(data_card)

        catalogue_card = QFrame()
        catalogue_card.setObjectName("card")
        catalogue_layout = QVBoxLayout(catalogue_card)
        catalogue_title = QLabel("Foods and recipes")
        catalogue_title.setStyleSheet("font-weight: 650;")
        catalogue_layout.addWidget(catalogue_title)
        catalogue_text = QLabel(
            "Export your catalogue to share it or move it to another computer. Foods go back in with "
            "“Import CSV or photo” on the Foods page; recipes can be imported here. "
            "Import foods first, because recipes refer to their ingredients by name."
        )
        catalogue_text.setWordWrap(True)
        catalogue_layout.addWidget(catalogue_text)
        catalogue_actions = QHBoxLayout()
        self.export_foods_button = QPushButton("Export foods to CSV")
        self.export_foods_button.setObjectName("exportFoodsCsvButton")
        self.export_foods_button.setToolTip("Save all basic foods (per 100 g or per item) to a CSV file")
        self.export_foods_button.clicked.connect(self._choose_foods_export)
        self.export_recipes_button = QPushButton("Export recipes to CSV")
        self.export_recipes_button.setObjectName("exportRecipesCsvButton")
        self.export_recipes_button.setToolTip("Save all recipes, one row per ingredient, to a CSV file")
        self.export_recipes_button.clicked.connect(self._choose_recipes_export)
        self.import_recipes_button = QPushButton("Import recipes from CSV")
        self.import_recipes_button.setObjectName("importRecipesCsvButton")
        self.import_recipes_button.setToolTip("Add recipes from a CSV file; existing recipes are never overwritten")
        self.import_recipes_button.clicked.connect(self._choose_recipe_import)
        for button in (self.export_foods_button, self.export_recipes_button, self.import_recipes_button):
            catalogue_actions.addWidget(button)
        catalogue_actions.addStretch(1)
        catalogue_layout.addLayout(catalogue_actions)
        layout.addWidget(catalogue_card)

        layout.addStretch(1)

    def _open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.data_folder)))

    def _choose_diary_export(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export diary to CSV", "diary-export.csv", "CSV files (*.csv)"
        )
        if filename:
            try:
                self.export_diary(filename)
            except OSError as error:
                QMessageBox.critical(self, "Export failed", str(error))

    def export_diary(self, filename: str) -> int:
        count = export_diary_csv(self.services.diary.all_entries(), filename)
        self.notify(f"Exported {count} diary entr{'y' if count == 1 else 'ies'} to {filename}.")
        return count

    # ---- foods and recipes ----------------------------------------------------------------------------

    def _choose_foods_export(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Export foods to CSV", "foods-export.csv", "CSV files (*.csv)")
        if filename:
            try:
                self.export_foods(filename)
            except OSError as error:
                QMessageBox.critical(self, "Export failed", str(error))

    def export_foods(self, filename: str) -> int:
        count = export_foods_csv(self.services.foods.search(), filename)
        self.notify(f"Exported {count} food{'' if count == 1 else 's'} to {filename}.")
        return count

    def _choose_recipes_export(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export recipes to CSV", "recipes-export.csv", "CSV files (*.csv)"
        )
        if filename:
            try:
                self.export_recipes(filename)
            except OSError as error:
                QMessageBox.critical(self, "Export failed", str(error))

    def export_recipes(self, filename: str) -> int:
        count = export_recipes_csv(self.services.recipes.search(), filename)
        self.notify(f"Exported {count} recipe{'' if count == 1 else 's'} to {filename}.")
        return count

    def _choose_recipe_import(self) -> None:
        help_dialog = CsvImportHelpDialog(
            "Import recipes from CSV",
            "Import recipes from a CSV with one row per ingredient. Ingredients are matched by name to the "
            "foods you already have, so import the foods first. Amounts are grams, or a number of items for "
            "foods counted per item. The final yield is optional when every ingredient is weighed. Recipes "
            "that already exist are skipped, never overwritten. Use “Export recipes to CSV” to see the format.",
            "recipe_name, yield_g, ingredient, amount",
            "Porridge,350,Oats,100",
            self,
            raw_header="recipe_name,yield_g,ingredient,amount",
        )
        if help_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if help_dialog.pasted_text:
            self.import_recipes_text(help_dialog.pasted_text)
            return
        filename = getattr(help_dialog, "dropped_path", None)
        if not filename:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Select recipe CSV", "", "CSV files (*.csv);;All files (*)"
            )
        if filename:
            self.import_recipes_csv(filename)

    def import_recipes_text(self, text: str) -> None:
        """Import recipes from CSV text that was pasted instead of chosen as a file."""
        try:
            table = self.services.recipe_importer.read_text(text)
        except (OSError, RecipeCsvFormatError) as error:
            QMessageBox.critical(self, "Recipe import failed", str(error))
            return
        self._import_recipe_table(table)

    def import_recipes_csv(self, filename: str) -> None:
        try:
            table = self.services.recipe_importer.read(filename)
        except (OSError, RecipeCsvFormatError) as error:
            QMessageBox.critical(self, "Recipe import failed", str(error))
            return
        self._import_recipe_table(table)

    def _import_recipe_table(self, table) -> None:
        importer = self.services.recipe_importer
        preview = preview_with_repair(
            self, table, importer, error_title="Fix the recipe CSV",
            intro="Each row needs a recipe name, an ingredient that exists in your foods, and an amount.",
        )
        if preview is None:
            return
        review = RecipeCsvReviewDialog(preview, self)
        if review.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.services.catalogue.import_recipes(tuple(item.draft for item in preview.ready))
        window = self.window()
        if hasattr(window, "refresh_after_restore"):
            window.refresh_after_restore()
        if result.failed:
            QMessageBox.warning(self, "Some recipes were not imported", "\n".join(
                f"{name}: {reason}" for name, reason in result.failed
            ))
        self.notify(f"Imported {result.imported} recipe{'' if result.imported == 1 else 's'}.")

    def _choose_export(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Calorie Tracker backup", "calorie-tracker-backup.sqlite3",
            "SQLite backup (*.sqlite3)",
        )
        if filename:
            try:
                self.export_backup(filename)
            except (OSError, ValueError) as error:
                QMessageBox.critical(self, "Backup failed", str(error))

    def export_backup(self, filename: str) -> None:
        path = self.services.backup.export(filename)
        self.notify(f"Backup exported to {path}.")

    def _choose_restore(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Calorie Tracker backup", "", "SQLite backup (*.sqlite3);;All files (*)"
        )
        if not filename:
            return
        answer = QMessageBox.warning(
            self, "Restore backup",
            "Restoring replaces the current catalogue, settings, and diary with the selected backup. "
            "A safety copy of the current database will be created first. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            safety = self.restore_backup(filename)
            QMessageBox.information(self, "Backup restored", f"Backup restored. Safety copy: {safety}")
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Restore failed", str(error))

    def restore_backup(self, filename: str):
        safety = self.services.backup.restore(filename)
        self.notify(f"Backup restored. Safety copy saved to {safety}.")
        window = self.window()
        if hasattr(window, "refresh_after_restore"):
            window.refresh_after_restore()  # also reloads the targets on the Settings page
        return safety

