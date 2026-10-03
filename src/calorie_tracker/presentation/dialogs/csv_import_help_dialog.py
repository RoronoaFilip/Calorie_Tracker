from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from calorie_tracker.presentation.csv_drop import CsvDropMixin


class CsvImportHelpDialog(CsvDropMixin, QDialog):
    """Shows a valid CSV schema and example; a CSV can also be dropped straight onto it."""

    def __init__(
        self,
        title: str,
        description: str,
        schema: str,
        example: str,
        parent=None,
    ):
        super().__init__(parent)
        self.dropped_path: str | None = None
        self.init_csv_drop()
        self.setWindowTitle(title)
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        intro = QLabel(description)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        schema_title = QLabel("Supported header row")
        schema_title.setStyleSheet("font-weight: 650;")
        layout.addWidget(schema_title)
        schema_label = QLabel(schema)
        schema_label.setObjectName("csvImportSchema")
        schema_label.setAccessibleName("CSV import header example")
        schema_label.setWordWrap(True)
        layout.addWidget(schema_label)

        example_title = QLabel("Example row")
        example_title.setStyleSheet("font-weight: 650;")
        layout.addWidget(example_title)
        example_label = QLabel(example)
        example_label.setObjectName("csvImportExample")
        example_label.setAccessibleName("CSV import example row")
        example_label.setWordWrap(True)
        layout.addWidget(example_label)

        self.drop_zone = QLabel("⤓  Drag and drop a .csv file here to import it right away")
        self.drop_zone.setObjectName("csvDropZone")
        self.drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_zone.setMinimumHeight(64)
        layout.addWidget(self.drop_zone)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.choose_button = QPushButton("Choose CSV")
        self.choose_button.setObjectName("primaryButton")
        self.choose_button.setAccessibleName("Choose CSV file")
        self.choose_button.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(self.choose_button)
        layout.addLayout(actions)

    def handle_dropped_csv(self, path: str) -> None:
        self.dropped_path = path
        self.accept()
