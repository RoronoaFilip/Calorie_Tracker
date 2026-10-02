from decimal import Decimal
import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food


NUTRIENT_LABELS = (
    ("calories", "Calories"), ("fat", "Fat (g)"), ("saturated_fat", "Saturated fat (g)"),
    ("carbohydrates", "Carbohydrates (g)"), ("sugars", "Sugars (g)"), ("protein", "Protein (g)"),
    ("fiber", "Fiber (g)"), ("omega_3", "Omega-3 (g)"), ("omega_6", "Omega-6 (g)"),
)


class FoodDialog(QDialog):
    def __init__(
        self,
        parent=None,
        food: Food | None = None,
        *,
        imported_food: Food | None = None,
        correction_fields: tuple[str, ...] = (),
        correction_errors: tuple[str, ...] = (),
    ):
        super().__init__(parent)
        if food:
            self.setWindowTitle("Edit food")
        elif imported_food:
            self.setWindowTitle("Correct imported food")
        else:
            self.setWindowTitle("Add food")
        self.setMinimumWidth(380)
        initial_food = food or imported_food
        self._food_id = initial_food.id if initial_food else str(uuid.uuid4())
        self._correction_fields = set(correction_fields)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit(initial_food.name if initial_food else "")
        self.name_input.setAccessibleName("Food name")
        form.addRow("Food name", self.name_input)
        self.nutrient_inputs = {}
        for key, label in NUTRIENT_LABELS:
            field = QDoubleSpinBox()
            field.setRange(0, 1_000_000)
            field.setDecimals(4)
            field.setSingleStep(1 if key == "calories" else 0.1)
            field.setAccessibleName(f"{label} per 100g")
            if initial_food:
                field.setValue(float(getattr(initial_food.nutrients_per_100g, key)))
            self.nutrient_inputs[key] = field
            form.addRow(label + " / 100 g", field)
        layout.addLayout(form)
        self.error_label = QLabel("")
        self.error_label.setObjectName("foodValidationErrors")
        self.error_label.setStyleSheet("color: #b53d48;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        if correction_errors:
            self.error_label.setText("\n".join(correction_errors))
        self._set_correction_state("food_name", self.name_input)
        self.name_input.textChanged.connect(lambda _: self._mark_corrected("food_name"))
        for key, field in self.nutrient_inputs.items():
            self._set_correction_state(key, field)
            field.valueChanged.connect(lambda _value, nutrient=key: self._mark_corrected(nutrient))
            field.lineEdit().textEdited.connect(lambda _text, nutrient=key: self._mark_corrected(nutrient))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        if self._correction_fields:
            labels = ", ".join(self._field_label(field) for field in sorted(self._correction_fields))
            self.error_label.setText(f"Correct the highlighted fields before saving: {labels}.")
            return
        if not self.name_input.text().strip():
            self.error_label.setText("Enter a food name.")
            return
        self.accept()

    def _set_correction_state(self, name: str, widget) -> None:
        if name not in self._correction_fields:
            return
        widget.setStyleSheet("border: 1px solid #b53d48;")
        label = self._field_label(name)
        widget.setAccessibleDescription(f"{label} needs correction before this food can be saved.")
        widget.setToolTip(f"Correct {label} before saving this imported food.")

    def _mark_corrected(self, name: str) -> None:
        if name not in self._correction_fields:
            return
        self._correction_fields.remove(name)
        widget = self.name_input if name == "food_name" else self.nutrient_inputs[name]
        widget.setStyleSheet("")
        widget.setAccessibleDescription("")
        widget.setToolTip("")
        if not self._correction_fields:
            self.error_label.clear()
        else:
            labels = ", ".join(self._field_label(field) for field in sorted(self._correction_fields))
            self.error_label.setText(f"Still needs correction: {labels}.")

    @staticmethod
    def _field_label(name: str) -> str:
        labels = {"food_name": "food name"}
        return labels.get(name, name.replace("_", " "))

    def food(self) -> Food:
        values = {name: Decimal(str(field.value())) for name, field in self.nutrient_inputs.items()}
        return Food(self._food_id, self.name_input.text().strip(), Nutrients(**values))
