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
from calorie_tracker.presentation.views.diary_view import DiaryView
from calorie_tracker.presentation.views.calendar_view import CalendarView
from calorie_tracker.presentation.views.settings_view import SettingsView


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

        self.diary_view = DiaryView(self.services, self.notify)
        self._stack.addWidget(self.diary_view)
        self.calendar_view = CalendarView(self.services, self._open_calendar_date)
        self._stack.addWidget(self.calendar_view)
        self.foods_view = FoodsView(self.services, self.notify)
        self._stack.addWidget(self.foods_view)
        self.settings_view = SettingsView(self.services, self.notify)
        self._stack.addWidget(self.settings_view)
        for index, (label, _, _) in enumerate(self.NAV_ITEMS):
            self._view_indexes[label] = index

        layout.addWidget(rail)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(root)
        self.setStyleSheet("""
            QWidget { color: #243041; }
            QMainWindow, QWidget#mainContent { background: #edf2f9; color: #243041; }
            QDialog { background: #e8eef7; color: #243041; }
            QWidget#navigationRail { background: #263752; border-right: 1px solid #1e2c43; }
            QLabel#brandLabel { color: #ffffff; font-size: 21px; font-weight: 700; }
            QLabel#privacyHint { color: #d0daea; font-size: 11px; }
            QLabel { background: transparent; color: #243041; }
            QPushButton { border: 0; border-radius: 10px; padding: 12px 13px; text-align: left;
                         background: #e2eaf6; color: #293a54; font-size: 14px; }
            QPushButton:hover { background: #d1def1; }
            QPushButton#navDiary, QPushButton#navCalendar, QPushButton#navFoods, QPushButton#navSettings {
                background: transparent; color: #d6e0ef; }
            QPushButton#navDiary:hover, QPushButton#navCalendar:hover, QPushButton#navFoods:hover,
            QPushButton#navSettings:hover { background: #344965; color: #ffffff; }
            QPushButton#navDiary:checked, QPushButton#navCalendar:checked, QPushButton#navFoods:checked,
            QPushButton#navSettings:checked { background: #506da4; color: #ffffff; font-weight: 600;
                                              border-left: 3px solid #b9d0ff; }
            QPushButton:focus { outline: 2px solid #7899d5; }
            QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit, QTableWidget, QListWidget {
                background: #f1f5fb; color: #243041; border: 1px solid #c2cede;
                border-radius: 7px; padding: 7px; min-height: 20px;
                selection-background-color: #dce6fb; selection-color: #243041; }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QDateEdit:focus {
                border: 1px solid #536fd1; }
            QComboBox QAbstractItemView { background: #f1f5fb; color: #243041;
                selection-background-color: #dce6fb; selection-color: #243041; }
            QHeaderView::section { background: #dfe8f5; color: #344154; border: 0; padding: 6px; }
            QCalendarWidget QWidget#qt_calendar_navigationbar { background: #dfe8f5; }
            QCalendarWidget QToolButton { color: #243041; background: transparent; }
            QCalendarWidget QTableView { background: #f1f5fb; color: #243041; gridline-color: #edf0f5;
                selection-background-color: #e3eaf9; selection-color: #243041; }
            QCalendarWidget QAbstractItemView:enabled { color: #243041; selection-background-color: #e3eaf9;
                selection-color: #243041; }
            QStatusBar { background: #dfe8f5; color: #344154; }
            QPushButton#primaryButton { background: #4f68c5; color: white; font-weight: 600; }
            QPushButton#primaryButton:hover { background: #4059b5; }
            QPushButton#dangerButton { color: #b53d48; }
            QFrame#card { background: #e5edf8; border: 1px solid #d1dceb; border-radius: 13px; }
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

    def _open_calendar_date(self, value: str) -> None:
        self.diary_view.set_date(value)
        self._select_view("Diary")

    def refresh_after_restore(self) -> None:
        self.diary_view.refresh()
        self.calendar_view.refresh()
        self.foods_view.refresh()

    def notify(self, message: str, timeout_ms: int = 3500) -> None:
        self.statusBar().showMessage(message, timeout_ms)
