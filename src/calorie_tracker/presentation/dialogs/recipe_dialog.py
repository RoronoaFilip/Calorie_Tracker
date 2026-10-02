from decimal import Decimal
import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from calorie_tracker.application.catalogue import CatalogueService
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient
from calorie_tracker.infrastructure.repositories import FoodRepository, RecipeRecord


def amount_field(initial: float = 1) -> QDoubleSpinBox:
    field = QDoubleSpinBox()
    field.setRange(0, 100_000)
    field.setDecimals(2)
    field.setValue(initial)
    field.setSuffix(" g")
    return field


class RecipeDialog(QDialog):
    def __init__(self, catalogue: CatalogueService, foods: FoodRepository,
                 parent=None, recipe: RecipeRecord | None = None):
        super().__init__(parent)
        self.catalogue = catalogue
        self.foods = foods
        self.recipe_id = recipe.id if recipe else str(uuid.uuid4())
        self.ingredients: list[RecipeIngredient] = list(recipe.draft.ingredients) if recipe else []
        self.setWindowTitle("Edit recipe" if recipe else "Create recipe")
        self.resize(640, 580)
        outer = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit(recipe.draft.name if recipe else "")
        self.name_input.setAccessibleName("Recipe name")
        form.addRow("Recipe name", self.name_input)
        ingredient_weight = sum((item.amount_g for item in self.ingredients), Decimal("0"))
        self.yield_input = amount_field(float(ingredient_weight))
        self.yield_input.setMaximum(max(100_000, float(ingredient_weight)))
        self.yield_input.setDecimals(6)
        self.yield_input.setReadOnly(True)
        self.yield_input.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.yield_input.setAccessibleName("Calculated final recipe yield in grams")
        self.yield_input.setToolTip("Automatically calculated from the ingredient amounts below")
        form.addRow("Final yield", self.yield_input)
        outer.addLayout(form)

        self.food_picker = QComboBox()
        self.food_picker.setAccessibleName("Basic food ingredient")
        self.foods_by_id: dict[str, Food] = {}
        for food in self.foods.search():
            self.food_picker.addItem(food.name, food.id)
            self.foods_by_id[food.id] = food
        self.ingredient_amount = amount_field()
        self.ingredient_amount.setAccessibleName("Ingredient amount in grams")
        self.add_ingredient_button = QPushButton("Add ingredient")
        self.add_ingredient_button.clicked.connect(self._add_ingredient)
        picker_row = QHBoxLayout()
        picker_row.addWidget(self.food_picker, 1)
        picker_row.addWidget(self.ingredient_amount)
        picker_row.addWidget(self.add_ingredient_button)
        outer.addLayout(picker_row)

        self.ingredient_table = QTableWidget(0, 3)
        self.ingredient_table.setHorizontalHeaderLabels(["Basic food", "Amount", "Remove"])
        self.ingredient_table.setMinimumHeight(210)
        self.ingredient_table.verticalHeader().setVisible(False)
        header = self.ingredient_table.horizontalHeader()
        header.setMinimumHeight(36)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.ingredient_table.setColumnWidth(2, 116)
        self.ingredient_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.ingredient_table.setAccessibleName("Recipe ingredients")
        outer.addWidget(self.ingredient_table)

        self.error_label = QLabel("")
        self.error_label.setObjectName("recipeValidationErrors")
        self.error_label.setStyleSheet("color: #b23b45; font-weight: 600;")
        self.error_label.setWordWrap(True)
        outer.addWidget(self.error_label)
        self.warning_label = QLabel("")
        self.warning_label.setObjectName("recipeValidationWarnings")
        self.warning_label.setStyleSheet("color: #8a5b08; background: #fff5dc; padding: 8px; border-radius: 6px;")
        self.warning_label.setWordWrap(True)
        outer.addWidget(self.warning_label)
        self.preview_label = QLabel("")
        self.preview_label.setObjectName("recipeNutritionPreview")
        self.preview_label.setStyleSheet("color: #536175;")
        self.preview_label.setWordWrap(True)
        outer.addWidget(self.preview_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setObjectName("primaryButton")
        self.save_button.setAccessibleName("Save recipe")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.name_input.textChanged.connect(self._refresh_validation)
        self._render_ingredients()
        self._refresh_validation()

    def _draft(self) -> RecipeDraft:
        return RecipeDraft(
            self.name_input.text(), Decimal(str(self.yield_input.value())), tuple(self.ingredients)
        )

    def _add_ingredient(self) -> None:
        food_id = self.food_picker.currentData()
        food = self.foods_by_id.get(food_id)
        if food is None:
            return
        self.ingredients.append(RecipeIngredient(food, Decimal(str(self.ingredient_amount.value()))))
        self._render_ingredients()
        self._update_calculated_yield()
        self._refresh_validation()

    def _remove_ingredient(self, index: int) -> None:
        del self.ingredients[index]
        self._render_ingredients()
        self._update_calculated_yield()
        self._refresh_validation()

    def _update_calculated_yield(self) -> None:
        ingredient_weight = sum((item.amount_g for item in self.ingredients), Decimal("0"))
        self.yield_input.setMaximum(max(100_000, float(ingredient_weight)))
        self.yield_input.setValue(float(ingredient_weight))

    def _render_ingredients(self) -> None:
        self.ingredient_table.setRowCount(len(self.ingredients))
        for index, ingredient in enumerate(self.ingredients):
            self.ingredient_table.setItem(index, 0, QTableWidgetItem(ingredient.food.name))
            self.ingredient_table.setItem(index, 1, QTableWidgetItem(f"{ingredient.amount_g:g} g"))
            remove = QPushButton("Remove")
            remove.setObjectName("recipeRemoveButton")
            remove.setAccessibleName(f"Remove {ingredient.food.name}")
            remove.setToolTip(f"Remove {ingredient.food.name} from the recipe")
            remove.clicked.connect(lambda checked=False, row=index: self._remove_ingredient(row))
            self.ingredient_table.setCellWidget(index, 2, remove)
            self.ingredient_table.setRowHeight(index, 40)

    def _refresh_validation(self) -> None:
        preview = self.catalogue.validate_recipe(self._draft(), editing_id=self.recipe_id)
        self.error_label.setText("\n".join(issue.message for issue in preview.errors))
        self.warning_label.setText("\n".join(f"Warning: {issue.message}" for issue in preview.warnings))
        self.warning_label.setVisible(bool(preview.warnings))
        self.save_button.setEnabled(preview.is_valid)
        if preview.is_valid:
            totals = preview.per_100g
            self.preview_label.setText(
                f"Per 100g: {totals.calories:.2f} kcal · "
                f"Protein {totals.protein:.2f}g · "
                f"Carbs {totals.carbohydrates:.2f}g · "
                f"Fat {totals.fat:.2f}g · "
                f"Fiber {totals.fiber:.2f}g"
            )
        else:
            self.preview_label.setText("Add a name, positive final yield, and at least one valid ingredient.")

    def _validate_and_accept(self) -> None:
        preview = self.catalogue.validate_recipe(self._draft(), editing_id=self.recipe_id)
        self.error_label.setText("\n".join(issue.message for issue in preview.errors))
        self.warning_label.setText("\n".join(f"Warning: {issue.message}" for issue in preview.warnings))
        if preview.is_valid:
            self.accept()

    def draft(self) -> RecipeDraft:
        return self._draft()
