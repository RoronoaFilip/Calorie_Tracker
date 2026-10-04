from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QCalendarWidget,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QTableView,
    QTextEdit,
    QToolButton,
    QWidget,
)


_ASSETS = Path(__file__).resolve().parent / "assets"
_CLICKABLE_TYPES = (QAbstractButton, QAbstractItemView, QAbstractSpinBox, QComboBox, QMenu)


CLOSE_DIALOG_SHORTCUT = "Ctrl+W"


def _inside_item_view(widget: QWidget) -> bool:
    """True for an in-cell editor (a line edit or spin box that lives inside a table or list)."""
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractItemView):
            return True
        parent = parent.parentWidget()
    return False


def _select_all_later(line_edit: QLineEdit) -> None:
    """Select the whole text once the click that focused the field has been handled."""
    def select() -> None:
        try:
            if line_edit.hasFocus() and not line_edit.isReadOnly():
                line_edit.selectAll()
        except RuntimeError:  # the field was deleted before this ran
            pass

    QTimer.singleShot(0, select)


def _handle_dialog_key(widget: QObject, event) -> bool:
    """Escape closes the pop-up; Enter submits dialogs that know how (``handle_enter``). True = handled."""
    if not isinstance(widget, QWidget) or event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier:
        return False
    if QApplication.activePopupWidget() is not None:  # a combo list, completer or calendar owns the key
        return False
    dialog = widget.window()
    if not isinstance(dialog, QDialog) or not dialog.isVisible():
        return False
    editing_cell = isinstance(widget, QLineEdit) and _inside_item_view(widget)
    if event.key() == Qt.Key.Key_Escape:
        if editing_cell or isinstance(widget, QDateTimeEdit):
            return False  # Escape first cancels the cell edit
        dialog.reject()
        return True
    if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        handler = getattr(dialog, "handle_enter", None)
        if handler is None or editing_cell or isinstance(widget, (QAbstractButton, QPlainTextEdit, QTextEdit)):
            return False
        return bool(handler(widget))
    return False


class _PointingCursorFilter(QObject):
    """App-wide behaviour: hand cursors, text-safe buttons, Escape/Ctrl+W on popups, Enter to submit,
    and select-all when a text field gets focus."""

    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.KeyPress:
            return _handle_dialog_key(watched, event)
        if kind == QEvent.Type.FocusIn:
            if isinstance(watched, QLineEdit) and not isinstance(watched.parentWidget(), QDateTimeEdit) \
                    and event.reason() not in (
                        Qt.FocusReason.PopupFocusReason, Qt.FocusReason.ActiveWindowFocusReason,
                    ):
                _select_all_later(watched)
            return False
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
