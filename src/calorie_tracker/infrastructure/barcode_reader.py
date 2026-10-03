"""Find retail barcodes in a photo using zxing-cpp (offline) and Pillow for opening the picture."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from calorie_tracker.domain.barcode import is_valid_barcode, normalize_barcode
from calorie_tracker.domain.products import BarcodeImageError, BarcodeReaderUnavailableError

INSTALL_HINT = "Install the barcode reader with:  python -m pip install zxing-cpp pillow"
_MAX_SIDE = 1600


def _open_image(path: Path | str) -> Any:
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise BarcodeReaderUnavailableError(f"Pillow is not installed. {INSTALL_HINT}") from error
    try:
        with Image.open(path) as picture:
            picture.load()
            return ImageOps.exif_transpose(picture).convert("RGB")  # honour the phone's rotation flag
    except Exception as error:  # Pillow raises many unrelated types for bad/unsupported files
        raise BarcodeImageError(
            f"This file could not be opened as a picture ({error.__class__.__name__}). "
            "JPEG, PNG, WebP, BMP, GIF and TIFF photos are supported."
        ) from error


def _variants(picture: Any) -> Iterator[Any]:
    """The photo as-is, then easier versions of it for blurry or very large pictures."""
    from PIL import ImageOps

    yield picture
    if max(picture.size) > _MAX_SIDE:
        scale = _MAX_SIDE / max(picture.size)
        yield picture.resize((max(1, round(picture.width * scale)), max(1, round(picture.height * scale))))
    yield ImageOps.autocontrast(picture.convert("L"))


def _zxing_decode(picture: Any) -> list[str]:
    try:
        import zxingcpp
    except ImportError as error:
        raise BarcodeReaderUnavailableError(f"The barcode reader (zxing-cpp) is not installed. {INSTALL_HINT}") from error
    try:
        kinds = zxingcpp.BarcodeFormat
        results = zxingcpp.read_barcodes(picture, formats=kinds.EAN13 | kinds.EAN8 | kinds.UPCA | kinds.UPCE)
    except (AttributeError, TypeError):  # a zxing-cpp version with another format API: read everything
        results = zxingcpp.read_barcodes(picture)
    return [result.text for result in results]


class ZxingBarcodeReader:
    """Returns every *valid* retail barcode found in a picture, in the order they were read."""

    def __init__(
        self,
        decode: Callable[[Any], list[str]] | None = None,
        open_image: Callable[[Path | str], Any] | None = None,
    ):
        self._decode = decode or _zxing_decode
        self._open_image = open_image or _open_image

    def read(self, path: Path | str) -> tuple[str, ...]:
        picture = self._open_image(path)
        for variant in _variants(picture):
            found: list[str] = []
            for text in self._decode(variant):
                code = normalize_barcode(text)
                if is_valid_barcode(code) and code not in found:
                    found.append(code)
            if found:
                return tuple(found)
        return ()
