from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QCalendarWidget,
    QComboBox,
    QMenu,
    QTableView,
    QToolButton,
    QWidget,
)


_ASSETS = Path(__file__).resolve().parent / "assets"
_CLICKABLE_TYPES = (QAbstractButton, QAbstractItemView, QAbstractSpinBox, QComboBox, QMenu)


class _PointingCursorFilter(QObject):
    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Polish:
            _set_pointing_cursor(watched)
        return False


def _set_pointing_cursor(widget: QWidget) -> None:
    if not isinstance(widget, _CLICKABLE_TYPES):
        return
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if isinstance(widget, QAbstractItemView):
        widget.viewport().setCursor(Qt.CursorShape.PointingHandCursor)


def install_pointing_cursors(application: QApplication) -> None:
    """Use a hand cursor on buttons, menus, pickers, and selectable views app-wide."""
    cursor_filter = getattr(application, "_pointing_cursor_filter", None)
    if cursor_filter is None:
        cursor_filter = _PointingCursorFilter(application)
        application._pointing_cursor_filter = cursor_filter
        application.installEventFilter(cursor_filter)
    for widget in application.allWidgets():
        _set_pointing_cursor(widget)


def style_chevron_button(button: QToolButton, direction: str, label: str) -> None:
    """Give a navigation button a visible, scalable chevron and accessible label."""
    if direction not in {"left", "right"}:
        raise ValueError(f"Unsupported chevron direction: {direction}")
    button.setText("")
    button.setIcon(QIcon(str(_ASSETS / f"chevron-{direction}.svg")))
    button.setIconSize(QSize(16, 16))
    button.setAccessibleName(label)
    button.setToolTip(label)


def style_calendar_arrows(calendar: QCalendarWidget) -> None:
    """Replace the platform calendar arrows with larger, themed chevrons."""
    day_grid = calendar.findChild(QTableView)
    if day_grid is not None:
        day_grid.setMouseTracking(True)
        day_grid.viewport().setMouseTracking(True)
    controls = (
        ("qt_calendar_prevmonth", "left", "Previous month"),
        ("qt_calendar_nextmonth", "right", "Next month"),
    )
    for object_name, direction, label in controls:
        button = calendar.findChild(QToolButton, object_name)
        if button is None:
            continue
        style_chevron_button(button, direction, label)
    month_button = calendar.findChild(QToolButton, "qt_calendar_monthbutton")
    if month_button is not None:
        month_button.setAccessibleName("Choose calendar month")
        month_button.setToolTip("Choose month")
    year_button = calendar.findChild(QToolButton, "qt_calendar_yearbutton")
    if year_button is not None:
        year_button.setAccessibleName("Choose calendar year")
        year_button.setToolTip("Choose year")
