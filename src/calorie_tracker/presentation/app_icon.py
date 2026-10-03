from pathlib import Path

from PySide6.QtGui import QIcon

ICON_PATH = Path(__file__).resolve().parent / "assets" / "app_icon.png"


def load_app_icon() -> QIcon:
    """The application icon (window title bar, taskbar, Alt+Tab)."""
    return QIcon(str(ICON_PATH))
