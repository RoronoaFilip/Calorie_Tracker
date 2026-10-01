import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient, RecipePreview, preview_recipe
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

    def seed_foods(self, foods: tuple[tuple[Food, str, int], ...]) -> tuple[int, int, int]:
        imported = already_present = name_conflicts = 0
        with self.database.transaction() as connection:
            for food, source_key, source_row in foods:
                source_exists = connection.execute(
                    "SELECT 1 FROM catalogue_items WHERE source_key=?", (source_key,)
                ).fetchone()
                if source_exists:
                    already_present += 1
                    continue
                name_exists = connection.execute(
                    "SELECT 1 FROM catalogue_items WHERE normalized_name=?", (food.name.strip().casefold(),)
                ).fetchone()
                if name_exists:
                    name_conflicts += 1
                    continue
                connection.execute(
                    """INSERT INTO catalogue_items
                       (id, name, normalized_name, kind, archived, nutrients_json, source_key, source_row)
                       VALUES (?, ?, ?, 'food', ?, ?, ?, ?)""",
                    (food.id, food.name, food.name.strip().casefold(), int(not food.active),
                     _nutrients_to_json(food.nutrients_per_100g), source_key, source_row),
                )
                imported += 1
        return imported, already_present, name_conflicts

    def get(self, food_id: str) -> Food | None:
        with self.database.read_connection() as connection:
            row = connection.execute(
                "SELECT id, name, nutrients_json, archived FROM catalogue_items WHERE id=? AND kind='food'",
                (food_id,),
            ).fetchone()
        if row is None:
            return None
        return Food(row["id"], row["name"], _nutrients_from_json(row["nutrients_json"]), not bool(row["archived"]))

    def archive(self, food_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE catalogue_items SET archived=1, updated_at=CURRENT_TIMESTAMP WHERE id=? AND kind='food'",
                (food_id,),
            )

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


@dataclass(frozen=True)
class RecipeRecord:
    id: str
    draft: RecipeDraft
    per_100g: Nutrients
    active: bool


class RecipeRepository:
    def __init__(self, database: Database, foods: FoodRepository):
        self.database = database
        self.foods = foods

    def name_exists(self, name: str, excluding_id: str | None = None) -> bool:
        with self.database.read_connection() as connection:
            row = connection.execute(
                """SELECT 1 FROM catalogue_items WHERE kind='recipe' AND normalized_name=?
                   AND (? IS NULL OR id != ?) LIMIT 1""",
                (name.strip().casefold(), excluding_id, excluding_id),
            ).fetchone()
        return row is not None

    def save(self, recipe_id: str, draft: RecipeDraft, preview: RecipePreview) -> None:
        if preview.errors:
            raise ValueError("Cannot persist a recipe with validation errors.")
        with self.database.transaction() as connection:
            existing = connection.execute("SELECT kind FROM catalogue_items WHERE id=?", (recipe_id,)).fetchone()
            if existing is not None and existing["kind"] != "recipe":
                raise ValueError("The requested catalogue ID belongs to a basic food.")
            for ingredient in draft.ingredients:
                ingredient_row = connection.execute(
                    "SELECT kind, archived FROM catalogue_items WHERE id=?",
                    (ingredient.food.id,),
                ).fetchone()
                if ingredient_row is None or ingredient_row["kind"] != "food" or ingredient_row["archived"]:
                    raise ValueError(f"Ingredient is missing, archived, or is not a basic food: {ingredient.food.name}")
            connection.execute(
                """INSERT INTO catalogue_items
                   (id, name, normalized_name, kind, archived, nutrients_json, recipe_yield_g)
                   VALUES (?, ?, ?, 'recipe', 0, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                     normalized_name=excluded.normalized_name, archived=0,
                     nutrients_json=excluded.nutrients_json, recipe_yield_g=excluded.recipe_yield_g,
                     updated_at=CURRENT_TIMESTAMP""",
                (recipe_id, draft.name.strip(), draft.name.strip().casefold(),
                 _nutrients_to_json(preview.per_100g), str(draft.yield_g)),
            )
            connection.execute("DELETE FROM recipe_ingredients WHERE recipe_id=?", (recipe_id,))
            connection.executemany(
                "INSERT INTO recipe_ingredients(recipe_id, position, food_id, amount_g) VALUES (?, ?, ?, ?)",
                ((recipe_id, index, ingredient.food.id, str(ingredient.amount_g))
                 for index, ingredient in enumerate(draft.ingredients)),
            )

    def get(self, recipe_id: str) -> RecipeRecord | None:
        with self.database.read_connection() as connection:
            row = connection.execute(
                "SELECT id, name, recipe_yield_g, nutrients_json, archived FROM catalogue_items "
                "WHERE id=? AND kind='recipe'", (recipe_id,),
            ).fetchone()
            if row is None:
                return None
            ingredient_rows = connection.execute(
                """SELECT f.id, f.name, f.nutrients_json, f.archived, ri.amount_g
                   FROM recipe_ingredients ri JOIN catalogue_items f ON f.id=ri.food_id
                   WHERE ri.recipe_id=? ORDER BY ri.position""",
                (recipe_id,),
            ).fetchall()
        ingredients = tuple(
            RecipeIngredient(
                Food(item["id"], item["name"], _nutrients_from_json(item["nutrients_json"]), not bool(item["archived"])),
                Decimal(item["amount_g"]),
            )
            for item in ingredient_rows
        )
        draft = RecipeDraft(row["name"], Decimal(row["recipe_yield_g"]), ingredients)
        return RecipeRecord(
            row["id"], draft, _nutrients_from_json(row["nutrients_json"]), not bool(row["archived"])
        )

    def search(self, query: str = "", include_archived: bool = False) -> tuple[RecipeRecord, ...]:
        pattern = f"%{query.strip().casefold()}%"
        with self.database.read_connection() as connection:
            rows = connection.execute(
                """SELECT id FROM catalogue_items WHERE kind='recipe' AND (? OR archived=0)
                   AND normalized_name LIKE ? ORDER BY normalized_name, id""",
                (int(include_archived), pattern),
            ).fetchall()
        return tuple(record for row in rows if (record := self.get(row["id"])) is not None)

    def archive(self, recipe_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE catalogue_items SET archived=1, updated_at=CURRENT_TIMESTAMP WHERE id=? AND kind='recipe'",
                (recipe_id,),
            )
