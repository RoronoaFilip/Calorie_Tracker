from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.bootstrap import ApplicationServices
from calorie_tracker.presentation.views.foods_view import FoodsView


class MainWindow(QMainWindow):
    NAV_ITEMS = (
        ("Diary", "◷", "Log food and review today's nutrition"),
        ("Calendar", "▦", "Browse diary history by date"),
        ("Foods", "◉", "Search and manage foods and recipes"),
        ("Settings", "⚙", "Set personal macro targets and preferences"),
    )

    def __init__(self, services: ApplicationServices):
        super().__init__()
        self.services = services
        self.setWindowTitle("Daily Plate · Calorie Tracker")
        self.setMinimumSize(1040, 680)
        self.resize(1280, 820)
        self._nav_buttons: dict[str, QPushButton] = {}
        self._stack = QStackedWidget()
        self._view_indexes: dict[str, int] = {}
        self._build_layout()
        self._select_view("Diary")
        self.statusBar().showMessage("Your nutrition data stays on this device.")

    def _build_layout(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        rail = QWidget()
        rail.setObjectName("navigationRail")
        rail.setFixedWidth(220)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(18, 26, 18, 20)
        rail_layout.setSpacing(12)
        brand = QLabel("Daily Plate\n<small>CALORIE TRACKER</small>")
        brand.setObjectName("brandLabel")
        brand.setAccessibleName("Daily Plate Calorie Tracker")
        rail_layout.addWidget(brand)
        rail_layout.addSpacing(22)

        for label, icon, tooltip in self.NAV_ITEMS:
            button = QPushButton(f"{icon}    {label}")
            button.setObjectName(f"nav{label}")
            button.setAccessibleName(label)
            button.setToolTip(tooltip)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=label: self._select_view(page))
            rail_layout.addWidget(button)
            self._nav_buttons[label] = button
        rail_layout.addStretch(1)
        privacy = QLabel("Local and private\nData stays on this computer")
        privacy.setObjectName("privacyHint")
        rail_layout.addWidget(privacy)

        self._stack.addWidget(self._placeholder("Diary", "Your day at a glance"))
        self._stack.addWidget(self._placeholder("Calendar", "Browse past days"))
        self._stack.addWidget(FoodsView(self.services, self.notify))
        self._stack.addWidget(self._placeholder("Settings", "Personal targets and local preferences"))
        for index, (label, _, _) in enumerate(self.NAV_ITEMS):
            self._view_indexes[label] = index

        layout.addWidget(rail)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(root)
        self.setStyleSheet("""
            QMainWindow, QWidget#mainContent { background: #f5f6f8; color: #243041; }
            QWidget#navigationRail { background: #ffffff; border-right: 1px solid #e4e8ee; }
            QLabel#brandLabel { color: #172538; font-size: 21px; font-weight: 700; }
            QLabel#privacyHint { color: #788495; font-size: 11px; }
            QPushButton { border: 0; border-radius: 10px; padding: 12px 13px; text-align: left;
                         background: transparent; color: #596577; font-size: 14px; }
            QPushButton:hover { background: #f2f5fb; }
            QPushButton:checked { background: #e9eefc; color: #3f5fc3; font-weight: 600;
                                  border-left: 3px solid #536fd1; }
            QPushButton:focus { outline: 2px solid #536fd1; }
            QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox { background: #ffffff; border: 1px solid #dbe1e9;
                border-radius: 7px; padding: 7px; min-height: 20px; }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border: 1px solid #536fd1; }
            QPushButton#primaryButton { background: #4f68c5; color: white; font-weight: 600; }
            QPushButton#primaryButton:hover { background: #4059b5; }
            QPushButton#dangerButton { color: #b53d48; }
            QFrame#card { background: #ffffff; border: 1px solid #e6e9ef; border-radius: 13px; }
        """)

    @staticmethod
    def _placeholder(title: str, message: str) -> QWidget:
        page = QWidget()
        page.setObjectName("mainContent")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(42, 38, 42, 36)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 26px; font-weight: 650; color: #172538;")
        layout.addWidget(heading)
        subheading = QLabel(message)
        subheading.setStyleSheet("font-size: 14px; color: #738094;")
        layout.addWidget(subheading)
        layout.addStretch(1)
        return page

    def _select_view(self, page: str) -> None:
        self._stack.setCurrentIndex(self._view_indexes[page])
        for label, button in self._nav_buttons.items():
            button.setChecked(label == page)

    def notify(self, message: str, timeout_ms: int = 3500) -> None:
        self.statusBar().showMessage(message, timeout_ms)
