import unittest

from calorie_tracker.domain.barcode import is_valid_barcode, lookup_candidates, normalize_barcode


class BarcodeValidationTests(unittest.TestCase):
    def test_accepts_real_world_codes_of_every_supported_type(self):
        for code in ("5449000000996", "4006381333931", "036000291452", "96385074", "04252614"):
            with self.subTest(code=code):
                self.assertTrue(is_valid_barcode(code))

    def test_rejects_a_wrong_check_digit_bad_length_and_non_digits(self):
        for code in ("5449000000997", "036000291453", "96385075", "123", "", "54490000009961", "54490000009AB"):
            with self.subTest(code=code):
                self.assertFalse(is_valid_barcode(code))

    def test_normalize_keeps_digits_only(self):
        self.assertEqual(normalize_barcode(" 5 449000-000996\n"), "5449000000996")
        self.assertEqual(normalize_barcode(""), "")

    def test_lookup_candidates_offer_the_leading_zero_spelling_of_upc_codes(self):
        self.assertEqual(lookup_candidates("5449000000996"), ("5449000000996",))
        self.assertEqual(lookup_candidates("036000291452"), ("0036000291452", "036000291452"))
        self.assertEqual(lookup_candidates("96385074"), ("96385074",))
        self.assertEqual(
            lookup_candidates("04252614"), ("04252614", "0042100005264", "042100005264")
        )


if __name__ == "__main__":
    unittest.main()
