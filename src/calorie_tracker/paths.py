"""Where bundled resources and the user's data live, in source runs and in a packaged .exe."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_FOLDER_NAME = "DailyPlate"
DATABASE_NAME = "calorie_tracker.sqlite3"


def is_frozen() -> bool:
    """True when running from a PyInstaller build."""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resource_root() -> Path:
    """Folder holding bundled read-only files such as the food seed CSV."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return project_root()


def seed_csv_path() -> Path:
    return resource_root() / "food_macros_seed.csv"


def user_data_dir() -> Path:
    """Writable folder for the database, logs and backups.

    Source runs keep using ``<project>/data``. A packaged exe uses a ``data`` folder next to
    the exe when one exists (portable mode); otherwise ``%LOCALAPPDATA%\\DailyPlate\\data``.
    """
    if not is_frozen():
        return project_root() / "data"
    portable = Path(sys.executable).resolve().parent / "data"
    if portable.is_dir():
        return portable
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_FOLDER_NAME / "data"


def default_database_path() -> Path:
    return user_data_dir() / DATABASE_NAME
