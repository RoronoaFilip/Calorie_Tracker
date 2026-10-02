from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class CsvImportHelpDialog(QDialog):
    """Shows a valid CSV schema and example before the user selects a file."""

    def __init__(
        self,
        title: str,
        description: str,
        schema: str,
        example: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
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
