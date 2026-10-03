from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QCalendarWidget,
    QComboBox,
    QDialog,
    QMenu,
    QPushButton,
    QTableView,
    QToolButton,
    QWidget,
)


_ASSETS = Path(__file__).resolve().parent / "assets"
_CLICKABLE_TYPES = (QAbstractButton, QAbstractItemView, QAbstractSpinBox, QComboBox, QMenu)


CLOSE_DIALOG_SHORTCUT = "Ctrl+W"


class _PointingCursorFilter(QObject):
    """Polish-time app-wide behaviour: hand cursors, text-safe buttons, Ctrl+W on popups."""

    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.Polish:
            _set_pointing_cursor(watched)
            if isinstance(watched, QPushButton):
                fit_button_text(watched)
            elif isinstance(watched, QDialog):
                install_close_shortcut(watched)
        elif kind == QEvent.Type.Show and isinstance(watched, QPushButton):
            # By now the style sheet padding is applied, so the size hint is the real one.
            fit_button_text(watched)
        return False


def fit_button_text(button: QPushButton) -> None:
    """Never let layouts or table cells squeeze a button below the width of its label."""
    if not button.text():
        return
    hint = button.sizeHint().width()
    if hint > button.minimumWidth():
        button.setMinimumWidth(hint)


def install_close_shortcut(dialog: QDialog) -> None:
    """Make Ctrl+W close a popup dialog (never the main window, which is not a QDialog)."""
    if dialog.property("closeShortcutInstalled"):
        return
    dialog.setProperty("closeShortcutInstalled", True)
    shortcut = QShortcut(QKeySequence(CLOSE_DIALOG_SHORTCUT), dialog)
    shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
    shortcut.setObjectName("closeDialogShortcut")
    shortcut.activated.connect(dialog.reject)


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
