import csv
import logging
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from calorie_tracker.application.quick_add import quick_add_rows
from calorie_tracker.bootstrap import build_services
from calorie_tracker.domain.nutrition import BASIS_COUNT, Nutrients
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient
from calorie_tracker.infrastructure.catalogue_csv_exporter import export_foods_csv, export_recipes_csv
from calorie_tracker.infrastructure.csv_reading import CsvTable
from calorie_tracker.infrastructure.diary_csv_importer import DiaryCsvFormatError
from calorie_tracker.infrastructure.recipe_csv_importer import (
    RecipeCsvFormatError, STATUS_EXISTS, STATUS_PROBLEM, STATUS_READY,
)


def table(*rows: list[str]) -> CsvTable:
    return CsvTable([list(row) for row in rows], ",", "utf-8")


class CatalogueTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.services = build_services(self.root / "data" / "tracker.sqlite3")
        self.addCleanup(self._close_log_handlers)
        self.services.foods.save(Food("oats", "Oats", Nutrients(
            calories=Decimal("380"), protein=Decimal("13"), fat=Decimal("7"), carbohydrates=Decimal("60"),
            fiber=Decimal("10"), omega_3=Decimal("0.1"),
        )))
        self.services.foods.save(Food(
            "egg", "Egg", Nutrients(calories=Decimal("70"), protein=Decimal("6"), fat=Decimal("5"),
                                    carbohydrates=Decimal("0.5")), True, BASIS_COUNT,
        ))
        self.services.catalogue.save_recipe("r1", RecipeDraft("Egg oats", Decimal("180"), (
            RecipeIngredient(self.services.foods.get("oats"), Decimal("100")),
            RecipeIngredient(self.services.foods.get("egg"), Decimal("2")),
        )))

    def _close_log_handlers(self):
        logger = logging.getLogger("calorie_tracker")
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def _other_catalogue(self):
        other = build_services(self.root / "other" / "tracker.sqlite3")
        return other

    def test_food_export_round_trips_through_the_food_importer(self):
        path = self.root / "foods.csv"
        self.assertEqual(export_foods_csv(self.services.foods.search(), path), 2)
        other = self._other_catalogue()
        preview = other.importer.preview(path)
        self.assertEqual(len(preview.foods), 2)
        self.assertEqual(preview.invalid_foods, ())
        other.importer.apply(preview)
        egg, oats = other.foods.search("egg")[0], other.foods.search("oats")[0]
        self.assertEqual((egg.basis, oats.basis), ("count", "g"))
        self.assertEqual(oats.nutrients_per_100g, self.services.foods.get("oats").nutrients_per_100g)
        self.assertEqual(egg.nutrients_per_100g.calories, Decimal("70"))

    def test_food_csv_with_unknown_basis_needs_correction(self):
        path = self.root / "bad.csv"
        path.write_text("food_name,basis,calories,protein,fat,carbohydrates\nBun,slice,200,6,2,40\n", encoding="utf-8")
        preview = self._other_catalogue().importer.preview(path)
        self.assertEqual(len(preview.invalid_foods), 1)
        self.assertEqual(preview.invalid_foods[0].fields_to_correct, ("basis",))

    def test_recipe_export_and_import_into_a_fresh_catalogue(self):
        foods_path, recipes_path = self.root / "foods.csv", self.root / "recipes.csv"
        export_foods_csv(self.services.foods.search(), foods_path)
        self.assertEqual(export_recipes_csv(self.services.recipes.search(), recipes_path), 1)
        rows = list(csv.reader(recipes_path.open(encoding="utf-8-sig")))
        self.assertEqual(rows[0], ["recipe_name", "yield_g", "ingredient", "amount", "unit"])
        self.assertEqual(rows[2], ["Egg oats", "180", "Egg", "2", "pcs"])

        other = self._other_catalogue()
        other.importer.apply(other.importer.preview(foods_path))
        preview = other.recipe_importer.preview(recipes_path)
        self.assertEqual([item.status for item in preview.items], [STATUS_READY])
        result = other.catalogue.import_recipes(tuple(item.draft for item in preview.ready))
        self.assertEqual((result.imported, result.failed), (1, ()))
        imported = other.recipes.search("egg oats")[0]
        self.assertEqual(imported.draft.yield_g, Decimal("180"))
        self.assertEqual([i.amount_g for i in imported.draft.ingredients], [Decimal("100"), Decimal("2")])
        self.assertEqual(imported.per_100g, self.services.recipes.get("r1").per_100g)

    def test_existing_recipe_names_are_never_overwritten(self):
        recipes_path = self.root / "recipes.csv"
        export_recipes_csv(self.services.recipes.search(), recipes_path)
        preview = self.services.recipe_importer.preview(recipes_path)
        self.assertEqual([item.status for item in preview.items], [STATUS_EXISTS])
        self.assertEqual(preview.ready, ())

    def test_name_can_be_left_empty_on_following_rows_and_yield_is_computed_for_weighed_recipes(self):
        preview = self.services.recipe_importer.preview_table(table(
            ["recipe", "ingredient", "amount"], ["Porridge", "Oats", "50"], ["", "Oats", "25 g"],
        ))
        item = preview.items[0]
        self.assertEqual((item.status, item.ingredient_count, item.draft.yield_g), (STATUS_READY, 2, Decimal("75")))

    def test_counted_ingredient_without_yield_is_a_problem(self):
        preview = self.services.recipe_importer.preview_table(table(
            ["recipe_name", "ingredient", "amount"], ["Omelette", "Egg", "3"],
        ))
        self.assertEqual(preview.items[0].status, STATUS_PROBLEM)
        self.assertIn("final yield", preview.items[0].message)

    def test_unknown_ingredient_is_reported_with_a_suggestion_and_marks_the_whole_recipe(self):
        data = table(
            ["recipe_name", "ingredient", "amount"], ["Porridge", "Oatz", "50"], ["Porridge", "Egg", "1"],
        )
        issues = self.services.recipe_importer.issues_for(data)
        self.assertEqual([(i.row, i.column) for i in issues], [(1, 1), (2, 0)])
        self.assertIn("Did you mean 'Oats'", issues[0].message)
        preview = self.services.recipe_importer.preview_table(data)
        self.assertEqual(preview.items[0].status, STATUS_PROBLEM)

    def test_file_without_recipe_columns_is_rejected_with_issues(self):
        with self.assertRaises(RecipeCsvFormatError) as caught:
            self.services.recipe_importer.preview_table(table(["a", "b"], ["1", "2"]))
        self.assertTrue(caught.exception.issues)


