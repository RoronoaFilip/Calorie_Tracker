"""Turn a photo of a product barcode into a draft food for the user to review."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from calorie_tracker.domain.barcode import lookup_candidates
from calorie_tracker.domain.products import (
    BarcodeImageError,
    BarcodeReaderUnavailableError,
    LookupFailedError,
    LookupOfflineError,
    ProductInfo,
)
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food

FOUND = "found"
NOT_FOUND = "not_found"
OFFLINE = "offline"
LOOKUP_FAILED = "lookup_failed"
NO_BARCODE = "no_barcode"
UNREADABLE = "unreadable_image"
READER_UNAVAILABLE = "reader_unavailable"


class BarcodeReader(Protocol):
    def read(self, path: Path | str) -> tuple[str, ...]: ...


class ProductLookup(Protocol):
    def lookup(self, barcode: str) -> ProductInfo | None: ...


@dataclass(frozen=True)
class PhotoImportResult:
    """Everything the UI needs: a draft food (possibly blank) and an honest explanation of how it was made."""

    status: str
    message: str
    barcode: str | None = None
    product: ProductInfo | None = None

    @property
    def found(self) -> bool:
        return self.status == FOUND

    def draft_food(self) -> Food | None:
        """A new, unsaved food. Blank nutrients when nothing was found; None when no form is useful."""
        if self.status in (NO_BARCODE, UNREADABLE, READER_UNAVAILABLE):
            return None
        if self.product is not None:
            return Food(str(uuid.uuid4()), self.product.display_name, self.product.nutrients_per_100g)
        return Food(str(uuid.uuid4()), "", Nutrients())


class ProductImportService:
    def __init__(self, reader: BarcodeReader, lookup: ProductLookup):
        self.reader = reader
        self.lookup = lookup

    def import_photo(self, path: Path | str) -> PhotoImportResult:
        try:
            codes = self.reader.read(path)
        except BarcodeReaderUnavailableError as error:
            return PhotoImportResult(READER_UNAVAILABLE, str(error))
        except BarcodeImageError as error:
            return PhotoImportResult(UNREADABLE, str(error))
        if not codes:
            return PhotoImportResult(
                NO_BARCODE,
                "No barcode was found in this photo. Try a sharper, well-lit picture where the bars fill "
                "much of the frame.",
            )
        barcode = codes[0]
        extra = f" ({len(codes) - 1} other barcode{'s' if len(codes) > 2 else ''} in the photo ignored.)" if len(codes) > 1 else ""
        try:
            product = None
            for candidate in lookup_candidates(barcode):
                product = self.lookup.lookup(candidate)
                if product is not None:
                    break
        except LookupOfflineError:
            return PhotoImportResult(
                OFFLINE,
                f"Barcode {barcode} was read, but there is no internet connection to look it up. "
                "Enter the nutrients by hand." + extra,
                barcode,
            )
        except LookupFailedError as error:
            return PhotoImportResult(
                LOOKUP_FAILED,
                f"Barcode {barcode} was read, but the product lookup failed: {error} Enter the nutrients by hand." + extra,
                barcode,
            )
        if product is None:
            return PhotoImportResult(
                NOT_FOUND,
                f"Barcode {barcode} is not in the Open Food Facts database. Enter the product by hand." + extra,
                barcode,
            )
        if product.missing_nutrients:
            message = (
                f"Barcode {barcode}: nutrients filled in from Open Food Facts. Not listed there and left at 0: "
                + ", ".join(name.replace("_", " ") for name in product.missing_nutrients)
                + ". Check everything against the package."
            )
        else:
            message = f"Barcode {barcode}: nutrients filled in from Open Food Facts. Check them against the package."
        return PhotoImportResult(FOUND, message + extra, barcode, product)
