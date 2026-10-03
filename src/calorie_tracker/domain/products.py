"""Packaged-product data obtained from a barcode lookup, and the errors a lookup can raise."""

from __future__ import annotations

from dataclasses import dataclass

from .nutrition import Nutrients


class BarcodeReaderUnavailableError(Exception):
    """The barcode-reading library is not installed."""


class BarcodeImageError(Exception):
    """The file could not be opened as a picture."""


class ProductLookupError(Exception):
    """Base class for lookup failures."""


class LookupOfflineError(ProductLookupError):
    """The product database could not be reached (no internet, DNS failure, timeout)."""


class LookupFailedError(ProductLookupError):
    """The product database answered, but not with a usable response."""


@dataclass(frozen=True)
class ProductInfo:
    """A product as described by a product database; nutrients are per 100 g."""

    barcode: str
    name: str
    nutrients_per_100g: Nutrients
    brand: str = ""
    # Supported nutrient fields the database had no value for (they stay at zero).
    missing_nutrients: tuple[str, ...] = ()

    @property
    def display_name(self) -> str:
        if self.brand and self.brand.casefold() not in self.name.casefold():
            return f"{self.name} ({self.brand})" if self.name else self.brand
        return self.name
