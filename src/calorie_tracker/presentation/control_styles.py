from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QCalendarWidget, QToolButton


_ASSETS = Path(__file__).resolve().parent / "assets"


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
