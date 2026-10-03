from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QLabel,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.bootstrap import ApplicationServices
from calorie_tracker.infrastructure.diary_csv_exporter import export_diary_csv


class SettingsView(QWidget):
    TARGETS = (
        ("calories", "Calories", "kcal"),
        ("protein", "Protein", "g"),
        ("carbohydrates", "Carbohydrates", "g"),
        ("fat", "Fat", "g"),
        ("fiber", "Fiber", "g"),
    )

    def __init__(self, services: ApplicationServices, notify):
        super().__init__()
        self.services = services
        self.notify = notify
        self.setObjectName("mainContent")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 34, 40, 36)
        layout.setSpacing(15)
        heading = QLabel("Settings")
        heading.setStyleSheet("font-size: 26px; font-weight: 650; color: #172538;")
        layout.addWidget(heading)
        description = QLabel("Daily targets drive the progress bars on your Diary. Leave a value at \"Not set\" to hide its bar.")
        description.setStyleSheet("color: #738094;")
        layout.addWidget(description)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        form = QFormLayout()
        self.target_inputs: dict[str, QDoubleSpinBox] = {}
        current = services.settings.get_json("daily_targets") or {}
        for key, label, unit in self.TARGETS:
            control = QDoubleSpinBox()
            control.setObjectName(f"target{key.title()}")
            control.setAccessibleName(f"Daily {label.lower()} target")
            control.setRange(0, 100000)
            control.setDecimals(1)
            control.setSuffix(f" {unit}")
            control.setSpecialValueText("Not set")
            control.setValue(float(current.get(key, 0)))
            self.target_inputs[key] = control
            form.addRow(f"{label} target", control)
        card_layout.addLayout(form)
        save = QPushButton("Save targets")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.save_targets)
        card_layout.addWidget(save)
        layout.addWidget(card)
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

    def set_target(self, key: str, value: float) -> None:
        self.target_inputs[key].setValue(value)

    def save_targets(self) -> None:
        values = {
            key: float(control.value())
            for key, control in self.target_inputs.items()
            if control.value() > 0
        }
        self.services.settings.set_json("daily_targets", values)
        self.notify("Daily targets saved.")

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
            window.refresh_after_restore()
        self.reload_targets()
        return safety

    def reload_targets(self) -> None:
        current = self.services.settings.get_json("daily_targets") or {}
        for key, control in self.target_inputs.items():
            control.setValue(float(current.get(key, 0)))
