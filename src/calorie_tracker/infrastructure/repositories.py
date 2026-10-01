import json
import sqlite3
from decimal import Decimal
from typing import Any

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food
from .database import Database


def _nutrients_to_json(nutrients: Nutrients) -> str:
    return json.dumps({key: str(value) for key, value in nutrients.__dict__.items()})


def _nutrients_from_json(value: str) -> Nutrients:
    raw = json.loads(value)
    return Nutrients(**{key: Decimal(number) for key, number in raw.items()})


class FoodRepository:
    def __init__(self, database: Database):
        self.database = database

    def save(self, food: Food, source_key: str | None = None, source_row: int | None = None) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO catalogue_items
                   (id, name, normalized_name, kind, archived, nutrients_json, source_key, source_row)
                   VALUES (?, ?, ?, 'food', ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, normalized_name=excluded.normalized_name,
                     archived=excluded.archived, nutrients_json=excluded.nutrients_json,
                     updated_at=CURRENT_TIMESTAMP""",
                (food.id, food.name, food.name.strip().casefold(), int(not food.active),
                 _nutrients_to_json(food.nutrients_per_100g), source_key, source_row),
            )

    def get(self, food_id: str) -> Food | None:
        with self.database.read_connection() as connection:
            row = connection.execute(
                "SELECT id, name, nutrients_json, archived FROM catalogue_items WHERE id=? AND kind='food'",
                (food_id,),
            ).fetchone()
        if row is None:
            return None
        return Food(row["id"], row["name"], _nutrients_from_json(row["nutrients_json"]), not bool(row["archived"]))

    def search(self, query: str = "", include_archived: bool = False) -> tuple[Food, ...]:
        pattern = f"%{query.strip().casefold()}%"
        with self.database.read_connection() as connection:
            rows = connection.execute(
                """SELECT id, name, nutrients_json, archived FROM catalogue_items
                   WHERE kind='food' AND (? OR archived=0) AND normalized_name LIKE ?
                   ORDER BY normalized_name, id""",
                (int(include_archived), pattern),
            ).fetchall()
        return tuple(
            Food(row["id"], row["name"], _nutrients_from_json(row["nutrients_json"]), not bool(row["archived"]))
            for row in rows
        )


class SettingsRepository:
    def __init__(self, database: Database):
        self.database = database

    def set_json(self, key: str, value: Any) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO preferences(key, value_json) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                     updated_at=CURRENT_TIMESTAMP""",
                (key, json.dumps(value, ensure_ascii=False, separators=(",", ":"))),
            )

    def get_json(self, key: str) -> Any | None:
        with self.database.read_connection() as connection:
            row = connection.execute("SELECT value_json FROM preferences WHERE key=?", (key,)).fetchone()
        return None if row is None else json.loads(row["value_json"])
