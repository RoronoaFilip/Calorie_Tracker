"""Turn whatever was dropped or chosen (files, zips) into an ordered list of things to import."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .csv_kind import CsvKind, classify_csv
from .file_kinds import CSV, IMAGE, ZIP, classify_file
from .zip_intake import ZipIntakeError, extract_zip

KIND_FOODS = "foods"
KIND_IMAGE = "image"
KIND_RECIPES = "recipes"
KIND_DIARY = "diary"
KIND_UNKNOWN_CSV = "unknown_csv"

# Foods first so the recipes and diary rows that use new foods can find them; photos create foods too.
_ORDER = {KIND_FOODS: 0, KIND_IMAGE: 1, KIND_RECIPES: 2, KIND_DIARY: 3, KIND_UNKNOWN_CSV: 4}
_DIARY_DATE_IN_NAME = re.compile(r"diary-(\d{4})-(\d{2})-(\d{2})", re.IGNORECASE)
_KIND_OF_CSV = {
    CsvKind.FOODS: KIND_FOODS,
    CsvKind.DIARY: KIND_DIARY,
    CsvKind.RECIPES: KIND_RECIPES,
    CsvKind.UNKNOWN: KIND_UNKNOWN_CSV,
}


@dataclass(frozen=True)
class IntakeItem:
    kind: str
    path: Path
    label: str
    diary_date: date | None = None


@dataclass(frozen=True)
class IntakePlan:
    items: tuple[IntakeItem, ...]
    problems: tuple[str, ...]


def diary_date_from_name(name: str) -> date | None:
    """``diary-2026-10-05.csv`` -> that date; an impossible date or a different name -> ``None``."""
    found = _DIARY_DATE_IN_NAME.search(name)
    if not found:
        return None
    try:
        return date(int(found.group(1)), int(found.group(2)), int(found.group(3)))
    except ValueError:
        return None


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _item_for(path: Path, label: str, source_name: str) -> IntakeItem | str:
    kind = classify_file(path)
    if kind == IMAGE:
        return IntakeItem(KIND_IMAGE, path, label)
    if kind == CSV:
        csv_kind = _KIND_OF_CSV[classify_csv(path)]
        when = diary_date_from_name(source_name) if csv_kind == KIND_DIARY else None
        return IntakeItem(csv_kind, path, label, when)
    return f"Skipped {label}: only CSV files, photos and zip files can be imported."


def build_intake_plan(paths: Sequence[Path | str], workdir: Path) -> IntakePlan:
    """Expand zips, classify every file, drop exact duplicates, and order the result for importing."""
    problems: list[str] = []
    candidates: list[tuple[Path, str, str]] = []  # path, label for messages, original file name
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            problems.append(f"Skipped {path.name or str(path)}: it is not a file.")
            continue
        if classify_file(path) == ZIP:
            try:
                extracted = extract_zip(path, workdir / f"zip-{len(candidates):03d}")
            except ZipIntakeError as error:
                problems.append(str(error))
                continue
            candidates.extend((item.path, item.origin, Path(item.origin).name) for item in extracted)
        else:
            candidates.append((path, path.name, path.name))
    items: list[IntakeItem] = []
    seen: set[str] = set()
    for path, label, source_name in candidates:
        try:
            digest = _digest(path)
        except OSError:
            problems.append(f"Skipped {label}: the file could not be read.")
            continue
        if digest in seen:
            problems.append(f"Skipped {label}: the same file was already included.")
            continue
        seen.add(digest)
        result = _item_for(path, label, source_name)
        if isinstance(result, str):
            problems.append(result)
        else:
            items.append(result)
    items.sort(key=lambda item: (_ORDER[item.kind], item.diary_date or date.max if item.kind == KIND_DIARY else date.max))
    return IntakePlan(tuple(items), tuple(problems))
