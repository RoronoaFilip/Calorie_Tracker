from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from pathlib import Path

from calorie_tracker.bootstrap import ApplicationServices
from calorie_tracker.presentation.views.foods_view import FoodsView
from calorie_tracker.presentation.views.diary_view import DiaryView
from calorie_tracker.presentation.views.calendar_view import CalendarView
from calorie_tracker.presentation.views.data_view import DataView
from calorie_tracker.presentation.views.help_view import HelpView
from calorie_tracker.presentation.views.settings_view import SettingsView
from calorie_tracker.presentation.app_icon import load_app_icon
from calorie_tracker.presentation.control_styles import install_pointing_cursors


class MainWindow(QMainWindow):
    # (page key, icon, tooltip). "database" and "help" are drawn as vector icons; the others are symbols.
    NAV_ITEMS = (
        ("Diary", "◷", "Log food and review today's nutrition"),
        ("Calendar", "▦", "Browse diary history by date"),
        ("Foods", "◉", "Search and manage foods and recipes"),
        ("Data", "database", "Back up, export and import your diary, foods and recipes"),
        ("Settings", "⚙", "Set personal macro targets and preferences"),
        ("Help", "help", "Keyboard shortcuts and how to use the app"),
    )
    NAV_LABELS = {"Data": "Manage your data"}  # page key -> text on the button, when it differs

    def __init__(self, services: ApplicationServices):
        super().__init__()
        install_pointing_cursors(QApplication.instance())
        self.services = services
        self.setWindowTitle("Daily Plate · Calorie Tracker")
        self.setWindowIcon(load_app_icon())
        self.setMinimumSize(1040, 680)
        self.resize(1280, 820)
        self._nav_buttons: dict[str, QPushButton] = {}
        self._stack = QStackedWidget()
        self._view_indexes: dict[str, int] = {}
        self._build_layout()
        self._install_navigation_shortcuts()
        self._select_view("Diary")

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
        brand = QLabel("Daily Plate")
        brand.setObjectName("brandLabel")
        brand.setAccessibleName("Daily Plate Calorie Tracker")
        rail_layout.addWidget(brand)
        brand_subtitle = QLabel("CALORIE TRACKER")
        brand_subtitle.setObjectName("brandSubtitle")
        rail_layout.addWidget(brand_subtitle)
        rail_layout.addSpacing(22)

        for label, icon, tooltip in self.NAV_ITEMS:
            button = QPushButton(self.NAV_LABELS.get(label, label))
            button.setIcon(self._navigation_icon(icon))
            button.setIconSize(QSize(28, 28))
            button.setObjectName(f"nav{label}")
            button.setProperty("navButton", True)  # styled as a navigation entry whatever the page is called
            button.setAccessibleName(self.NAV_LABELS.get(label, label))
            button.setToolTip(tooltip)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=label: self._select_view(page))
            rail_layout.addWidget(button)
            self._nav_buttons[label] = button
        rail_layout.addStretch(1)
        privacy = QLabel("Local and private\nData stays on this computer")
        privacy.setObjectName("privacyHint")
        privacy.setWordWrap(True)
        rail_layout.addWidget(privacy)

        self.diary_view = DiaryView(self.services, self.notify)
        self._stack.addWidget(self.diary_view)
        self.calendar_view = CalendarView(self.services, self._open_calendar_date)
        self._stack.addWidget(self.calendar_view)
        self.foods_view = FoodsView(self.services, self.notify)
        self._stack.addWidget(self.foods_view)
        self.data_view = DataView(self.services, self.notify)
        self._stack.addWidget(self.data_view)
        self.settings_view = SettingsView(self.services, self.notify)
        self._stack.addWidget(self.settings_view)
        self.help_view = HelpView()
        self._stack.addWidget(self.help_view)
        for index, (label, _, _) in enumerate(self.NAV_ITEMS):
            self._view_indexes[label] = index

        layout.addWidget(rail)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(root)
        assets = Path(__file__).resolve().parent / "assets"
        arrow_down = (assets / "chevron-down.svg").as_posix()
        arrow_up = (assets / "chevron-up.svg").as_posix()
        stylesheet = """
            QWidget { color: #243041; font-size: 16px; }
            QMainWindow, QWidget#mainContent { background: #edf2f9; color: #243041; }
            QDialog { background: #e8eef7; color: #243041; }
            QWidget#navigationRail { background: #263752; border-right: 1px solid #1e2c43; }
            QLabel#brandLabel { color: #ffffff; font-size: 21px; font-weight: 700; }
            QLabel#brandSubtitle { color: #d6e0ef; font-size: 14px; font-weight: 700; letter-spacing: 1px; }
            QLabel#privacyHint { color: #d0daea; font-size: 14px; }
            QLabel { background: transparent; color: #243041; }
            /* Buttons: white fill + clear outline so they never melt into the tinted cards. */
            QPushButton { border: 1px solid #9db0cf; border-radius: 9px; padding: 9px 16px;
                         text-align: center; background: #ffffff; color: #243b61;
                         font-size: 16px; font-weight: 500; }
            QPushButton:hover { background: #eef3fc; border-color: #5f7fc0; }
            QPushButton:pressed { background: #dbe5f6; }
            QPushButton:focus { border: 1px solid #4f68c5; }
            QPushButton:disabled { background: #eef1f6; color: #8f9bb0; border-color: #d3dbe8; }
            QPushButton[compact="true"] { padding: 5px 12px; font-size: 16px; border-radius: 7px; }
            QPushButton#previousDayButton, QPushButton#nextDayButton {
                min-width: 44px; max-width: 44px; min-height: 42px; max-height: 42px;
                padding: 4px; text-align: center; font-size: 22px; font-weight: 600; }
            QPushButton[navButton="true"] {
                background: transparent; color: #d6e0ef; border: 2px solid transparent;
                text-align: left; padding: 12px 13px; font-weight: 400; }
            QPushButton[navButton="true"]:hover { background: #344965; color: #ffffff; }
            QPushButton[navButton="true"]:checked { background: #506da4; color: #ffffff; font-weight: 600;
                                                    border-left: 3px solid #b9d0ff; }
            QPushButton[navButton="true"]:focus { border-top: 2px solid #91abd8;
                border-right: 2px solid #91abd8; border-bottom: 2px solid #91abd8; }
            QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit, QTableWidget, QListWidget {
                background: #f1f5fb; color: #243041; border: 1px solid #c2cede;
                border-radius: 7px; padding: 7px; min-height: 22px; font-size: 16px;
                selection-background-color: #dce6fb; selection-color: #243041; }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QDateEdit:focus {
                border: 1px solid #536fd1; }
            QDateEdit { min-width: 175px; font-size: 16px; color: #172538; }
            QComboBox, QDateEdit { padding-right: 30px; }
            QComboBox::drop-down, QDateEdit::drop-down {
                subcontrol-origin: padding; subcontrol-position: right center; width: 30px;
                border-left: 1px solid #c2cede; background: #e2eaf6;
                border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
            QComboBox::down-arrow, QDateEdit::down-arrow {
                image: url("__ARROW_DOWN_URL__"); width: 14px; height: 10px; }
            QSpinBox, QDoubleSpinBox { padding-right: 29px; }
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border; width: 24px; border-left: 1px solid #c2cede;
                background: #e2eaf6; }
            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-position: top right; border-top-right-radius: 6px; }
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-position: bottom right; border-bottom-right-radius: 6px; }
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #d1def1; }
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                image: url("__ARROW_UP_URL__"); width: 14px; height: 10px; }
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                image: url("__ARROW_DOWN_URL__"); width: 14px; height: 10px; }
            QMenu { background: #f1f5fb; color: #243041; border: 1px solid #c2cede; padding: 4px; font-size: 16px; }
            QMenu::item { background: transparent; color: #243041; padding: 5px 18px; }
            QMenu::item:selected { background: #dce6fb; color: #243041; }
            QMenu::item:disabled { color: #738094; }
            QComboBox QAbstractItemView { background: #f1f5fb; color: #243041;
                selection-background-color: #dce6fb; selection-color: #243041; }
            QTableWidget { gridline-color: #d1dceb; }
            QHeaderView::section { background: #dfe8f5; color: #344154; border: 0; padding: 8px; font-size: 15px; }
            QTableCornerButton::section { background: #dfe8f5; border: 0; }
            QScrollArea { background: #edf2f9; border: 0; }
            QWidget#settingsContent { background: #edf2f9; }
            /* Scroll bars: a clearly coloured handle on a tinted track, so they are easy to see and grab. */
            QScrollBar:vertical { background: #d3deef; width: 16px; margin: 0; border-radius: 8px; }
            QScrollBar::handle:vertical { background: #3f5bbf; min-height: 40px; border-radius: 6px; margin: 2px; }
            QScrollBar::handle:vertical:hover { background: #324ba6; }
            QScrollBar::handle:vertical:pressed { background: #2a3f8c; }
            QScrollBar:horizontal { background: #d3deef; height: 16px; margin: 0; border-radius: 8px; }
            QScrollBar::handle:horizontal { background: #3f5bbf; min-width: 40px; border-radius: 6px; margin: 2px; }
            QScrollBar::handle:horizontal:hover { background: #324ba6; }
            QScrollBar::handle:horizontal:pressed { background: #2a3f8c; }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; background: none; border: 0; }
            QScrollBar::add-page, QScrollBar::sub-page { background: none; }
            QCalendarWidget QWidget#qt_calendar_navigationbar { background: #dfe8f5; }
            QCalendarWidget { background: #f1f5fb; border: 1px solid #c2cede; border-radius: 8px; }
            QCalendarWidget QToolButton { color: #405985; background: transparent; border: 0;
                border-radius: 7px; min-width: 34px; min-height: 32px; font-size: 20px; font-weight: 600; }
            QCalendarWidget QToolButton:hover { background: #cbd9ee; }
            QCalendarWidget QToolButton#qt_calendar_monthbutton,
            QCalendarWidget QToolButton#qt_calendar_yearbutton { padding-right: 12px; }
            QCalendarWidget QToolButton::menu-indicator {
                image: url("__ARROW_DOWN_URL__"); subcontrol-origin: padding;
                subcontrol-position: right center; width: 14px; height: 10px; }
            QCalendarWidget QTableView { background: #f1f5fb; color: #243041; gridline-color: #cbd6e5;
                border: 1px solid #c2cede; font-size: 16px;
                selection-background-color: #e3eaf9; selection-color: #243041; }
            QCalendarWidget QTableView::item { border: 1px solid #d5dfed; }
            QCalendarWidget QAbstractItemView:enabled { color: #243041; selection-background-color: #e3eaf9;
                selection-color: #243041; }
            QStatusBar { background: #dfe8f5; color: #344154; font-size: 15px; }
            QPushButton#primaryButton { background: #3f5bbf; color: #ffffff; border: 1px solid #334c9f;
                                       font-weight: 600; }
            QPushButton#primaryButton:hover { background: #324ba6; }
            QPushButton#primaryButton:pressed { background: #2a3f8c; }
            QPushButton#primaryButton:disabled { background: #b7c2e6; color: #f2f5fc; border-color: #aab6de; }
            QPushButton#importDiaryCsvButton, QPushButton#importFoodCsvButton, QPushButton#choosePhotoButton {
                background: #e6edff; color: #2c46a3; border: 1px solid #6f8be0; font-weight: 600; }
            QPushButton#importDiaryCsvButton:hover, QPushButton#importFoodCsvButton:hover,
            QPushButton#choosePhotoButton:hover { background: #d5e1ff; border-color: #4f68c5; }
            QPushButton#undoButton { background: #f4dde1; color: #7a3340; border: 1px solid #d3a2ab;
                                     padding-bottom: 12px; }
            QPushButton#undoButton:hover { background: #efcdd3; }
            QPushButton#addFoodButton { background: transparent; color: #34508f;
                                       border: 1px dashed #7f93b8; text-align: left; }
            QPushButton#addFoodButton:hover { background: #ffffff; border: 1px solid #5f7fc0; }
            QPushButton#dangerButton, QPushButton#catalogueArchiveButton {
                background: #ffffff; color: #b0303d; border: 1px solid #dd9aa1; }
            QPushButton#dangerButton:hover, QPushButton#catalogueArchiveButton:hover {
                background: #fdecee; border-color: #c4414f; }
            QPushButton#catalogueEditButton { color: #2f4a9a; }
            QWidget#mainContent[dropActive="true"] { background: #e1eaff; border: 2px dashed #4f68c5; }
            QDialog[dropActive="true"] { background: #dbe6ff; border: 2px dashed #4f68c5; }
            QLabel#csvDropZone { border: 2px dashed #7f93b8; border-radius: 10px; background: #f1f5fb;
                                color: #3d56a3; font-weight: 600; padding: 12px; }
            QCheckBox, QRadioButton { color: #243041; spacing: 8px; font-size: 16px; }
            QPlainTextEdit { background: #f1f5fb; color: #243041; border: 1px solid #c2cede; border-radius: 7px;
                             padding: 7px; font-size: 16px; }
            QPlainTextEdit:focus { border: 1px solid #536fd1; }
            QPushButton#quickAddButton { background: #e6edff; color: #2c46a3; border: 1px solid #6f8be0; font-weight: 600; }
            QPushButton#quickAddButton:hover { background: #d5e1ff; border-color: #4f68c5; }
            QWidget#catalogueRow { background: transparent; }
            QWidget#catalogueRow[selected="true"] { background: #dce6fb; border-radius: 7px; }
            QPushButton#recipeRemoveButton { min-height: 30px; padding: 5px 10px; }
            QFrame#card { background: #e5edf8; border: 1px solid #d1dceb; border-radius: 13px; }
            /* Banner on dialogs that show where prefilled data came from (info / success / warning). */
            QFrame#dialogBanner { background: #e6edff; border: 1px solid #b4c4ea; border-radius: 11px; }
            QFrame#dialogBanner[level="success"] { background: #e1f3e8; border-color: #9fd2b3; }
            QFrame#dialogBanner[level="warning"] { background: #fff0d2; border-color: #e5c176; }
            QLabel#dialogBannerText { font-size: 15px; color: #243041; }
            QLabel#foodPhotoPreview { background: #ffffff; border: 1px solid #c2cede; border-radius: 8px;
                                      color: #738094; }
            /* CSV repair popup */
            QLabel#csvRepairStatus { font-size: 16px; padding: 2px 0; }
            QListWidget#csvRepairIssues { background: #fbfcfe; padding: 4px; }
            QListWidget#csvRepairIssues::item { padding: 5px 8px; border-radius: 5px; color: #7d2630; }
            QListWidget#csvRepairIssues::item:selected { background: #fbe1e4; color: #5e1c24; }
        """
        self.setStyleSheet(
            stylesheet.replace("__ARROW_DOWN_URL__", arrow_down).replace("__ARROW_UP_URL__", arrow_up)
        )

    @staticmethod
    def _navigation_icon(glyph: str) -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colour = QColor("#d6e0ef")
        if glyph == "database":
            # A stack of disks: the usual "data" symbol.
            pen = QPen(colour, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(6, 4, 20, 8))
            for top in (8, 14, 20):
                painter.drawArc(QRectF(6, top, 20, 8), 180 * 16, 180 * 16)
            painter.drawLine(6, 8, 6, 24)
            painter.drawLine(26, 8, 26, 24)
        elif glyph == "help":
            # A question mark in a circle.
            painter.setPen(QPen(colour, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(4, 4, 24, 24))
            painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "?")
        else:
            painter.setPen(colour)
            painter.setFont(QFont("Segoe UI Symbol", 20))
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
        painter.end()
        return QIcon(pixmap)

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
        subheading.setStyleSheet("font-size: 16px; color: #738094;")
        layout.addWidget(subheading)
        layout.addStretch(1)
        return page

    def _install_navigation_shortcuts(self) -> None:
        """Ctrl+1…6 (Cmd on macOS) jump to the pages in the navigation; F1 opens Help."""
        self._navigation_shortcuts = []
        for number, (label, _icon, _tip) in enumerate(self.NAV_ITEMS, start=1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{number}"), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(lambda page=label: self._select_view(page))
            self._navigation_shortcuts.append(shortcut)
            self._nav_buttons[label].setToolTip(f"{_tip} (Ctrl+{number})")
        help_shortcut = QShortcut(QKeySequence("F1"), self)
        help_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        help_shortcut.activated.connect(lambda: self._select_view("Help"))
        self._navigation_shortcuts.append(help_shortcut)
        self._help_shortcut = help_shortcut

    def _select_view(self, page: str) -> None:
        self._stack.setCurrentIndex(self._view_indexes[page])
        if page == "Calendar" and hasattr(self, "calendar_view"):
            self.calendar_view.refresh()  # pick up entries added since it was last shown
        if page == "Foods" and hasattr(self, "foods_view"):
            self.foods_view.refresh()  # include anything imported elsewhere (e.g. recipes from Settings)
            self.foods_view.on_page_shown()
        for label, button in self._nav_buttons.items():
            button.setChecked(label == page)

    def _open_calendar_date(self, value: str) -> None:
        self.diary_view.set_date(value)
        self._select_view("Diary")

    def refresh_after_restore(self) -> None:
        self.diary_view.refresh()
        self.calendar_view.refresh()
        self.foods_view.refresh()
        self.settings_view.reload_targets()

    def notify(self, message: str, timeout_ms: int = 3500) -> None:
        self.statusBar().showMessage(message, timeout_ms)
