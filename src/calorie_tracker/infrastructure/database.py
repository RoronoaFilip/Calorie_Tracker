from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


SCHEMA_VERSION = 2

_SCHEMA = """
BEGIN EXCLUSIVE;
CREATE TABLE IF NOT EXISTS catalogue_items (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('food', 'recipe')),
    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    nutrients_json TEXT NOT NULL,
    basis TEXT NOT NULL DEFAULT 'g' CHECK (basis IN ('g', 'count')),
    recipe_yield_g TEXT,
    source_key TEXT UNIQUE,
    source_row INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_catalogue_normalized_name ON catalogue_items(normalized_name);
CREATE INDEX IF NOT EXISTS idx_catalogue_kind_active ON catalogue_items(kind, archived, name);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    recipe_id TEXT NOT NULL REFERENCES catalogue_items(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    food_id TEXT NOT NULL REFERENCES catalogue_items(id) ON DELETE RESTRICT,
    amount_g TEXT NOT NULL,
    PRIMARY KEY (recipe_id, position)
);
CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_food_id ON recipe_ingredients(food_id);

CREATE TABLE IF NOT EXISTS diary_entries (
    id TEXT PRIMARY KEY,
    diary_date TEXT NOT NULL,
    meal TEXT NOT NULL CHECK (meal IN ('Breakfast', 'Lunch', 'Dinner', 'Snacks')),
    catalogue_item_id TEXT REFERENCES catalogue_items(id) ON DELETE SET NULL,
    display_name TEXT NOT NULL,
    amount_g TEXT NOT NULL,
    basis TEXT NOT NULL DEFAULT 'g' CHECK (basis IN ('g', 'count')),
    nutrients_snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_diary_date ON diary_entries(diary_date);
CREATE INDEX IF NOT EXISTS idx_diary_date_meal ON diary_entries(diary_date, meal);

CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recent_foods (
    catalogue_item_id TEXT PRIMARY KEY REFERENCES catalogue_items(id) ON DELETE CASCADE,
    last_used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_recent_foods_used ON recent_foods(last_used_at DESC);
PRAGMA user_version = 2;
COMMIT;
"""

# Version 1 -> 2: foods can be counted per item instead of per 100 g. Existing rows stay per 100 g.
_MIGRATION_1_TO_2 = """
BEGIN EXCLUSIVE;
ALTER TABLE catalogue_items ADD COLUMN basis TEXT NOT NULL DEFAULT 'g' CHECK (basis IN ('g', 'count'));
ALTER TABLE diary_entries ADD COLUMN basis TEXT NOT NULL DEFAULT 'g' CHECK (basis IN ('g', 'count'));
PRAGMA user_version = 2;
COMMIT;
"""


class Database:
    """Creates connections on demand; importing this module never opens the database."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("Database schema is newer than this application.")
            if version == 0:
                connection.executescript(_SCHEMA)
            elif version == 1:
                connection.executescript(_MIGRATION_1_TO_2)
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def read_connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
