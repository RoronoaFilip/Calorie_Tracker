import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from calorie_tracker.domain.nutrition import Nutrients, check_basis
from calorie_tracker.domain.diary import DiaryEntry
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient, RecipePreview, preview_recipe
from .database import Database


def _nutrients_to_json(nutrients: Nutrients) -> str:
    return json.dumps({key: str(value) for key, value in nutrients.__dict__.items()})


def _nutrients_from_json(value: str) -> Nutrients:
    raw = json.loads(value)
    return Nutrients(**{key: Decimal(number) for key, number in raw.items()})


class BasisInUseError(ValueError):
    """A food's basis (per 100 g / per item) cannot change while recipes use it: their amounts would change meaning."""

    def __init__(self, food_name: str, recipe_names: tuple[str, ...]):
        shown = ", ".join(recipe_names[:5]) + (f" and {len(recipe_names) - 5} more" if len(recipe_names) > 5 else "")
        super().__init__(
            f"“{food_name}” is an ingredient of: {shown}. Changing between per 100 g and per item would change "
            "what those ingredient amounts mean, so edit or remove it in those recipes first. "
            "Diary history is not affected."
        )
        self.recipe_names = recipe_names


def _food_from_row(row: sqlite3.Row) -> Food:
    return Food(
        row["id"], row["name"], _nutrients_from_json(row["nutrients_json"]),
        not bool(row["archived"]), row["basis"],
    )


