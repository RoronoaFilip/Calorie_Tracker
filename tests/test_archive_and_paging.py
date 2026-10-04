import logging
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from calorie_tracker.application.catalogue import RecipeValidationError
from calorie_tracker.bootstrap import build_services
from calorie_tracker.domain.nutrition import BASIS_COUNT, Nutrients
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient
from calorie_tracker.infrastructure.database import Database


def make_services(root: Path):
    return build_services(root / "data" / "tracker.sqlite3")


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.services = make_services(self.root)
        self.addCleanup(self._close_log_handlers)
        self.services.foods.save(Food("egg", "Egg", Nutrients(calories=Decimal("70"))))
        self.services.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))
        self.services.catalogue.save_recipe("r1", RecipeDraft("Egg oats", Decimal("200"), (
            RecipeIngredient(self.services.foods.get("oats"), Decimal("100")),
            RecipeIngredient(self.services.foods.get("egg"), Decimal("100")),
        )))
        self.entry = self.services.diary.add_item("2026-03-01", "Breakfast", "r1", Decimal("150"))

    def _close_log_handlers(self):
        logger = logging.getLogger("calorie_tracker")
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def test_archiving_moves_the_recipe_out_of_the_catalogue_and_keeps_the_diary_snapshot(self):
        self.services.recipes.archive("r1")
        self.assertIsNone(self.services.recipes.get("r1"))
        self.assertEqual(self.services.recipes.search(), ())
        archived = self.services.recipes.get_archived("r1")
        self.assertEqual((archived.name, archived.yield_g), ("Egg oats", Decimal("200")))
        self.assertEqual([i.food_name for i in archived.ingredients], ["Oats", "Egg"])
        kept = self.services.diary.diary.get(self.entry.id)
        self.assertIsNone(kept.catalogue_item_id)
        self.assertEqual(kept.nutrients.calories, Decimal("337.5"))

    def test_food_basis_can_change_once_the_recipe_is_archived(self):
        with self.assertRaises(ValueError):
            self.services.foods.save(Food("egg", "Egg", Nutrients(calories=Decimal("70")), True, BASIS_COUNT))
        self.services.recipes.archive("r1")
        self.services.foods.save(Food("egg", "Egg", Nutrients(calories=Decimal("70")), True, BASIS_COUNT))
        self.assertEqual(self.services.foods.get("egg").basis, "count")

    def test_restoring_unchanged_recipe_needs_no_review_and_relinks_the_diary(self):
        self.services.recipes.archive("r1")
        plan = self.services.catalogue.prepare_restore("r1")
        self.assertFalse(plan.needs_review)
        self.services.catalogue.restore_recipe("r1", plan.draft)
        self.assertEqual(self.services.recipes.get("r1").draft.name, "Egg oats")
        self.assertIsNone(self.services.recipes.get_archived("r1"))
        self.assertEqual(self.services.diary.diary.get(self.entry.id).catalogue_item_id, "r1")

    def test_restore_asks_for_review_when_an_ingredient_changed_basis(self):
        self.services.recipes.archive("r1")
        self.services.foods.save(Food("egg", "Egg", Nutrients(calories=Decimal("70")), True, BASIS_COUNT))
        plan = self.services.catalogue.prepare_restore("r1")
        self.assertTrue(plan.needs_review)
        self.assertIn("Egg", plan.problems[0])
        self.assertIn("per item", plan.problems[0])
        self.assertIn("per 100 g", plan.problems[0])
        # the person fixes the amount (2 eggs) and gives the final weight, then the recipe returns
        fixed = RecipeDraft("Egg oats", Decimal("200"), (
            RecipeIngredient(self.services.foods.get("oats"), Decimal("100")),
            RecipeIngredient(self.services.foods.get("egg"), Decimal("2")),
        ))
        self.services.catalogue.restore_recipe("r1", fixed)
        self.assertEqual(self.services.recipes.get("r1").draft.ingredients[1].amount_g, Decimal("2"))

    def test_restore_with_an_invalid_draft_is_refused_and_stays_archived(self):
        self.services.recipes.archive("r1")
        with self.assertRaises(RecipeValidationError):
            self.services.catalogue.restore_recipe("r1", RecipeDraft("Egg oats", Decimal("0"), ()))
        self.assertIsNotNone(self.services.recipes.get_archived("r1"))

    def test_archived_foods_can_be_restored(self):
        self.services.foods.archive("oats")
        self.assertFalse(self.services.foods.get("oats").active)
        self.services.foods.restore("oats")
        self.assertTrue(self.services.foods.get("oats").active)


class PagingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.services = make_services(Path(self.temp_dir.name))
        self.addCleanup(self._close_log_handlers)
        for number in range(40):
            self.services.foods.save(Food(f"f{number:02d}", f"Food {number:02d}", Nutrients(calories=Decimal(number))))
        self.services.foods.save(Food("egg", "Egg", Nutrients(calories=Decimal("70")), True, BASIS_COUNT))
        self.services.catalogue.save_recipe("r1", RecipeDraft("Food salad", Decimal("100"), (
            RecipeIngredient(self.services.foods.get("f01"), Decimal("100")),
        )))
        self.services.catalogue.save_recipe("r2", RecipeDraft("Egg dish", Decimal("2"), (
            RecipeIngredient(self.services.foods.get("egg"), Decimal("2")),
        )))

    def _close_log_handlers(self):
        logger = logging.getLogger("calorie_tracker")
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def test_pages_follow_each_other_without_overlap_and_end_cleanly(self):
        query = self.services.catalogue_query
        first = query.page(limit=15, offset=0)
        second = query.page(limit=15, offset=15)
        rest = query.page(limit=15, offset=30)
        self.assertEqual((len(first), len(second), len(rest)), (15, 15, 13))  # 40 foods + egg + 2 recipes
        ids = [row.id for row in first + second + rest]
        self.assertEqual(len(ids), len(set(ids)))
        names = [row.name.casefold() for row in first + second + rest]
        self.assertEqual(names, sorted(names))
        self.assertEqual(query.page(limit=15, offset=45), [])

    def test_search_and_kind_filter_are_done_by_the_database(self):
        query = self.services.catalogue_query
        self.assertEqual([r.name for r in query.page("egg")], ["Egg", "Egg dish"])
        self.assertEqual([r.name for r in query.page("egg", kind="recipe")], ["Egg dish"])
        self.assertEqual([r.name for r in query.page("egg", kind="food")], ["Egg"])
        self.assertEqual(len(query.page(kind="recipe")), 2)
        self.assertEqual(query.page("100%"), [])  # wildcard characters are matched literally
        with self.assertRaises(ValueError):
            query.page(kind="drinks")

    def test_rows_carry_basis_and_nutrients(self):
        egg = self.services.catalogue_query.page("egg", kind="food")[0]
        self.assertEqual((egg.kind, egg.basis, egg.nutrients.calories), ("food", "count", Decimal("70")))

    def test_archived_page_lists_archived_foods_and_recipes_only(self):
        self.services.recipes.archive("r1")
        self.services.foods.archive("f02")
        query = self.services.catalogue_query
        self.assertEqual([(r.kind, r.name) for r in query.archived_page()], [("food", "Food 02"), ("recipe", "Food salad")])
        self.assertEqual([r.name for r in query.archived_page(kind="recipe")], ["Food salad"])
        self.assertNotIn("Food salad", [r.name for r in query.page()])


class MigrationV3Tests(unittest.TestCase):
    def test_recipes_archived_before_the_upgrade_move_to_the_archive_table(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "data" / "tracker.sqlite3"
        services = make_services(Path(temp.name))
        self.addCleanup(lambda: [h.close() for h in logging.getLogger("calorie_tracker").handlers[:]])
        services.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))
        services.catalogue.save_recipe("r1", RecipeDraft("Porridge", Decimal("100"), (
            RecipeIngredient(services.foods.get("oats"), Decimal("100")),
        )))
        entry = services.diary.add_item("2026-03-01", "Breakfast", "r1", Decimal("100"))
        # Simulate a version 2 database in which the recipe was archived with the old flag.
        connection = sqlite3.connect(path)
        connection.executescript(
            "DROP TABLE archived_recipe_ingredients; DROP TABLE archived_recipes;"
            "UPDATE catalogue_items SET archived=1 WHERE id='r1'; PRAGMA user_version = 2;"
        )
        connection.commit()
        connection.close()
        Database(path).initialize()
        migrated = make_services(Path(temp.name))
        self.assertEqual(migrated.recipes.search(), ())
        archived = migrated.recipes.get_archived("r1")
        self.assertEqual(archived.name, "Porridge")
        self.assertEqual(archived.diary_entry_ids, (entry.id,))
        self.assertEqual(archived.ingredients[0].food_name, "Oats")
        with migrated.database.read_connection() as c:
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 3)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM recipe_ingredients").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
