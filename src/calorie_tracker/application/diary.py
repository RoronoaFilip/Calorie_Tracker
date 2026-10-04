from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
import uuid

from calorie_tracker.domain.diary import DayTotals, DiaryEntry, MEALS, MealPortion, normalize_portions
from calorie_tracker.domain.nutrition import BASIS_GRAMS, Nutrients, ZERO, unit_label
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
    def _validate_amount(amount: Decimal, basis: str = BASIS_GRAMS) -> None:
        if not amount.is_finite() or amount <= ZERO:
            raise ValueError(f"Amount must be a finite number greater than 0 {unit_label(basis)}.")

    def _resolve(self, catalogue_item_id: str) -> tuple[str, Nutrients, str]:
        """Name, nutrient snapshot values and basis ("g" or "count") of an active food or recipe."""
        food = self.foods.get(catalogue_item_id)
        if food is not None:
            if not food.active:
                raise ValueError("Archived foods cannot be added to the diary.")
            return food.name, food.nutrients_per_100g, food.basis
        recipe = self.recipes.get(catalogue_item_id)
        if recipe is None or not recipe.active:
            raise ValueError("Choose an active food or recipe from the catalogue.")
        return recipe.draft.name, recipe.per_100g, BASIS_GRAMS

    def _build_entry(self, diary_date: str, meal: str, catalogue_item_id: str, amount: Decimal) -> DiaryEntry:
        if meal not in MEALS:
            raise ValueError(f"Meal must be one of: {', '.join(MEALS)}.")
        name, nutrients, basis = self._resolve(catalogue_item_id)
        self._validate_amount(amount, basis)
        return DiaryEntry(str(uuid.uuid4()), diary_date, meal, catalogue_item_id, name, amount, nutrients, basis)

    def add_item(self, diary_date: str, meal: str, catalogue_item_id: str, amount_g: Decimal) -> DiaryEntry:
        """Log a food or recipe. ``amount_g`` is grams, or the number of items for a counted food."""
        self._validate_date(diary_date)
        entry = self._build_entry(diary_date, meal, catalogue_item_id, amount_g)
        self.diary.add(entry)
        return entry

    def add_items_batch(
        self, diary_date: str, items: tuple[DiaryEntryInput, ...]
    ) -> tuple[DiaryEntry, ...]:
        self._validate_date(diary_date)
        result = tuple(
            self._build_entry(diary_date, item.meal, item.catalogue_item_id, item.amount_g) for item in items
        )
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
        entry = self.diary.get(entry_id)
        if entry is None:
            raise KeyError(f"Diary entry not found: {entry_id}")
        self._validate_amount(amount_g, entry.basis)
        updated = replace(entry, amount_g=amount_g)
        self.diary.update_amount(updated)
        return updated

    def split_entry(
        self, entry_id: str, portions: tuple[MealPortion, ...] | list[MealPortion]
    ) -> tuple[DiaryEntry, ...]:
        """Replace one entry with one entry per meal; the portions must add up to its amount."""
        entry = self.diary.get(entry_id)
        if entry is None:
            raise KeyError(f"Diary entry not found: {entry_id}")
        checked = normalize_portions(
            entry.amount_g, ((p.meal, p.amount_g) for p in portions), entry.unit
        )
        replacements = tuple(
            replace(entry, id=str(uuid.uuid4()), meal=portion.meal, amount_g=portion.amount_g)
            for portion in checked
        )
        self.diary.replace(entry_id, replacements)
        return replacements

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
        self._validate_amount(entry.amount_g, entry.basis)
        self.diary.restore(entry)
        return entry

    def populated_dates(self, start_date: str, end_date: str) -> frozenset[str]:
        self._validate_date(start_date)
        self._validate_date(end_date)
        if end_date < start_date:
            raise ValueError("End date cannot be before start date.")
        return self.diary.populated_dates(start_date, end_date)

    def first_logged_date(self) -> str | None:
        return self.diary.first_date()

    def all_entries(self) -> tuple[DiaryEntry, ...]:
        return self.diary.all_entries()
