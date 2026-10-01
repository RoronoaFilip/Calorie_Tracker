from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.bootstrap import ApplicationServices


class CalendarView(QWidget):
    def __init__(self, services: ApplicationServices, on_date_selected):
        super().__init__()
        self.services = services
        self.on_date_selected = on_date_selected
        self.populated_dates: frozenset[str] = frozenset()
        self.setObjectName("mainContent")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 34, 40, 36)
        layout.setSpacing(15)
        heading = QLabel("Calendar history")
        heading.setStyleSheet("font-size: 26px; font-weight: 650; color: #172538;")
        layout.addWidget(heading)
        description = QLabel("Days with saved diary entries are highlighted. Choose a date to open that day.")
        description.setStyleSheet("color: #738094;")
        layout.addWidget(description)
        controls = QHBoxLayout()
        controls.addStretch(1)
        today = QPushButton("Today")
        today.setToolTip("Return to the current month")
        today.clicked.connect(self.show_today)
        controls.addWidget(today)
        layout.addLayout(controls)
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.calendar.setAccessibleName("Diary history calendar")
        self.calendar.setToolTip("Dates with diary entries are highlighted in blue")
        self.calendar.clicked.connect(self._date_clicked)
        self.calendar.currentPageChanged.connect(lambda _year, _month: self.refresh())
        layout.addWidget(self.calendar, 1)
        self.refresh()

    def set_month(self, year: int, month: int) -> None:
        self.calendar.setCurrentPage(year, month)
        self.refresh()

    def show_today(self) -> None:
        today = date.today()
        self.calendar.setCurrentPage(today.year, today.month)
        self.calendar.setSelectedDate(QDate(today.year, today.month, today.day))
        self.refresh()

    def refresh(self) -> None:
        year, month = self.calendar.yearShown(), self.calendar.monthShown()
        start = QDate(year, month, 1).toString("yyyy-MM-dd")
        end = QDate(year, month, QDate(year, month, 1).daysInMonth()).toString("yyyy-MM-dd")
        self.populated_dates = self.services.diary.populated_dates(start, end)
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())
        marker = QTextCharFormat()
        marker.setBackground(Qt.GlobalColor.cyan)
        marker.setForeground(Qt.GlobalColor.darkBlue)
        marker.setFontWeight(600)
        for value in self.populated_dates:
            parsed = date.fromisoformat(value)
            self.calendar.setDateTextFormat(QDate(parsed.year, parsed.month, parsed.day), marker)

    def _date_clicked(self, value: QDate) -> None:
        self.select_date(value.toString("yyyy-MM-dd"))

    def select_date(self, value: str) -> None:
        parsed = date.fromisoformat(value)
        selected = QDate(parsed.year, parsed.month, parsed.day)
        self.calendar.setSelectedDate(selected)
        self.on_date_selected(value)
