"""Read the catalogue one page at a time, straight from the database.

The Foods page asks for a page (a search text, an optional foods-only / recipes-only filter, a limit and an
offset) and keeps only what it shows, so a large catalogue is never loaded into memory in one go.
"""

from __future__ import annotations

from dataclasses import dataclass

from calorie_tracker.domain.nutrition import Nutrients
from .database import Database
from .repositories import _nutrients_from_json

KIND_ALL, KIND_FOOD, KIND_RECIPE = "all", "food", "recipe"
KINDS = (KIND_ALL, KIND_FOOD, KIND_RECIPE)


@dataclass(frozen=True)
class CatalogueRow:
    """One line of the catalogue. For recipes the nutrients are per 100 g; for foods, per 100 g or per item."""

    kind: str  # "food" or "recipe"
    id: str
    name: str
    basis: str  # "g" or "count"
    nutrients: Nutrients


def _like(query: str) -> str:
    escaped = query.strip().casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class CatalogueQuery:
    def __init__(self, database: Database):
        self.database = database

    def page(self, query: str = "", kind: str = KIND_ALL, limit: int = 15, offset: int = 0) -> list[CatalogueRow]:
        """Active foods and recipes whose name contains ``query``, ordered by name."""
        if kind not in KINDS:
            raise ValueError(f"Unknown catalogue filter: {kind!r}")
        with self.database.read_connection() as connection:
            rows = connection.execute(
                """SELECT kind, id, name, basis, nutrients_json FROM catalogue_items
                   WHERE archived=0 AND (?='all' OR kind=?) AND normalized_name LIKE ? ESCAPE '\\'
                   ORDER BY normalized_name, id LIMIT ? OFFSET ?""",
                (kind, kind, _like(query), limit, offset),
            ).fetchall()
        return [self._row(item) for item in rows]

    def archived_page(self, query: str = "", kind: str = KIND_ALL, limit: int = 15, offset: int = 0) -> list[CatalogueRow]:
        """Archived foods (flagged in the catalogue) and archived recipes (their own table), ordered by name."""
        if kind not in KINDS:
            raise ValueError(f"Unknown catalogue filter: {kind!r}")
        pattern = _like(query)
        with self.database.read_connection() as connection:
            rows = connection.execute(
                """SELECT * FROM (
                       SELECT 'food' AS kind, id, name, normalized_name, basis, nutrients_json
                       FROM catalogue_items WHERE kind='food' AND archived=1
                       UNION ALL
                       SELECT 'recipe', id, name, normalized_name, 'g', nutrients_json FROM archived_recipes
                   ) WHERE (?='all' OR kind=?) AND normalized_name LIKE ? ESCAPE '\\'
                   ORDER BY normalized_name, id LIMIT ? OFFSET ?""",
                (kind, kind, pattern, limit, offset),
            ).fetchall()
        return [self._row(item) for item in rows]

    @staticmethod
    def _row(item) -> CatalogueRow:
        return CatalogueRow(item["kind"], item["id"], item["name"], item["basis"], _nutrients_from_json(item["nutrients_json"]))
