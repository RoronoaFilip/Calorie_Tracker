from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
import uuid

from calorie_tracker.domain.diary import DayTotals, DiaryEntry, MEALS
from calorie_tracker.domain.nutrition import Nutrients, ZERO
from calorie_tracker.infrastructure.repositories import DiaryRepository, FoodRepository, RecipeRepository


@dataclass(frozen=True)
class DiaryEntryInput:
    meal: str
    catalogue_item_id: str
    amount_g: Decimal


class DiaryService:
    def __init__(self, foods: FoodRepository, recipes: RecipeRepository, diary: DiaryRepository):
        self.foods = foods
        self.recipes = recipes
        self.diary = diary

    @staticmethod
    def _validate_date(diary_date: str) -> None:
        try:
            parsed = date.fromisoformat(diary_date)
        except (ValueError, TypeError):
            raise ValueError("Choose a valid diary date in YYYY-MM-DD format.") from None
        if parsed.isoformat() != diary_date:
            raise ValueError("Choose a valid diary date in YYYY-MM-DD format.")

    @staticmethod
    def _validate_amount(amount_g: Decimal) -> None:
        if not amount_g.is_finite() or amount_g <= ZERO:
            raise ValueError("Amount must be a finite number greater than 0 g.")

    def add_item(self, diary_date: str, meal: str, catalogue_item_id: str, amount_g: Decimal) -> DiaryEntry:
        self._validate_date(diary_date)
        if meal not in MEALS:
            raise ValueError(f"Meal must be one of: {', '.join(MEALS)}.")
        self._validate_amount(amount_g)
        food = self.foods.get(catalogue_item_id)
        if food is not None:
            if not food.active:
                raise ValueError("Archived foods cannot be added to the diary.")
            name, nutrients = food.name, food.nutrients_per_100g
        else:
            recipe = self.recipes.get(catalogue_item_id)
            if recipe is None or not recipe.active:
                raise ValueError("Choose an active food or recipe from the catalogue.")
            name, nutrients = recipe.draft.name, recipe.per_100g
        entry = DiaryEntry(
            str(uuid.uuid4()), diary_date, meal, catalogue_item_id, name, amount_g, nutrients
        )
        self.diary.add(entry)
        return entry

    def add_items_batch(
        self, diary_date: str, items: tuple[DiaryEntryInput, ...]
    ) -> tuple[DiaryEntry, ...]:
        self._validate_date(diary_date)
        entries: list[DiaryEntry] = []
        for item in items:
            if item.meal not in MEALS:
                raise ValueError(f"Meal must be one of: {', '.join(MEALS)}.")
            self._validate_amount(item.amount_g)
            food = self.foods.get(item.catalogue_item_id)
            if food is not None:
                if not food.active:
                    raise ValueError("Archived foods cannot be added to the diary.")
                name, nutrients = food.name, food.nutrients_per_100g
            else:
                recipe = self.recipes.get(item.catalogue_item_id)
                if recipe is None or not recipe.active:
                    raise ValueError("Choose an active food or recipe from the catalogue.")
                name, nutrients = recipe.draft.name, recipe.per_100g
            entries.append(DiaryEntry(
                str(uuid.uuid4()), diary_date, item.meal, item.catalogue_item_id,
                name, item.amount_g, nutrients,
            ))
        result = tuple(entries)
        self.diary.add_many(result)
        return result

    def entries_for_day(self, diary_date: str) -> tuple[DiaryEntry, ...]:
        self._validate_date(diary_date)
        return self.diary.entries_on(diary_date)

    def totals_for_day(self, diary_date: str) -> DayTotals:
        entries = self.entries_for_day(diary_date)
        meals = {meal: Nutrients() for meal in MEALS}
        total = Nutrients()
        for entry in entries:
            meals[entry.meal] += entry.nutrients
            total += entry.nutrients
        return DayTotals(meals, total)

    def edit_amount(self, entry_id: str, amount_g: Decimal) -> DiaryEntry:
        self._validate_amount(amount_g)
        entry = self.diary.get(entry_id)
        if entry is None:
            raise KeyError(f"Diary entry not found: {entry_id}")
        updated = replace(entry, amount_g=amount_g)
        self.diary.update_amount(updated)
        return updated

    def repeat_entry(self, entry_id: str) -> DiaryEntry:
        entry = self.diary.get(entry_id)
        if entry is None:
            raise KeyError(f"Diary entry not found: {entry_id}")
        repeated = replace(entry, id=str(uuid.uuid4()))
        self.diary.add(repeated)
        return repeated

    def delete_entry(self, entry_id: str) -> DiaryEntry:
        deleted = self.diary.delete(entry_id)
        if deleted is None:
            raise KeyError(f"Diary entry not found: {entry_id}")
        return deleted

    def restore_entry(self, entry: DiaryEntry) -> DiaryEntry:
        self._validate_date(entry.diary_date)
        self._validate_amount(entry.amount_g)
        self.diary.restore(entry)
        return entry

    def populated_dates(self, start_date: str, end_date: str) -> frozenset[str]:
        self._validate_date(start_date)
        self._validate_date(end_date)
        if end_date < start_date:
            raise ValueError("End date cannot be before start date.")
        return self.diary.populated_dates(start_date, end_date)