class FoodRepository:
    def __init__(self, database: Database):
        self.database = database

    def restore(self, food_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE catalogue_items SET archived=0, updated_at=CURRENT_TIMESTAMP WHERE id=? AND kind='food'",
                (food_id,),
            )

    def recipes_using(self, food_id: str) -> tuple[str, ...]:
        """Names of the recipes that have this food as an ingredient."""
        with self.database.read_connection() as connection:
            rows = connection.execute(
                """SELECT DISTINCT r.name FROM recipe_ingredients ri
                   JOIN catalogue_items r ON r.id=ri.recipe_id WHERE ri.food_id=? ORDER BY r.name""",
                (food_id,),
            ).fetchall()
        return tuple(row["name"] for row in rows)

    def save(self, food: Food, source_key: str | None = None, source_row: int | None = None) -> None:
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT basis FROM catalogue_items WHERE id=? AND kind='food'", (food.id,)
            ).fetchone()
            if existing is not None and existing["basis"] != check_basis(food.basis):
                used_in = connection.execute(
                    """SELECT DISTINCT r.name FROM recipe_ingredients ri
                       JOIN catalogue_items r ON r.id=ri.recipe_id WHERE ri.food_id=? ORDER BY r.name""",
                    (food.id,),
                ).fetchall()
                if used_in:
                    raise BasisInUseError(food.name, tuple(row["name"] for row in used_in))
            connection.execute(
                """INSERT INTO catalogue_items
                   (id, name, normalized_name, kind, archived, nutrients_json, basis, source_key, source_row)
                   VALUES (?, ?, ?, 'food', ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, normalized_name=excluded.normalized_name,
                     archived=excluded.archived, nutrients_json=excluded.nutrients_json,
                     basis=excluded.basis, updated_at=CURRENT_TIMESTAMP""",
                (food.id, food.name, food.name.strip().casefold(), int(not food.active),
                 _nutrients_to_json(food.nutrients_per_100g), check_basis(food.basis), source_key, source_row),
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
                       (id, name, normalized_name, kind, archived, nutrients_json, basis, source_key, source_row)
                       VALUES (?, ?, ?, 'food', ?, ?, ?, ?, ?)""",
                    (food.id, food.name, food.name.strip().casefold(), int(not food.active),
                     _nutrients_to_json(food.nutrients_per_100g), check_basis(food.basis), source_key, source_row),
                )
                imported += 1
        return imported, already_present, name_conflicts

    def get(self, food_id: str) -> Food | None:
        with self.database.read_connection() as connection:
            row = connection.execute(
                "SELECT id, name, nutrients_json, archived, basis FROM catalogue_items WHERE id=? AND kind='food'",
                (food_id,),
            ).fetchone()
        if row is None:
            return None
        return _food_from_row(row)

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
                """SELECT id, name, nutrients_json, archived, basis FROM catalogue_items
                   WHERE kind='food' AND (? OR archived=0) AND normalized_name LIKE ?
                   ORDER BY normalized_name, id""",
                (int(include_archived), pattern),
            ).fetchall()
        return tuple(_food_from_row(row) for row in rows)


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


@dataclass(frozen=True)
class ArchivedIngredient:
    """An ingredient as it was when the recipe was archived (the food may have changed since)."""

    food_id: str
    food_name: str
    basis: str
    amount_g: Decimal


@dataclass(frozen=True)
class ArchivedRecipe:
    id: str
    name: str
    yield_g: Decimal
    per_100g: Nutrients
    ingredients: tuple[ArchivedIngredient, ...]
    diary_entry_ids: tuple[str, ...]


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
            self._save_in(connection, recipe_id, draft, preview)

    @staticmethod
    def _save_in(connection: sqlite3.Connection, recipe_id: str, draft: RecipeDraft, preview: RecipePreview) -> None:
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
                """SELECT f.id, f.name, f.nutrients_json, f.archived, f.basis, ri.amount_g
                   FROM recipe_ingredients ri JOIN catalogue_items f ON f.id=ri.food_id
                   WHERE ri.recipe_id=? ORDER BY ri.position""",
                (recipe_id,),
            ).fetchall()
        ingredients = tuple(
            RecipeIngredient(
                _food_from_row(item),
                Decimal(item["amount_g"]),
            )
            for item in ingredient_rows
        )
        draft = RecipeDraft(row["name"], Decimal(row["recipe_yield_g"]), ingredients)
        return RecipeRecord(
            row["id"], draft, _nutrients_from_json(row["nutrients_json"]), not bool(row["archived"])
        )

    def search(self, query: str = "", include_archived: bool = False) -> tuple[RecipeRecord, ...]:
        """Recipes in the catalogue. Archived recipes live in their own table (see ``get_archived``)."""
        pattern = f"%{query.strip().casefold()}%"
        with self.database.read_connection() as connection:
            rows = connection.execute(
                """SELECT id FROM catalogue_items WHERE kind='recipe' AND archived=0
                   AND normalized_name LIKE ? ORDER BY normalized_name, id""",
                (pattern,),
            ).fetchall()
        return tuple(record for row in rows if (record := self.get(row["id"])) is not None)

    def archive(self, recipe_id: str) -> None:
        """Move a recipe out of the catalogue into the archive tables.

        The foods it used are no longer held by it, so they can be changed (e.g. from per 100 g to per item).
        Diary entries keep their own snapshot; the ids of the entries that pointed at the recipe are remembered
        so a restore can link them again.
        """
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT id, name, normalized_name, recipe_yield_g, nutrients_json FROM catalogue_items "
                "WHERE id=? AND kind='recipe'", (recipe_id,),
            ).fetchone()
            if row is None:
                return
            diary_ids = [
                entry["id"] for entry in
                connection.execute("SELECT id FROM diary_entries WHERE catalogue_item_id=?", (recipe_id,))
            ]
            connection.execute("DELETE FROM archived_recipes WHERE id=?", (recipe_id,))
            connection.execute(
                """INSERT INTO archived_recipes
                   (id, name, normalized_name, recipe_yield_g, nutrients_json, diary_entry_ids)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (row["id"], row["name"], row["normalized_name"], row["recipe_yield_g"] or "0",
                 row["nutrients_json"], ",".join(diary_ids)),
            )
            connection.execute(
                """INSERT INTO archived_recipe_ingredients (recipe_id, position, food_id, food_name, basis, amount_g)
                   SELECT ri.recipe_id, ri.position, ri.food_id, f.name, f.basis, ri.amount_g
                   FROM recipe_ingredients ri JOIN catalogue_items f ON f.id=ri.food_id
                   WHERE ri.recipe_id=?""",
                (recipe_id,),
            )
            connection.execute("DELETE FROM recipe_ingredients WHERE recipe_id=?", (recipe_id,))
            connection.execute("DELETE FROM recent_foods WHERE catalogue_item_id=?", (recipe_id,))
            connection.execute("UPDATE diary_entries SET catalogue_item_id=NULL WHERE catalogue_item_id=?", (recipe_id,))
            connection.execute("DELETE FROM catalogue_items WHERE id=?", (recipe_id,))

    def get_archived(self, recipe_id: str) -> ArchivedRecipe | None:
        with self.database.read_connection() as connection:
            row = connection.execute(
                "SELECT id, name, recipe_yield_g, nutrients_json, diary_entry_ids FROM archived_recipes WHERE id=?",
                (recipe_id,),
            ).fetchone()
            if row is None:
                return None
            ingredient_rows = connection.execute(
                """SELECT food_id, food_name, basis, amount_g FROM archived_recipe_ingredients
                   WHERE recipe_id=? ORDER BY position""",
                (recipe_id,),
            ).fetchall()
        return ArchivedRecipe(
            row["id"], row["name"], Decimal(row["recipe_yield_g"]), _nutrients_from_json(row["nutrients_json"]),
            tuple(
                ArchivedIngredient(item["food_id"], item["food_name"], item["basis"], Decimal(item["amount_g"]))
                for item in ingredient_rows
            ),
            tuple(value for value in row["diary_entry_ids"].split(",") if value),
        )

    def restore(self, recipe_id: str, draft: RecipeDraft, preview: RecipePreview) -> None:
        """Put an archived recipe back in the catalogue (with the given, checked draft) and leave the archive."""
        if preview.errors:
            raise ValueError("Cannot persist a recipe with validation errors.")
        with self.database.transaction() as connection:
            archived = connection.execute(
                "SELECT diary_entry_ids FROM archived_recipes WHERE id=?", (recipe_id,)
            ).fetchone()
            if archived is None:
                raise KeyError(f"Archived recipe not found: {recipe_id}")
            self._save_in(connection, recipe_id, draft, preview)
            for entry_id in (value for value in archived["diary_entry_ids"].split(",") if value):
                connection.execute(
                    "UPDATE diary_entries SET catalogue_item_id=? WHERE id=? AND catalogue_item_id IS NULL",
                    (recipe_id, entry_id),
                )
            connection.execute("DELETE FROM archived_recipe_ingredients WHERE recipe_id=?", (recipe_id,))
            connection.execute("DELETE FROM archived_recipes WHERE id=?", (recipe_id,))


