"""Look a barcode up in Open Food Facts (https://world.openfoodfacts.org, data under the ODbL licence)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from calorie_tracker.domain.nutrition import Nutrients, ZERO
from calorie_tracker.domain.products import LookupFailedError, LookupOfflineError, ProductInfo

ATTRIBUTION = "Source: Open Food Facts (openfoodfacts.org), licensed under the ODbL."
USER_AGENT = "DailyPlate-CalorieTracker/0.1 (local desktop app; barcode lookup on demand)"
BASE_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json?fields=code,product_name,brands,nutriments"
KJ_PER_KCAL = Decimal("4.184")

# Supported nutrient -> key in Open Food Facts' "nutriments" object (grams per 100 g, calories in kcal).
NUTRIMENT_KEYS = {
    "calories": "energy-kcal_100g",
    "fat": "fat_100g",
    "saturated_fat": "saturated-fat_100g",
    "carbohydrates": "carbohydrates_100g",
    "sugars": "sugars_100g",
    "protein": "proteins_100g",
    "fiber": "fiber_100g",
    "omega_3": "omega-3-fat_100g",
    "omega_6": "omega-6-fat_100g",
}


def _number(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation:
        return None
    return number if number.is_finite() and number >= ZERO else None


def _tidy(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01") if value >= 1 else Decimal("0.001"))


def parse_product(barcode: str, payload: object) -> ProductInfo | None:
    """Map an Open Food Facts response to a ProductInfo; None when the product is not in the database."""
    if not isinstance(payload, dict) or payload.get("status") != 1:
        return None
    product = payload.get("product")
    if not isinstance(product, dict):
        return None
    nutriments = product.get("nutriments")
    nutriments = nutriments if isinstance(nutriments, dict) else {}
    values: dict[str, Decimal] = {}
    missing: list[str] = []
    for field, key in NUTRIMENT_KEYS.items():
        number = _number(nutriments.get(key))
        if number is None and field == "calories":
            kilojoules = _number(nutriments.get("energy-kj_100g"))
            if kilojoules is None:
                kilojoules = _number(nutriments.get("energy_100g"))  # kJ in the v2 API
            number = kilojoules / KJ_PER_KCAL if kilojoules is not None else None
        if number is None:
            missing.append(field)
        else:
            values[field] = _tidy(number)
    name = str(product.get("product_name") or "").strip()
    brand = str(product.get("brands") or "").split(",")[0].strip()
    return ProductInfo(barcode, name, Nutrients.from_mapping(values), brand, tuple(missing))


class OpenFoodFactsLookup:
    """Online product lookup. Only ever called when the user imports a barcode photo."""

    def __init__(self, timeout: float = 5.0, opener: Callable[..., object] | None = None):
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen

    def lookup(self, barcode: str) -> ProductInfo | None:
        request = urllib.request.Request(
            BASE_URL.format(code=barcode), headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as error:  # an HTTP answer: the network itself works
            if error.code == 404:
                return None
            if error.code == 429:
                raise LookupFailedError("Open Food Facts asked us to slow down; try again in a minute.") from error
            raise LookupFailedError(f"Open Food Facts answered with HTTP {error.code}.") from error
        except (urllib.error.URLError, OSError) as error:  # DNS failure, refused, unreachable, timed out
            raise LookupOfflineError("Could not reach Open Food Facts.") from error
        try:
            payload = json.loads(body)
        except ValueError as error:
            raise LookupFailedError("Open Food Facts sent an unreadable answer.") from error
        return parse_product(barcode, payload)
