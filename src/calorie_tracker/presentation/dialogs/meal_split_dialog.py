from decimal import Decimal

from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.domain.diary import MEALS, MealPortion, normalize_portions


def _grams(value: Decimal) -> str:
    return f"{value.normalize():f}"


def describe_portions(portions: tuple[MealPortion, ...], unit: str = "g") -> str:
    """'Lunch' for a single meal, otherwise 'Lunch 200 g · Dinner 300 g' (unit "pcs" for counted foods)."""
    if len(portions) == 1:
        return portions[0].meal
    return " · ".join(f"{p.meal} {_grams(p.amount_g)} {unit}" for p in portions)


class MealSplitDialog(QDialog):
    """Share one amount between any of the four meals; the parts must add up to the total."""

    def __init__(
        self,
        food_name: str,
        total_g: Decimal,
        current: tuple[MealPortion, ...] = (),
        parent: QWidget | None = None,
        unit: str = "g",
    ):
        super().__init__(parent)
        self.total_g = total_g
        self.unit = unit
        self.portions: tuple[MealPortion, ...] = ()
        self.setWindowTitle("Split between meals")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        title = QLabel(f"{food_name} · {_grams(total_g)} {unit} in total")
        title.setStyleSheet("font-weight: 650; font-size: 17px;")
        title.setWordWrap(True)
        layout.addWidget(title)
        hint = QLabel(
            f"Type how many {'items' if unit == 'pcs' else 'grams'} go to each meal, "
            "or use Rest to put what is left in a meal."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self.amount_inputs: dict[str, QDoubleSpinBox] = {}
        start = {portion.meal: portion.amount_g for portion in current}
        for row, meal in enumerate(MEALS):
            grid.addWidget(QLabel(meal), row, 0)
            spin = QDoubleSpinBox()
            spin.setObjectName(f"splitAmount{meal}")
            spin.setAccessibleName(f"{'Items' if unit == 'pcs' else 'Grams'} for {meal}")
            spin.setDecimals(2)
            spin.setRange(0, float(total_g))
            spin.setSuffix(f" {unit}")
            spin.setValue(float(start.get(meal, Decimal(0))))
            spin.valueChanged.connect(self._refresh)
            self.amount_inputs[meal] = spin
            grid.addWidget(spin, row, 1)
            rest = QPushButton("Rest")
            rest.setObjectName(f"splitRest{meal}")
            rest.setAccessibleName(f"Put the remaining amount in {meal}")
            rest.setToolTip(f"Put whatever is not yet assigned in {meal}")
            rest.clicked.connect(lambda checked=False, name=meal: self.fill_rest(name))
            grid.addWidget(rest, row, 2)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        self.status_label = QLabel()
        self.status_label.setObjectName("splitStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.apply_button = QPushButton("Apply split")
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self.apply)
        actions.addWidget(cancel)
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)
        self._refresh()
        first = next(
            (meal for meal in MEALS if start.get(meal, 0) > 0), MEALS[0]
        )
        self.amount_inputs[first].setFocus()
        self.amount_inputs[first].selectAll()

    def _values(self) -> list[tuple[str, Decimal]]:
        return [(meal, Decimal(str(round(spin.value(), 2)))) for meal, spin in self.amount_inputs.items()]

    def fill_rest(self, meal: str) -> None:
        others = sum(value for name, value in self._values() if name != meal)
        remaining = max(Decimal(0), self.total_g - others)
        self.amount_inputs[meal].setValue(float(remaining))

    def _refresh(self, *_args) -> None:
        assigned = sum(value for _, value in self._values())
        remaining = self.total_g - assigned
        if abs(remaining) <= Decimal("0.005") and assigned > 0:
            self.status_label.setText(f"✓ All {_grams(self.total_g)} {self.unit} are assigned.")
            self.status_label.setStyleSheet("color: #1f7a4d; font-weight: 600;")
            self.apply_button.setEnabled(True)
        elif remaining > 0:
            self.status_label.setText(
                f"{_grams(assigned)} {self.unit} assigned · "
                f"{_grams(remaining.quantize(Decimal('0.01')))} {self.unit} still to place."
            )
            self.status_label.setStyleSheet("color: #9a6700; font-weight: 600;")
            self.apply_button.setEnabled(False)
        else:
            self.status_label.setText(f"✕ Over by {_grams((-remaining).quantize(Decimal('0.01')))} {self.unit}.")
            self.status_label.setStyleSheet("color: #b53d48; font-weight: 600;")
            self.apply_button.setEnabled(False)

    def apply(self) -> None:
        try:
            self.portions = normalize_portions(self.total_g, self._values(), self.unit)
        except ValueError as error:
            self.status_label.setText(str(error))
            return
        self.accept()
