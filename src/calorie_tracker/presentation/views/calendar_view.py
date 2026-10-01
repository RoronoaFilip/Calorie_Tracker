from datetime import date

from PySide6.QtCore import QDate, QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.bootstrap import ApplicationServices
from calorie_tracker.presentation.control_styles import style_calendar_arrows


class DiaryCalendarWidget(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._day_grid = self.findChild(QTableView)
        self._hovered_date: QDate | None = None
        self._hover_base_format: QTextCharFormat | None = None
        if self._day_grid is not None:
            self._day_grid.setMouseTracking(True)
            self._day_grid.viewport().setMouseTracking(True)
            self._day_grid.viewport().installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if self._day_grid is not None and watched is self._day_grid.viewport():
            if event.type() == QEvent.Type.MouseMove:
                self._set_hovered_date(self._date_at(event.position().toPoint()))
            elif event.type() == QEvent.Type.Leave:
                self._set_hovered_date(None)
        return super().eventFilter(watched, event)

    def _date_at(self, position) -> QDate | None:
        if self._day_grid is None:
            return None
        index = self._day_grid.indexAt(position)
        week_column_count = self._day_grid.model().columnCount() - 7
        weekday_column = index.column() - week_column_count
        date_row = index.row() - 1
        if not index.isValid() or date_row < 0 or not 0 <= weekday_column < 7:
            return None
        first_day = QDate(self.yearShown(), self.monthShown(), 1)
        offset = (first_day.dayOfWeek() - self.firstDayOfWeek().value + 7) % 7
        days_from_month_start = date_row * 7 + weekday_column - offset
        return first_day.addDays(days_from_month_start)

    def _set_hovered_date(self, value: QDate | None) -> None:
        if value == self._hovered_date:
            return
        if self._hovered_date is not None and self._hover_base_format is not None:
            self.setDateTextFormat(self._hovered_date, self._hover_base_format)
        self._hovered_date = value
        self._hover_base_format = None
        if value is not None:
            self._hover_base_format = QTextCharFormat(self.dateTextFormat(value))
            hover_format = QTextCharFormat(self._hover_base_format)
            hover_format.setBackground(QColor("#cbd9ee"))
            self.setDateTextFormat(value, hover_format)

    def paintCell(self, painter: QPainter, rect, day: QDate) -> None:
        super().paintCell(painter, rect, day)
        if day != QDate.currentDate():
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#d64545"))
        painter.drawEllipse(QRectF(rect.center().x() - 4, rect.bottom() - 11, 8, 8))
        painter.restore()


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
        self.calendar = DiaryCalendarWidget()
        style_calendar_arrows(self.calendar)
        self.calendar.setGridVisible(True)
        self.calendar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.calendar.setAccessibleName("Diary history calendar")
        self.calendar.setAccessibleDescription(
            "Today has a red dot. Underlined blue dates contain diary entries."
        )
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
        marker.setForeground(QColor("#4f68c5"))
        marker.setFontWeight(600)
        marker.setFontUnderline(True)
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