class DiaryRepository:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _entry_from_row(row: sqlite3.Row) -> DiaryEntry:
        return DiaryEntry(
            row["id"], row["diary_date"], row["meal"], row["catalogue_item_id"],
            row["display_name"], Decimal(row["amount_g"]),
            _nutrients_from_json(row["nutrients_snapshot_json"]), row["basis"],
        )

    def add(self, entry: DiaryEntry) -> None:
        self.add_many((entry,))

    @staticmethod
    def _insert(connection: sqlite3.Connection, entry: DiaryEntry) -> None:
        connection.execute(
            """INSERT INTO diary_entries
               (id, diary_date, meal, catalogue_item_id, display_name, amount_g, basis, nutrients_snapshot_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (entry.id, entry.diary_date, entry.meal, entry.catalogue_item_id, entry.display_name,
             str(entry.amount_g), check_basis(entry.basis), _nutrients_to_json(entry.nutrients_per_100g)),
        )
        if entry.catalogue_item_id is not None:
            connection.execute(
                """INSERT INTO recent_foods(catalogue_item_id, last_used_at) VALUES (?, CURRENT_TIMESTAMP)
                   ON CONFLICT(catalogue_item_id) DO UPDATE SET last_used_at=CURRENT_TIMESTAMP""",
                (entry.catalogue_item_id,),
            )

    def add_many(self, entries: tuple[DiaryEntry, ...]) -> None:
        if not entries:
            return
        with self.database.transaction() as connection:
            for entry in entries:
                self._insert(connection, entry)

    def replace(self, entry_id: str, entries: tuple[DiaryEntry, ...]) -> None:
        """Atomically delete one entry and insert its replacements."""
        with self.database.transaction() as connection:
            cursor = connection.execute("DELETE FROM diary_entries WHERE id=?", (entry_id,))
            if cursor.rowcount != 1:
                raise KeyError(f"Diary entry not found: {entry_id}")
            for entry in entries:
                self._insert(connection, entry)

    def first_date(self) -> str | None:
        with self.database.read_connection() as connection:
            row = connection.execute("SELECT MIN(diary_date) AS first FROM diary_entries").fetchone()
        return row["first"] if row is not None else None

    def all_entries(self) -> tuple[DiaryEntry, ...]:
        with self.database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM diary_entries ORDER BY diary_date, rowid"
            ).fetchall()
        return tuple(self._entry_from_row(row) for row in rows)

    def get(self, entry_id: str) -> DiaryEntry | None:
        with self.database.read_connection() as connection:
            row = connection.execute("SELECT * FROM diary_entries WHERE id=?", (entry_id,)).fetchone()
        return None if row is None else self._entry_from_row(row)

    def entries_on(self, diary_date: str) -> tuple[DiaryEntry, ...]:
        with self.database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM diary_entries WHERE diary_date=? ORDER BY rowid", (diary_date,)
            ).fetchall()
        return tuple(self._entry_from_row(row) for row in rows)

    def update_amount(self, entry: DiaryEntry) -> None:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """UPDATE diary_entries SET amount_g=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (str(entry.amount_g), entry.id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Diary entry not found: {entry.id}")

    def delete(self, entry_id: str) -> DiaryEntry | None:
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM diary_entries WHERE id=?", (entry_id,)).fetchone()
            if row is None:
                return None
            connection.execute("DELETE FROM diary_entries WHERE id=?", (entry_id,))
        return self._entry_from_row(row)

    def restore(self, entry: DiaryEntry) -> None:
        self.add(entry)

    def populated_dates(self, start_date: str, end_date: str) -> frozenset[str]:
        with self.database.read_connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT diary_date FROM diary_entries WHERE diary_date BETWEEN ? AND ?",
                (start_date, end_date),
            ).fetchall()
        return frozenset(row["diary_date"] for row in rows)

    def recent_items(self, limit: int = 8) -> tuple[tuple[str, str, str], ...]:
        with self.database.read_connection() as connection:
            rows = connection.execute(
                """SELECT c.id, c.name, c.kind FROM recent_foods r
                   JOIN catalogue_items c ON c.id=r.catalogue_item_id
                   WHERE c.archived=0 ORDER BY r.last_used_at DESC, c.name LIMIT ?""",
                (max(0, min(limit, 50)),),
            ).fetchall()
        return tuple((row["id"], row["name"], row["kind"]) for row in rows)
