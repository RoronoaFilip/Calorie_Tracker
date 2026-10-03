import io
import json
import socket
import unittest
import urllib.error
from decimal import Decimal

from calorie_tracker.domain.products import LookupFailedError, LookupOfflineError
from calorie_tracker.infrastructure.open_food_facts import OpenFoodFactsLookup, parse_product


class _Response:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self):
        return self._body


def opener_returning(payload) -> object:
    calls = []

    def opener(request, timeout):
        calls.append((request, timeout))
        return _Response(payload if isinstance(payload, bytes) else json.dumps(payload).encode())

    opener.calls = calls
    return opener


def opener_raising(error: BaseException):
    def opener(request, timeout):
        raise error

    return opener


FULL_PRODUCT = {
    "status": 1,
    "product": {
        "product_name": "Hazelnut spread",
        "brands": "Nutella,Ferrero",
        "nutriments": {
            "energy-kcal_100g": 539, "fat_100g": 30.9, "saturated-fat_100g": 10.6,
            "carbohydrates_100g": 57.5, "sugars_100g": "56.3", "proteins_100g": 6.3,
            "fiber_100g": 0, "omega-3-fat_100g": 0.0012, "omega-6-fat_100g": 3.456789,
        },
    },
}


class ParseProductTests(unittest.TestCase):
    def test_maps_every_supported_nutrient(self):
        product = parse_product("3017620422003", FULL_PRODUCT)
        n = product.nutrients_per_100g
        self.assertEqual(product.display_name, "Hazelnut spread (Nutella)")
        self.assertEqual(
            (n.calories, n.fat, n.saturated_fat, n.carbohydrates, n.sugars, n.protein, n.fiber),
            (Decimal("539.00"), Decimal("30.90"), Decimal("10.60"), Decimal("57.50"), Decimal("56.30"),
             Decimal("6.30"), Decimal("0.000")),
        )
        self.assertEqual((n.omega_3, n.omega_6), (Decimal("0.001"), Decimal("3.46")))
        self.assertEqual(product.missing_nutrients, ())

    def test_missing_nutrients_are_listed_and_left_at_zero(self):
        product = parse_product("1", {"status": 1, "product": {
            "product_name": "Rice", "nutriments": {"energy-kcal_100g": 360, "proteins_100g": 7}}})
        self.assertEqual(product.nutrients_per_100g.fat, Decimal("0"))
        self.assertIn("omega_3", product.missing_nutrients)
        self.assertNotIn("calories", product.missing_nutrients)

    def test_calories_fall_back_to_kilojoules(self):
        product = parse_product("1", {"status": 1, "product": {
            "product_name": "X", "nutriments": {"energy-kj_100g": 418.4}}})
        self.assertEqual(product.nutrients_per_100g.calories, Decimal("100.00"))

    def test_garbage_values_are_treated_as_missing(self):
        product = parse_product("1", {"status": 1, "product": {"product_name": "X", "nutriments": {
            "energy-kcal_100g": "n/a", "fat_100g": -4, "proteins_100g": True, "sugars_100g": None}}})
        self.assertEqual(product.nutrients_per_100g.calories, Decimal("0"))
        self.assertIn("fat", product.missing_nutrients)
        self.assertIn("protein", product.missing_nutrients)

    def test_unknown_product_or_unexpected_shape_is_none(self):
        self.assertIsNone(parse_product("1", {"status": 0, "status_verbose": "product not found"}))
        self.assertIsNone(parse_product("1", {"status": 1}))
        self.assertIsNone(parse_product("1", ["not", "a", "dict"]))

    def test_brand_already_in_the_name_is_not_repeated(self):
        product = parse_product("1", {"status": 1, "product": {"product_name": "Nutella 400g", "brands": "Nutella"}})
        self.assertEqual(product.display_name, "Nutella 400g")


class OpenFoodFactsLookupTests(unittest.TestCase):
    def test_requests_the_product_with_a_descriptive_user_agent_and_timeout(self):
        opener = opener_returning(FULL_PRODUCT)
        product = OpenFoodFactsLookup(timeout=3, opener=opener).lookup("3017620422003")

        request, timeout = opener.calls[0]
        self.assertIn("/api/v2/product/3017620422003.json", request.full_url)
        self.assertIn("DailyPlate", request.get_header("User-agent"))
        self.assertEqual(timeout, 3)
        self.assertEqual(product.barcode, "3017620422003")

    def test_unknown_product_is_none_not_an_error(self):
        self.assertIsNone(OpenFoodFactsLookup(opener=opener_returning({"status": 0})).lookup("1"))
        not_found = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"{}"))
        self.assertIsNone(OpenFoodFactsLookup(opener=opener_raising(not_found)).lookup("1"))

    def test_network_problems_are_reported_as_offline(self):
        for error in (
            urllib.error.URLError(socket.gaierror("no dns")),
            TimeoutError("timed out"),
            ConnectionResetError("reset"),
            OSError("network unreachable"),
        ):
            with self.subTest(error=error):
                with self.assertRaises(LookupOfflineError):
                    OpenFoodFactsLookup(opener=opener_raising(error)).lookup("1")

    def test_server_problems_are_a_failure_not_offline(self):
        for code in (429, 500, 503):
            error = urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b""))
            with self.subTest(code=code), self.assertRaises(LookupFailedError):
                OpenFoodFactsLookup(opener=opener_raising(error)).lookup("1")
        with self.assertRaises(LookupFailedError):
            OpenFoodFactsLookup(opener=opener_returning(b"<html>maintenance</html>")).lookup("1")


if __name__ == "__main__":
    unittest.main()
