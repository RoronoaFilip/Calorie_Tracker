import unittest
from decimal import Decimal

from calorie_tracker.application.product_import import (
    FOUND, LOOKUP_FAILED, NO_BARCODE, NOT_FOUND, OFFLINE, READER_UNAVAILABLE, UNREADABLE, ProductImportService,
)
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.products import (
    BarcodeImageError, BarcodeReaderUnavailableError, LookupFailedError, LookupOfflineError, ProductInfo,
)


class FakeReader:
    def __init__(self, result=(), error=None):
        self.result, self.error = result, error

    def read(self, path):
        if self.error:
            raise self.error
        return self.result


class FakeLookup:
    def __init__(self, products=None, error=None):
        self.products, self.error, self.asked = products or {}, error, []

    def lookup(self, barcode):
        self.asked.append(barcode)
        if self.error:
            raise self.error
        return self.products.get(barcode)


PRODUCT = ProductInfo("5449000000996", "Cola", Nutrients(calories=Decimal("42")), "Brand")


class ProductImportServiceTests(unittest.TestCase):
    def service(self, reader, lookup):
        return ProductImportService(reader, lookup)

    def test_found_product_becomes_a_draft_food_with_a_fresh_id(self):
        result = self.service(FakeReader(("5449000000996",)), FakeLookup({"5449000000996": PRODUCT})).import_photo("p.jpg")

        self.assertEqual(result.status, FOUND)
        food = result.draft_food()
        self.assertEqual((food.name, food.nutrients_per_100g.calories), ("Cola (Brand)", Decimal("42")))
        self.assertNotEqual(food.id, result.draft_food().id)  # nothing is stored; every draft is new

    def test_missing_nutrients_are_called_out(self):
        partial = ProductInfo("5449000000996", "Cola", Nutrients(), missing_nutrients=("fiber", "omega_3"))
        result = self.service(FakeReader(("5449000000996",)), FakeLookup({"5449000000996": partial})).import_photo("p")
        self.assertIn("fiber, omega 3", result.message)

    def test_upc_a_is_looked_up_with_the_leading_zero_spelling_first_then_as_read(self):
        lookup = FakeLookup({"036000291452": PRODUCT})
        result = self.service(FakeReader(("036000291452",)), lookup).import_photo("p")
        self.assertEqual(lookup.asked, ["0036000291452", "036000291452"])
        self.assertEqual(result.status, FOUND)

    def test_offline_still_gives_a_blank_draft_and_says_there_is_no_connection(self):
        result = self.service(FakeReader(("5449000000996",)), FakeLookup(error=LookupOfflineError("x"))).import_photo("p")
        self.assertEqual(result.status, OFFLINE)
        self.assertIn("no internet connection", result.message)
        self.assertEqual(result.barcode, "5449000000996")
        self.assertEqual(result.draft_food().name, "")

    def test_unknown_product_and_failed_lookup_fall_back_to_a_blank_draft(self):
        unknown = self.service(FakeReader(("5449000000996",)), FakeLookup()).import_photo("p")
        failed = self.service(FakeReader(("5449000000996",)), FakeLookup(error=LookupFailedError("HTTP 500."))).import_photo("p")
        self.assertEqual((unknown.status, failed.status), (NOT_FOUND, LOOKUP_FAILED))
        self.assertIsNotNone(unknown.draft_food())
        self.assertIn("HTTP 500.", failed.message)

    def test_photo_problems_give_no_draft_food(self):
        cases = (
            (FakeReader(()), NO_BARCODE),
            (FakeReader(error=BarcodeImageError("bad file")), UNREADABLE),
            (FakeReader(error=BarcodeReaderUnavailableError("install it")), READER_UNAVAILABLE),
        )
        for reader, status in cases:
            with self.subTest(status=status):
                lookup = FakeLookup()
                result = self.service(reader, lookup).import_photo("p")
                self.assertEqual(result.status, status)
                self.assertIsNone(result.draft_food())
                self.assertEqual(lookup.asked, [])  # never queries the network without a barcode

    def test_several_barcodes_use_the_first_and_say_so(self):
        result = self.service(
            FakeReader(("5449000000996", "4006381333931")), FakeLookup({"5449000000996": PRODUCT})
        ).import_photo("p")
        self.assertIn("1 other barcode", result.message)


if __name__ == "__main__":
    unittest.main()
