import unittest
from decimal import Decimal

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient, preview_recipe
from calorie_tracker.infrastructure.source_map import CSV_HEADER_ROW, EXCLUDED_ICE_CREAM_NAMES, FOOD_NAME_HEADER, NUTRIENT_HEADERS


class NutritionTests(unittest.TestCase):
    def test_scales_every_nutrient_by_entered_grams(self):
        nutrients = Nutrients(
            calories=Decimal("210"), fat=Decimal("8"), saturated_fat=Decimal("2"),
            carbohydrates=Decimal("24"), sugars=Decimal("9"), protein=Decimal("12"),
            fiber=Decimal("3"), omega_3=Decimal("1.5"), omega_6=Decimal("0.5"),
        )

        self.assertEqual(
            nutrients.for_amount(Decimal("50")),
            Nutrients(
                calories=Decimal("105"), fat=Decimal("4"), saturated_fat=Decimal("1"),
                carbohydrates=Decimal("12"), sugars=Decimal("4.5"), protein=Decimal("6"),
                fiber=Decimal("1.5"), omega_3=Decimal("0.75"), omega_6=Decimal("0.25"),
            ),
        )

    def test_scales_every_nutrient_for_counted_quantity_without_rounding(self):
        nutrients = Nutrients(
            calories=Decimal("123.4567"), fat=Decimal("8.1234"), saturated_fat=Decimal("2.3456"),
            carbohydrates=Decimal("24.5678"), sugars=Decimal("9.8765"), protein=Decimal("12.3456"),
            fiber=Decimal("3.4567"), omega_3=Decimal("1.2345"), omega_6=Decimal("0.9876"),
        )

        self.assertEqual(
            nutrients.for_quantity(Decimal("0.5"), "count"),
            Nutrients(
                calories=Decimal("61.72835"), fat=Decimal("4.06170"), saturated_fat=Decimal("1.17280"),
                carbohydrates=Decimal("12.28390"), sugars=Decimal("4.93825"), protein=Decimal("6.17280"),
                fiber=Decimal("1.72835"), omega_3=Decimal("0.61725"), omega_6=Decimal("0.49380"),
            ),
        )

    def test_rejects_an_unsupported_basis_in_nutrient_scaling(self):
        with self.assertRaises(ValueError):
            Nutrients(calories=Decimal("100")).for_quantity(Decimal("50"), "litre")


