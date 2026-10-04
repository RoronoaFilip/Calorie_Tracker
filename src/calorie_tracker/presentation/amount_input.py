"""A number box for amounts that are either grams or a count of items."""

from __future__ import annotations

from PySide6.QtWidgets import QDoubleSpinBox

from calorie_tracker.domain.nutrition import BASIS_COUNT, BASIS_GRAMS, unit_label

GRAM_DECIMALS = 1
COUNT_DECIMALS = 2  # so that a half (0.5) or a third (0.33) can be typed


class AmountSpinBox(QDoubleSpinBox):
    """Grams for weighed foods and recipes, a number of items (halves, thirds... allowed) for counted foods."""

    def __init__(self, basis: str = BASIS_GRAMS, value: float = 100, parent=None):
        super().__init__(parent)
        self.setRange(0, 100_000)
        self.basis = BASIS_GRAMS
        self.set_basis(basis, value)

    def set_basis(self, basis: str, value: float | None = None) -> None:
        """Switch between grams and items; ``value`` (if given) is the new amount, else a sensible default."""
        self.basis = basis
        counted = basis == BASIS_COUNT
        self.setDecimals(COUNT_DECIMALS if counted else GRAM_DECIMALS)
        self.setSingleStep(0.5 if counted else 10)
        self.setMinimum(0.01 if counted else 0.1)
        self.setSuffix(f" {unit_label(basis)}")
        if value is None:
            value = 1 if counted else 100
        self.setValue(value)
        self.setAccessibleName("Number of items" if counted else "Amount in grams")
