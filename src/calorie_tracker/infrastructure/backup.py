from datetime import datetime
import os
from pathlib import Path
import sqlite3
import tempfile

from .database import Database, SCHEMA_VERSION


class BackupService:
    REQUIRED_TABLES = {
        "catalogue_items", "recipe_ingredients", "diary_entries", "preferences", "recent_foods"
    }

    def __init__(self, database: Database, safety_directory: Path | str):
        self.database = database
        self.safety_directory = Path(safety_directory)

    @staticmethod
    def _same_file(first: Path, second: Path) -> bool:
        return first.resolve() == second.resolve()

    @staticmethod
    def _read_only_uri(path: Path) -> str:
        return f"{path.resolve().as_uri()}?mode=ro"

    @classmethod
    def validate(cls, path: Path | str) -> None:
        source_path = Path(path)
        try:
            connection = sqlite3.connect(cls._read_only_uri(source_path), uri=True)
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                version = connection.execute("PRAGMA user_version").fetchone()
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if integrity is None or integrity[0] != "ok":
                    raise ValueError("SQLite integrity check failed.")
                if version is None or version[0] != SCHEMA_VERSION:
                    raise ValueError("Backup schema version is not supported.")
                if not cls.REQUIRED_TABLES.issubset(tables):
                    raise ValueError("Backup is missing required application tables.")
            finally:
                connection.close()
        except (OSError, sqlite3.Error, ValueError) as error:
            raise ValueError("Choose a valid Calorie Tracker backup database.") from error

    def export(self, destination: Path | str) -> Path:
        target = Path(destination)
        if self._same_file(target, self.database.path):
            raise ValueError("Choose a different file for the backup.")
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f"{target.stem}-", suffix=".tmp", dir=target.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with self.database.read_connection() as source:
                backup = sqlite3.connect(temporary)
                try:
                    source.backup(backup)
                finally:
                    backup.close()
            self.validate(temporary)
            os.replace(temporary, target)
            return target
        except sqlite3.Error as error:
            raise ValueError("Could not create a verified Calorie Tracker backup.") from error
        finally:
            temporary.unlink(missing_ok=True)

    def restore(self, source_path: Path | str) -> Path:
        source = Path(source_path)
        if self._same_file(source, self.database.path):
            raise ValueError("Choose a backup file different from the database currently in use.")
        self.validate(source)
        self.safety_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        safety_copy = self.safety_directory / f"before-restore-{timestamp}.sqlite3"
        self.export(safety_copy)
        try:
            backup = sqlite3.connect(self._read_only_uri(source), uri=True)
            try:
                live = sqlite3.connect(self.database.path)
                try:
                    live.execute("PRAGMA foreign_keys = ON")
                    backup.backup(live)
                finally:
                    live.close()
            finally:
                backup.close()
        except sqlite3.Error as error:
            raise ValueError("Could not restore the selected Calorie Tracker backup.") from error
        self.database.initialize()
        return safety_copy