class RecipeValidationTests(unittest.TestCase):
    def test_recipe_preview_uses_ingredient_totals_and_final_yield(self):
        oats = Food("oats", "Oats", Nutrients(calories=Decimal("380"), protein=Decimal("13")))
        milk = Food("milk", "Milk", Nutrients(calories=Decimal("50"), protein=Decimal("3")))
        preview = preview_recipe(RecipeDraft(
            name="Breakfast",
            yield_g=Decimal("300"),
            ingredients=(RecipeIngredient(oats, Decimal("40")), RecipeIngredient(milk, Decimal("200"))),
        ))

        self.assertEqual(preview.total_nutrients.calories, Decimal("252"))
        self.assertEqual(preview.per_100g.calories, Decimal("84"))
        self.assertEqual(preview.total_nutrients.protein, Decimal("11.2"))
        self.assertEqual(preview.per_100g.protein, Decimal("3.733333333333333333333333333"))
        self.assertEqual(preview.errors, ())

    def test_yield_difference_is_a_warning_not_a_blocking_error(self):
        oats = Food("oats", "Oats", Nutrients(calories=Decimal("380")))
        preview = preview_recipe(RecipeDraft(
            name="Oat mix", yield_g=Decimal("150"),
            ingredients=(RecipeIngredient(oats, Decimal("100")),),
        ))

        self.assertEqual(preview.errors, ())
        self.assertEqual([warning.field for warning in preview.warnings], ["yield_g"])
        self.assertIn("differs from", preview.warnings[0].message)

    def test_invalid_recipe_inputs_are_reported_by_field(self):
        preview = preview_recipe(RecipeDraft(
            name=" ", yield_g=Decimal("0"), ingredients=(),
        ))

        self.assertEqual(
            [error.field for error in preview.errors],
            ["name", "yield_g", "ingredients"],
        )

    def test_all_nutrients_are_calculated_from_ingredients_and_final_yield(self):
        food_a = Food("a", "A", Nutrients(
            calories=Decimal("123.4567"), fat=Decimal("8.1234"), saturated_fat=Decimal("2.3456"),
            carbohydrates=Decimal("24.5678"), sugars=Decimal("9.8765"), protein=Decimal("12.3456"),
            fiber=Decimal("3.4567"), omega_3=Decimal("1.2345"), omega_6=Decimal("0.9876"),
        ))
        food_b = Food("b", "B", Nutrients(
            calories=Decimal("210.1234"), fat=Decimal("3.2109"), saturated_fat=Decimal("1.1098"),
            carbohydrates=Decimal("11.2223"), sugars=Decimal("4.3334"), protein=Decimal("17.4445"),
            fiber=Decimal("5.5556"), omega_3=Decimal("0.6667"), omega_6=Decimal("1.7778"),
        ))
        preview = preview_recipe(RecipeDraft(
            "Precise recipe", Decimal("250"),
            (RecipeIngredient(food_a, Decimal("100")), RecipeIngredient(food_b, Decimal("50"))),
        ))

        self.assertEqual(preview.total_nutrients, Nutrients(
            calories=Decimal("228.5184"), fat=Decimal("9.72885"), saturated_fat=Decimal("2.9005"),
            carbohydrates=Decimal("30.17895"), sugars=Decimal("12.0432"), protein=Decimal("21.06785"),
            fiber=Decimal("6.2345"), omega_3=Decimal("1.56785"), omega_6=Decimal("1.8765"),
        ))
        self.assertEqual(preview.per_100g, Nutrients(
            calories=Decimal("91.40736"), fat=Decimal("3.89154"), saturated_fat=Decimal("1.1602"),
            carbohydrates=Decimal("12.07158"), sugars=Decimal("4.81728"), protein=Decimal("8.42714"),
            fiber=Decimal("2.4938"), omega_3=Decimal("0.62714"), omega_6=Decimal("0.7506"),
        ))

    def test_non_finite_recipe_values_are_invalid(self):
        food = Food("food", "Food", Nutrients(calories=Decimal("100")))
        for yield_g, amount in ((Decimal("Infinity"), Decimal("10")), (Decimal("100"), Decimal("Infinity"))):
            with self.subTest(yield_g=yield_g, amount=amount):
                preview = preview_recipe(RecipeDraft(
                    "Recipe", yield_g, (RecipeIngredient(food, amount),),
                ))
                self.assertFalse(preview.is_valid)

    def test_archived_ingredient_is_rejected_and_named_in_the_validation(self):
        archived = Food("old", "Archived food", Nutrients(calories=Decimal("10")), active=False)
        preview = preview_recipe(RecipeDraft(
            name="Recipe", yield_g=Decimal("20"),
            ingredients=(RecipeIngredient(archived, Decimal("20")),),
        ))

        self.assertFalse(preview.is_valid)
        self.assertEqual(preview.errors[0].field, "ingredients.0.food")
        self.assertIn("Archived food", preview.errors[0].message)


class VerifiedSourceMapTests(unittest.TestCase):
    def test_csv_map_contains_only_the_nine_verified_per_100g_fields(self):
        self.assertEqual(CSV_HEADER_ROW, 4)
        self.assertEqual(FOOD_NAME_HEADER, "food_name")
        self.assertEqual(set(NUTRIENT_HEADERS.values()), {
            "calories / 100g", "fat / 100g", "saturated_fat / 100g",
            "carbohydrates / 100g", "sugars / 100g", "protein / 100g",
            "fiber / 100g", "omega-3 / 100g", "omega-6 / 100g",
        })
        self.assertTrue(all(header.endswith("/ 100g") for header in NUTRIENT_HEADERS.values()))

    def test_ice_cream_source_rows_are_excluded_from_basic_food_seeding(self):
        self.assertEqual(EXCLUDED_ICE_CREAM_NAMES, {"cocoa ice cream", "vanilla ice cream"})


if __name__ == "__main__":
    unittest.main()
