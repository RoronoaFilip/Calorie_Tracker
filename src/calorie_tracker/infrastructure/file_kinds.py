"""Decide whether a dropped or chosen file is a CSV, a photo, or something unsupported."""

from __future__ import annotations

from pathlib import Path

CSV = "csv"
IMAGE = "image"
UNSUPPORTED = "unsupported"

IMAGE_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".bmp", ".gif", ".webp",
    ".tif", ".tiff", ".heic", ".heif",
})
IMAGE_FILTER = "Photos (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff *.heic *.heif);;All files (*)"


def _looks_like_image(header: bytes) -> bool:
    return (
        header.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"BM"))
        or header.startswith((b"II*\x00", b"MM\x00*"))
        or (header[:4] == b"RIFF" and header[8:12] == b"WEBP")
        or (header[4:8] == b"ftyp" and header[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"heif", b"hevc"))
    )


def classify_file(path: Path | str) -> str:
    """Return ``csv``, ``image`` or ``unsupported``.

    The file's real content wins over its name, so a photo without (or with a wrong) extension is still
    recognised; a ``.csv`` is accepted by name. Unreadable files are judged by extension alone.
    """
    target = Path(path)
    try:
        with target.open("rb") as stream:
            header = stream.read(16)
    except OSError:
        header = b""
    if header and _looks_like_image(header):
        return IMAGE
    suffix = target.suffix.casefold()
    if suffix == ".csv":
        return CSV
    if suffix in IMAGE_EXTENSIONS:
        return IMAGE
    return UNSUPPORTED
