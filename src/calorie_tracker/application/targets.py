"""Daily targets and the "acceptable drift" around them.

A day's total is shown as a percentage of its target. The percentage counts as on track (green) when it lies in
the acceptable range, which is exactly 100% unless the person widens it, e.g. 85% to 110%.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

DEFAULT_DRIFT = (100, 100)
DRIFT_KEY = "target_drift"


def normalize_drift(low: int | None, high: int | None) -> tuple[int, int]:
    """A missing bound is 100%; if the bounds are the wrong way round they are swapped."""
    low = DEFAULT_DRIFT[0] if low is None else int(low)
    high = DEFAULT_DRIFT[1] if high is None else int(high)
    return (low, high) if low <= high else (high, low)


def load_drift(settings, key: str) -> tuple[int, int]:
    """The acceptable (lower %, upper %) range saved for one nutrient."""
    saved = (settings.get_json(DRIFT_KEY) or {}).get(key)
    try:
        return normalize_drift(saved[0], saved[1])
    except (TypeError, IndexError, ValueError):
        return DEFAULT_DRIFT


def percent_of_target(total: Decimal, target: Decimal) -> int:
    """Whole-number percentage of the target; may be above 100."""
    return int((total * 100 / target).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def is_on_track(percent: int, drift: tuple[int, int]) -> bool:
    return drift[0] <= percent <= drift[1]
