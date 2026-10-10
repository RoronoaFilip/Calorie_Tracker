"""Safely pull the CSV files and photos out of a zip, following the app's folder rules.

Rules: only CSV files and photos are taken; more than one folder is an error; files at the root plus the
files of exactly one folder are all taken; folders inside that folder are ignored. Member paths are never
used to write files, so a hostile zip cannot write outside the work folder.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .file_kinds import IMAGE_EXTENSIONS

MAX_FILES = 500
MAX_TOTAL_BYTES = 200 * 1024 * 1024
_CHUNK = 1024 * 1024
_UNSAFE_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ZipIntakeError(ValueError):
    """The zip cannot be imported; the message explains why in plain words."""


@dataclass(frozen=True)
class ExtractedFile:
    path: Path
    origin: str  # for messages, for example "export.zip/photos/a.jpg"


def _declared_size(info: zipfile.ZipInfo) -> int:
    return info.file_size


def _parts(name: str) -> list[str]:
    return [part for part in name.replace("\\", "/").split("/") if part not in ("", ".")]


def _is_unsafe(name: str, parts: list[str]) -> bool:
    normalized = name.replace("\\", "/")
    return normalized.startswith("/") or bool(re.match(r"^[A-Za-z]:", normalized)) or ".." in parts


def _is_junk(parts: list[str]) -> bool:
    return any(part == "__MACOSX" or part.startswith(".") for part in parts)


def _safe_filename(name: str) -> str:
    cleaned = _UNSAFE_NAME_CHARS.sub("_", name).strip(" .") or "file"
    suffix = PurePosixPath(cleaned).suffix
    return cleaned[:80 - len(suffix)] + suffix if len(cleaned) > 80 else cleaned


def _wanted(filename: str) -> bool:
    suffix = PurePosixPath(filename).suffix.casefold()
    return suffix == ".csv" or suffix in IMAGE_EXTENSIONS


def extract_zip(
    zip_path: Path | str,
    workdir: Path,
    *,
    max_files: int = MAX_FILES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
) -> tuple[ExtractedFile, ...]:
    source = Path(zip_path)
    label = source.name
    try:
        archive = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError) as error:
        raise ZipIntakeError(f"{label} is not a readable zip file.") from error
    with archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        if len(members) > max_files:
            raise ZipIntakeError(f"{label} holds {len(members)} files; the limit is {max_files}.")
        entries: list[tuple[zipfile.ZipInfo, list[str]]] = []
        for info in members:
            parts = _parts(info.filename)
            if _is_unsafe(info.filename, parts):
                raise ZipIntakeError(f"{label} contains an unsafe file path ({info.filename!r}), so it was not imported.")
            if parts and not _is_junk(parts):
                entries.append((info, parts))
        folders = {parts[0] for _info, parts in entries if len(parts) > 1}
        if len(folders) > 1:
            raise ZipIntakeError(
                f"{label} contains more than one folder ({', '.join(sorted(folders))}). "
                "Put everything at the top level or in a single folder."
            )
        chosen = [
            (info, parts) for info, parts in entries
            if len(parts) <= 2 and _wanted(parts[-1])  # root files and the single folder's own files
        ]
        if not chosen:
            raise ZipIntakeError(f"{label} contains no CSV files or photos.")
        if sum(_declared_size(info) for info, _parts_ in chosen) > max_total_bytes:
            raise ZipIntakeError(f"{label} is too large to import (limit {max_total_bytes // (1024 * 1024)} MB).")
        workdir.mkdir(parents=True, exist_ok=True)
        extracted: list[ExtractedFile] = []
        written = 0
        for index, (info, parts) in enumerate(sorted(chosen, key=lambda item: "/".join(item[1]).casefold())):
            if info.flag_bits & 0x1:
                raise ZipIntakeError(f"{label} is password-protected.")
            target = workdir / f"{index:03d}-{_safe_filename(parts[-1])}"
            try:
                with archive.open(info) as reader, target.open("wb") as writer:
                    while chunk := reader.read(_CHUNK):
                        written += len(chunk)
                        if written > max_total_bytes:
                            raise ZipIntakeError(
                                f"{label} is too large to import (limit {max_total_bytes // (1024 * 1024)} MB)."
                            )
                        writer.write(chunk)
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError) as error:
                raise ZipIntakeError(f"{label} could not be read ({parts[-1]}).") from error
            extracted.append(ExtractedFile(target, f"{label}/{'/'.join(parts)}"))
        return tuple(extracted)
