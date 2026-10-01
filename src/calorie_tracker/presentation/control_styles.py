from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QCalendarWidget, QToolButton


def style_calendar_arrows(calendar: QCalendarWidget) -> None:
    """Replace the platform calendar arrows with larger, themed chevrons."""
    controls = (
        ("qt_calendar_prevmonth", "‹", "Previous month"),
        ("qt_calendar_nextmonth", "›", "Next month"),
    )
    for object_name, glyph, label in controls:
        button = calendar.findChild(QToolButton, object_name)
        if button is None:
            continue
        button.setIcon(QIcon())
        button.setText(glyph)
        button.setAccessibleName(label)
        button.setToolTip(label)
