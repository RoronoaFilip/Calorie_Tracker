import unittest

from calorie_tracker.domain.food_matching import FoodName, normalize_name, suggest_foods


def foods(*names, recent=()):
    return [FoodName(str(index), name, name in recent) for index, name in enumerate(names)]


class NormalizeNameTests(unittest.TestCase):
    def test_case_spacing_punctuation_and_latin_accents_are_ignored(self):
        self.assertEqual(normalize_name("  Crème   Fraîche, "), "creme fraiche")

    def test_cyrillic_letters_are_not_flattened(self):
        self.assertEqual(normalize_name("Йогурт"), "йогурт")
        self.assertNotEqual(normalize_name("Йогурт"), normalize_name("Иогурт"))


class SuggestFoodsTests(unittest.TestCase):
    def test_spelling_level_differences_are_confident(self):
        cases = [
            ("eggs", "Egg"),
            ("rolled oats", "Oats, rolled"),
            ("creme fraiche", "Crème fraîche"),
            ("chiken breast", "Chicken breast"),
            ("potatoes", "Potato"),
        ]
        for typed, stored in cases:
            with self.subTest(typed=typed):
                result = suggest_foods(typed, foods(stored, "Milk", "Rice"))
                self.assertTrue(result and result[0].name == stored and result[0].confident, result)

    def test_extra_or_missing_words_are_suggestions_only(self):
        for typed, stored in (("skim milk", "Milk"), ("milk", "Milk 2%"), ("boiled potato", "Potato")):
            with self.subTest(typed=typed):
                result = suggest_foods(typed, foods(stored))
                self.assertEqual([item.name for item in result], [stored])
                self.assertFalse(result[0].confident)

    def test_ambiguous_candidates_are_not_confident(self):
        result = suggest_foods("oats", foods("Oats (Brand A)", "Oats (Brand B)"))
        self.assertEqual(len(result), 2)
        self.assertFalse(any(item.confident for item in result))

    def test_clear_winner_over_a_weaker_candidate_is_confident(self):
        result = suggest_foods("oats", foods("Oat milk", "Oats"))
        self.assertEqual(result[0].name, "Oats")
        self.assertTrue(result[0].confident)

    def test_recent_foods_break_ties_only(self):
        tied = suggest_foods("oats", foods("Oats (Brand A)", "Oats (Brand B)", recent=("Oats (Brand B)",)))
        self.assertEqual(tied[0].name, "Oats (Brand B)")
        weak = suggest_foods("milk", foods("Milk 2%", recent=("Milk 2%",)))
        self.assertFalse(weak[0].confident)

    def test_nothing_close_returns_nothing(self):
        self.assertEqual(suggest_foods("pizza", foods("Oats", "Milk")), ())
        self.assertEqual(suggest_foods("   ", foods("Oats")), ())

    def test_limit_and_order(self):
        result = suggest_foods("oat", foods("Oat flakes", "Oat bran", "Oat milk", "Oat cake", "Oats"), limit=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].name, "Oats")
        self.assertEqual([item.score for item in result], sorted((item.score for item in result), reverse=True))

    def test_cyrillic_names_match_by_case(self):
        result = suggest_foods("МЛЯКО", foods("мляко"))
        self.assertTrue(result[0].confident)


if __name__ == "__main__":
    unittest.main()
