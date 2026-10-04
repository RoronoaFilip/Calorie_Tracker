from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from calorie_tracker.presentation.shortcuts_content import NOTE, shortcuts_html


class HelpView(QWidget):
    """Explains how to work with the app from the keyboard."""

    def __init__(self):
        super().__init__()
        self.setObjectName("mainContent")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("helpScroll")
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
        heading = QLabel("Help")
        heading.setStyleSheet("font-size: 26px; font-weight: 650; color: #172538;")
        layout.addWidget(heading)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        title = QLabel("Keyboard shortcuts")
        title.setStyleSheet("font-size: 18px; font-weight: 650;")
        card_layout.addWidget(title)
        self.shortcuts_label = QLabel(shortcuts_html())
        self.shortcuts_label.setObjectName("shortcutsText")
        self.shortcuts_label.setTextFormat(Qt.TextFormat.RichText)
        self.shortcuts_label.setWordWrap(True)
        self.shortcuts_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.shortcuts_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(self.shortcuts_label)
        note = QLabel(NOTE)
        note.setWordWrap(True)
        note.setStyleSheet("color: #536175;")
        card_layout.addWidget(note)
        layout.addWidget(card)
        layout.addStretch(1)
