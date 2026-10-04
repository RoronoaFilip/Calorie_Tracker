from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.infrastructure.file_kinds import CSV, IMAGE
from calorie_tracker.presentation.control_styles import fit_button_text
from calorie_tracker.presentation.file_drop import FileDropMixin


class CsvImportHelpDialog(FileDropMixin, QDialog):
    """Shows a valid CSV schema and example; a file can also be dropped straight onto it.

    With ``allow_photo`` the dialog also offers a barcode photo as the thing to import: ``selected_kind`` is
    then ``"csv"`` or ``"photo"``, and a dropped file's content decides which it was.

    With ``raw_header`` the dialog can switch to **raw input**: a text box, started with only that header row,
    where CSV text is pasted instead of choosing a file. Then ``pasted_text`` holds the text and
    ``selected_kind`` is ``"text"``.
    """

    def __init__(
        self,
        title: str,
        description: str,
        schema: str,
        example: str,
        parent=None,
        *,
        allow_photo: bool = False,
        raw_header: str | None = None,
    ):
        super().__init__(parent)
        self.dropped_path: str | None = None
        self.pasted_text: str | None = None
        self.raw_header = raw_header
        self.selected_kind = "csv"
        self.allow_photo = allow_photo
        self.drop_kinds = frozenset({CSV, IMAGE}) if allow_photo else frozenset({CSV})
        self.init_file_drop()
        self.setWindowTitle(title)
        self.setMinimumWidth(640 if allow_photo else 540)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
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

        drop_text = (
            "⤓  Drag and drop a .csv file or a photo of a barcode here"
            if allow_photo else "⤓  Drag and drop a .csv file here to import it right away"
        )
        self.drop_zone = QLabel(drop_text)
        self.drop_zone.setObjectName("csvDropZone")
        self.drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_zone.setWordWrap(True)
        self.drop_zone.setMinimumHeight(64)
        layout.addWidget(self.drop_zone)

        # Raw input: paste CSV text instead of choosing a file.
        self.raw_panel = QWidget()
        raw_layout = QVBoxLayout(self.raw_panel)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_title = QLabel("Paste the CSV text below. The first row is the header; add one row per line.")
        raw_title.setWordWrap(True)
        raw_layout.addWidget(raw_title)
        self.raw_input = QPlainTextEdit()
        self.raw_input.setObjectName("csvRawInput")
        self.raw_input.setAccessibleName("Raw CSV text")
        self.raw_input.setMinimumHeight(150)
        self.raw_input.setPlainText((raw_header + "\n") if raw_header else "")
        raw_layout.addWidget(self.raw_input)
        self.raw_panel.setVisible(False)
        layout.addWidget(self.raw_panel)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.raw_toggle: QPushButton | None = None
        if raw_header is not None:
            self.raw_toggle = QPushButton("Raw input")
            self.raw_toggle.setObjectName("rawInputToggle")
            self.raw_toggle.setCheckable(True)
            self.raw_toggle.setAccessibleName("Switch between choosing a file and pasting raw CSV text")
            self.raw_toggle.setToolTip("Paste CSV text instead of choosing a file")
            self.raw_toggle.toggled.connect(self._raw_toggled)
            actions.addWidget(self.raw_toggle)
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self.photo_button: QPushButton | None = None
        if allow_photo:
            self.photo_button = QPushButton("Choose barcode photo")
            self.photo_button.setObjectName("choosePhotoButton")
            self.photo_button.setAccessibleName("Choose a photo of a product barcode")
            self.photo_button.setToolTip("Read a product's barcode from a photo and look up its nutrients")
            self.photo_button.clicked.connect(self._choose_photo)
            actions.addWidget(self.photo_button)
        self.choose_button = QPushButton("Choose CSV")
        self.choose_button.setObjectName("primaryButton")
        self.choose_button.setAccessibleName("Choose CSV file")
        self.choose_button.clicked.connect(self._choose_csv)
        actions.addWidget(self.choose_button)
        self.use_text_button = QPushButton("Import pasted text")
        self.use_text_button.setObjectName("primaryButton")
        self.use_text_button.setAccessibleName("Import the pasted CSV text")
        self.use_text_button.clicked.connect(self._use_text)
        self.use_text_button.setVisible(False)
        actions.addWidget(self.use_text_button)
        layout.addLayout(actions)
        for button in self.findChildren(QPushButton):
            fit_button_text(button)
        for keys in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(keys), self, activated=self._use_text)

    def _raw_toggled(self, raw: bool) -> None:
        self.raw_panel.setVisible(raw)
        self.drop_zone.setVisible(not raw)
        self.choose_button.setVisible(not raw)
        self.use_text_button.setVisible(raw)
        if self.photo_button is not None:
            self.photo_button.setVisible(not raw)
        if raw:
            self.raw_input.setFocus()
            self.raw_input.moveCursor(QTextCursor.MoveOperation.End)

    def _use_text(self) -> None:
        text = self.raw_input.toPlainText()
        if self.raw_toggle is None or not self.raw_toggle.isChecked() or not text.strip():
            return
        self.pasted_text = text
        self.selected_kind = "text"
        self.accept()

    def _choose_csv(self) -> None:
        self.selected_kind = "csv"
        self.accept()

    def _choose_photo(self) -> None:
        self.selected_kind = "photo"
        self.accept()

    def handle_dropped_csv(self, path: str) -> None:
        self.dropped_path = path
        self.selected_kind = "csv"
        self.accept()

    def handle_dropped_image(self, path: str) -> None:
        self.dropped_path = path
        self.selected_kind = "photo"
        self.accept()
