"""Retail barcode normalisation and check-digit validation (EAN-13, EAN-8, UPC-A, UPC-E)."""

from __future__ import annotations

import re

_NON_DIGITS = re.compile(r"\D+")


def normalize_barcode(text: str) -> str:
    """Keep digits only, so ' 5 449000 000996 ' and '5449000000996' compare equal."""
    return _NON_DIGITS.sub("", text or "")


def _gtin_check_digit(body: str) -> int:
    """GS1 check digit for the digits *before* the check digit (weights 3,1,3,1… from the right)."""
    total = sum(int(char) * (3 if index % 2 == 0 else 1) for index, char in enumerate(reversed(body)))
    return (10 - total % 10) % 10


def _upce_to_upca(code: str) -> str:
    """Expand an 8-digit UPC-E (number system 0 or 1) to its 12-digit UPC-A."""
    system, digits, check = code[0], code[1:7], code[7]
    last = digits[5]
    if last in "012":
        body = digits[0:2] + last + "0000" + digits[2:5]
    elif last == "3":
        body = digits[0:3] + "00000" + digits[3:5]
    elif last == "4":
        body = digits[0:4] + "00000" + digits[4]
    else:
        body = digits[0:5] + "0000" + last
    return system + body + check


def is_valid_barcode(code: str) -> bool:
    """True when ``code`` is a well-formed EAN-13, UPC-A (12), EAN-8 or UPC-E (8) with a correct check digit."""
    if not code.isdigit():
        return False
    if len(code) in (12, 13):
        return _gtin_check_digit(code[:-1]) == int(code[-1])
    if len(code) == 8:
        if _gtin_check_digit(code[:-1]) == int(code[-1]):
            return True  # EAN-8
        if code[0] in "01":
            expanded = _upce_to_upca(code)
            return _gtin_check_digit(expanded[:-1]) == int(expanded[-1])
    return False


def lookup_candidates(code: str) -> tuple[str, ...]:
    """Spellings to try in a product database, best first.

    Databases usually store UPC-A as a 13-digit EAN with a leading zero, so both spellings are offered.
    """
    if len(code) == 13:
        return (code,)
    if len(code) == 12:
        return ("0" + code, code)
    if len(code) == 8:
        candidates = [code]
        if code[0] in "01":
            expanded = _upce_to_upca(code)
            candidates += ["0" + expanded, expanded]
        return tuple(candidates)
    return (code,)