class RawTextImportTests(CatalogueTransferTests):
    """Pasted CSV text goes through exactly the same checks as a CSV file."""

    def test_food_recipe_and_diary_importers_read_pasted_text(self):
        foods = self._other_catalogue().importer.read_text(
            "food_name,basis,calories,protein,fat,carbohydrates\nBun,count,200,6,2,40\n"
        )
        self.assertEqual(len(self._other_catalogue().importer.preview_table(foods).foods), 1)
        recipes = self.services.recipe_importer.read_text(
            "recipe_name,yield_g,ingredient,amount\nPasted,150,Oats,50\n"
        )
        self.assertEqual(self.services.recipe_importer.preview_table(recipes).items[0].status, STATUS_READY)
        diary = self.services.diary_importer.read_text("food_name,amount/count,meal\nEgg,0.5,Lunch\n")
        row = self.services.diary_importer.preview_table(diary).rows[0]
        self.assertTrue(row.is_importable)
        self.assertEqual((row.basis, row.amount_g), ("count", Decimal("0.5")))

    def test_pasted_text_with_a_different_delimiter_is_detected(self):
        table = self.services.diary_importer.read_text("food_name;amount;meal\nOats;45;Lunch\n")
        self.assertEqual(table.delimiter, ";")


class QuickAddTests(unittest.TestCase):
    def test_table_rows_become_csv_rows_and_blank_foods_are_dropped(self):
        rows = quick_add_rows([
            ("Oats", "45.0", "Breakfast"), ("Egg", Decimal("0.50"), "Lunch"),
            ("  ", "10", "Dinner"), ("Rice", 100.0, "Snacks"),
        ])
        self.assertEqual(rows, [
            ["food_name", "grams_eaten", "meal"],
            ["Oats", "45", "Breakfast"], ["Egg", "0.5", "Lunch"], ["Rice", "100", "Snacks"],
        ])

    def test_rows_go_through_the_normal_diary_import_checks(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        services = build_services(Path(temp.name) / "data" / "tracker.sqlite3")
        self.addCleanup(lambda: [h.close() for h in logging.getLogger("calorie_tracker").handlers[:]])
        services.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))
        services.foods.save(Food("egg", "Egg", Nutrients(calories=Decimal("70")), True, BASIS_COUNT))
        rows = quick_add_rows([
            ("Oats", "45", "Breakfast"), ("Egg", "0.5", "Breakfast"), ("Porridge", "100", "Lunch"),
        ])
        table = CsvTable(rows, ",", "utf-8")
        preview = services.diary_importer.preview_table(table)
        oats, egg, porridge = preview.rows
        self.assertTrue(oats.is_importable and egg.is_importable)
        self.assertEqual((egg.basis, egg.amount_g, egg.meal), ("count", Decimal("0.5"), "Breakfast"))
        self.assertFalse(porridge.is_importable)
        self.assertEqual(services.diary_importer.issues_for(table), ())  # a missing food is fixed on the review screen


