from decimal import Decimal, InvalidOperation
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
    def __init__(self, parent=None, food: Food | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit food" if food else "Add food")
        self.setMinimumWidth(380)
        self._food_id = food.id if food else str(uuid.uuid4())
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit(food.name if food else "")
        self.name_input.setAccessibleName("Food name")
        form.addRow("Food name", self.name_input)
        self.nutrient_inputs = {}
        for key, label in NUTRIENT_LABELS:
            field = QDoubleSpinBox()
            field.setRange(0, 1_000_000)
            field.setDecimals(4)
            field.setSingleStep(1 if key == "calories" else 0.1)
            field.setAccessibleName(f"{label} per 100 g")
            if food:
                field.setValue(float(getattr(food.nutrients_per_100g, key)))
            self.nutrient_inputs[key] = field
            form.addRow(label + " / 100 g", field)
        layout.addLayout(form)
        self.error_label = QLabel("")
        self.error_label.setObjectName("foodValidationErrors")
        self.error_label.setStyleSheet("color: #b53d48;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        if not self.name_input.text().strip():
            self.error_label.setText("Enter a food name.")
            return
        self.accept()

    def food(self) -> Food:
        values = {name: Decimal(str(field.value())) for name, field in self.nutrient_inputs.items()}
        return Food(self._food_id, self.name_input.text().strip(), Nutrients(**values))
