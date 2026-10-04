from datetime import date

from PySide6.QtCore import QDate, QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.bootstrap import ApplicationServices
from calorie_tracker.presentation.control_styles import style_calendar_arrows


HEADER_BACKGROUND = "#a5b8d8"  # weekday names and week numbers: clearly darker than the date cells
HEADER_TEXT = "#14213d"
WEEKEND_RED = Qt.GlobalColor.red  # the colour Qt uses for Saturday and Sunday
OTHER_MONTH_BACKGROUND = "#dbe3f0"  # days of the previous/next month: darker than this month's cells, lighter than the headers
OTHER_MONTH_OPACITY = 0.5  # their numbers are drawn half transparent


class _HeaderDelegate(QStyledItemDelegate):
    """Paints the weekday-name row and the week-number column in a darker colour; dates are left to Qt.

    The style sheet used for the rest of the app would otherwise decide the colour of these cells.
    """

    def __init__(self, inner, grid: QTableView):
        super().__init__(grid)
        self._inner = inner  # Qt's own delegate, which draws the dates through ``paintCell``
        self._grid = grid

    def _is_header(self, index) -> bool:
        week_columns = self._grid.model().columnCount() - 7
        return index.row() == 0 or index.column() < week_columns

    def paint(self, painter: QPainter, option, index) -> None:
        if not self._is_header(index):
            self._inner.paint(painter, option, index)
            return
        painter.save()
        painter.fillRect(option.rect, QColor(HEADER_BACKGROUND))
        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        if isinstance(foreground, QBrush):
            colour = foreground.color()
        elif isinstance(foreground, QColor):
            colour = foreground
        else:
            colour = QColor(HEADER_TEXT)
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(colour)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, "" if text is None else str(text))
        painter.restore()

    def sizeHint(self, option, index):
        return self._inner.sizeHint(option, index)


class DiaryCalendarWidget(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._day_grid = self.findChild(QTableView)
        self._hovered_date: QDate | None = None
        self._hover_base_format: QTextCharFormat | None = None
        self._logged: frozenset[str] = frozenset()
        self._tracking_start: str | None = None
        # The weekday names row and the week-number column share one "header" format: a darker colour.
        header_format = QTextCharFormat()
        header_format.setBackground(QColor(HEADER_BACKGROUND))
        header_format.setForeground(QColor(HEADER_TEXT))
        header_format.setFontWeight(700)
        self.setHeaderTextFormat(header_format)
        if self._day_grid is not None:
            self._header_delegate = _HeaderDelegate(self._day_grid.itemDelegate(), self._day_grid)
            self._day_grid.setItemDelegate(self._header_delegate)
            self._day_grid.setMouseTracking(True)
            self._day_grid.viewport().setMouseTracking(True)
            self._day_grid.viewport().installEventFilter(self)

    def _in_shown_month(self, day: QDate | None) -> bool:
        return day is not None and day.month() == self.monthShown() and day.year() == self.yearShown()

    def eventFilter(self, watched, event) -> bool:
        if self._day_grid is not None and watched is self._day_grid.viewport():
            kind = event.type()
            if kind == QEvent.Type.MouseMove:
                day = self._date_at(event.position().toPoint())
                clickable = day is not None
                self._set_hovered_date(day)
                self._day_grid.viewport().setCursor(
                    Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor
                )
            elif kind == QEvent.Type.Leave:
                self._set_hovered_date(None)
            elif kind in (
                QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick,
            ):
                # Only dates can be clicked (this month's and the dimmed days of the neighbouring months),
                # not the weekday names or the week numbers.
                if self._date_at(event.position().toPoint()) is None:
                    return True
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

    def set_history(self, logged: frozenset[str], tracking_start: str | None) -> None:
        """Past days with entries get a green tick; past days since tracking began without any get a red cross."""
        self._logged = logged
        self._tracking_start = tracking_start
        self.updateCells()

    def day_status(self, day: QDate) -> str | None:
        """'logged', 'missed', or None (today, future, before tracking began, other months)."""
        if day.month() != self.monthShown() or day.year() != self.yearShown():
            return None
        if day >= QDate.currentDate():
            return None
        iso = day.toString("yyyy-MM-dd")
        if iso in self._logged:
            return "logged"
        if self._tracking_start is not None and iso >= self._tracking_start:
            return "missed"
        return None

    def _draw_status(self, painter: QPainter, rect, status: str) -> None:
        size = 14
        left, top = rect.right() - size - 7, rect.top() + 6
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if status == "logged":
            pen = QPen(QColor("#1f9d55"), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline([
                QPointF(left, top + size * 0.55), QPointF(left + size * 0.38, top + size * 0.9),
                QPointF(left + size, top + size * 0.1),
            ])
        else:
            pen = QPen(QColor("#d64545"), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(left + 1, top + 1), QPointF(left + size - 1, top + size - 1))
            painter.drawLine(QPointF(left + size - 1, top + 1), QPointF(left + 1, top + size - 1))
        painter.restore()

    def paintCell(self, painter: QPainter, rect, day: QDate) -> None:
        if self._in_shown_month(day):
            super().paintCell(painter, rect, day)
        else:
            # Days of the previous/next month: a darker shade, with the number half transparent. Still clickable.
            painter.save()
            painter.fillRect(rect, QColor(OTHER_MONTH_BACKGROUND))
            painter.setOpacity(OTHER_MONTH_OPACITY)
            super().paintCell(painter, rect, day)
            painter.restore()
        status = self.day_status(day)
        if status is not None:
            self._draw_status(painter, rect, status)
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
        description = QLabel("Choose a date to open that day.")
        description.setStyleSheet("color: #738094;")
        layout.addWidget(description)
        controls = QHBoxLayout()
        self.legend_label = QLabel(
            "<span style='color:#1f9d55; font-weight:700'>✓</span> logged &nbsp;&nbsp; "
            "<span style='color:#d64545; font-weight:700'>✕</span> missed &nbsp;&nbsp; "
            "<span style='color:#d64545'>●</span> today"
        )
        self.legend_label.setObjectName("calendarLegend")
        self.legend_label.setAccessibleName("Calendar legend: tick means logged, cross means missed, dot means today")
        controls.addWidget(self.legend_label)
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
            "Today has a red dot. A green tick marks past days with diary entries; a red cross marks past days with none since tracking began."
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
        self.calendar.set_history(self.populated_dates, self.services.diary.first_logged_date())
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())
        marker = QTextCharFormat()
        marker.setForeground(QColor("#4f68c5"))
        marker.setFontWeight(600)
        marker.setFontUnderline(True)
        weekend_marker = QTextCharFormat(marker)
        weekend_marker.setForeground(QColor(WEEKEND_RED))  # a logged Saturday or Sunday stays red
        for value in self.populated_dates:
            parsed = date.fromisoformat(value)
            day = QDate(parsed.year, parsed.month, parsed.day)
            self.calendar.setDateTextFormat(day, weekend_marker if day.dayOfWeek() >= 6 else marker)

    def _date_clicked(self, value: QDate) -> None:
        self.select_date(value.toString("yyyy-MM-dd"))

    def select_date(self, value: str) -> None:
        parsed = date.fromisoformat(value)
        selected = QDate(parsed.year, parsed.month, parsed.day)
        self.calendar.setSelectedDate(selected)
        self.on_date_selected(value)