if __name__ == "__main__":
    unittest.main()


class TargetDriftTests(unittest.TestCase):
    def test_default_drift_only_accepts_exactly_100_percent(self):
        from calorie_tracker.application.targets import DEFAULT_DRIFT, is_on_track, percent_of_target
        self.assertEqual(DEFAULT_DRIFT, (100, 100))
        self.assertEqual(percent_of_target(Decimal("1999"), Decimal("2000")), 100)  # rounds to a whole percent
        self.assertTrue(is_on_track(100, DEFAULT_DRIFT))
        self.assertFalse(is_on_track(99, DEFAULT_DRIFT))
        self.assertFalse(is_on_track(101, DEFAULT_DRIFT))

    def test_custom_range_and_over_100(self):
        from calorie_tracker.application.targets import is_on_track, normalize_drift, percent_of_target
        drift = normalize_drift(85, 110)
        self.assertTrue(is_on_track(85, drift) and is_on_track(110, drift))
        self.assertFalse(is_on_track(84, drift) or is_on_track(111, drift))
        self.assertEqual(percent_of_target(Decimal("3000"), Decimal("2000")), 150)
        self.assertEqual(normalize_drift(110, 85), (85, 110))  # wrong way round
        self.assertEqual(normalize_drift(85, None), (85, 100))  # missing upper bound is 100
        self.assertEqual(normalize_drift(None, None), (100, 100))

    def test_load_drift_defaults_when_nothing_or_garbage_is_saved(self):
        from calorie_tracker.application.targets import load_drift
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        services = build_services(Path(temp.name) / "data" / "tracker.sqlite3")
        self.addCleanup(lambda: [h.close() for h in logging.getLogger("calorie_tracker").handlers[:]])
        self.assertEqual(load_drift(services.settings, "calories"), (100, 100))
        services.settings.set_json("target_drift", {"calories": [85, 110], "fat": "oops"})
        self.assertEqual(load_drift(services.settings, "calories"), (85, 110))
        self.assertEqual(load_drift(services.settings, "fat"), (100, 100))
