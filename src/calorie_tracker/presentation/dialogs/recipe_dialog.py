from dataclasses import replace
from decimal import Decimal
import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QCompleter,
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
    QWidget,
)

from calorie_tracker.application.catalogue import CatalogueService
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient
from calorie_tracker.infrastructure.repositories import FoodRepository, RecipeRecord
from calorie_tracker.presentation.amount_input import AmountSpinBox

_ROW_HEIGHT = 48


def amount_field(initial: float = 1) -> QDoubleSpinBox:
    field = QDoubleSpinBox()
    field.setRange(0, 100_000)
    field.setDecimals(2)
    field.setValue(initial)
    field.setSuffix(" g")
    return field


def _decimal(value: float) -> Decimal:
    return Decimal(str(round(value, 4)))


class RecipeDialog(QDialog):
    """Create or edit a recipe.

    Ingredients are found by typing (any part of the name matches) or by opening the list. Grams for weighed
    foods, a number of items for foods counted per item. Enter adds the ingredient while you are in the
    ingredient row, and saves the recipe anywhere else.
    """

    def __init__(self, catalogue: CatalogueService, foods: FoodRepository,
                 parent=None, recipe: RecipeRecord | None = None):
        super().__init__(parent)
        self.catalogue = catalogue
        self.foods = foods
        self.recipe_id = recipe.id if recipe else str(uuid.uuid4())
        self.ingredients: list[RecipeIngredient] = list(recipe.draft.ingredients) if recipe else []
        self.setWindowTitle("Edit recipe" if recipe else "Create recipe")
        self.resize(720, 640)
        outer = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit(recipe.draft.name if recipe else "")
        self.name_input.setAccessibleName("Recipe name")
        form.addRow("Recipe name", self.name_input)
        weighed = self._weighed_total()
        start_yield = float(recipe.draft.yield_g) if recipe and self._has_counted() else float(weighed)
        self.yield_input = QDoubleSpinBox()
        self.yield_input.setRange(0, 100_000)
        self.yield_input.setSuffix(" g")
        self.yield_input.setMaximum(max(100_000, start_yield))
        self.yield_input.setDecimals(6)
        self.yield_input.setValue(start_yield)
        self.yield_input.setAccessibleName("Final recipe yield in grams")
        form.addRow("Final yield", self.yield_input)
        outer.addLayout(form)
        self.yield_hint = QLabel(
            "Counted ingredients have no weight, so enter the final weight of the finished recipe in grams."
        )
        self.yield_hint.setObjectName("recipeYieldHint")
        self.yield_hint.setWordWrap(True)
        self.yield_hint.setStyleSheet("color: #536175;")
        outer.addWidget(self.yield_hint)

        self.food_picker = QComboBox()
        self.food_picker.setAccessibleName("Basic food ingredient")
        self.food_picker.setEditable(True)
        self.food_picker.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.food_picker.lineEdit().setPlaceholderText("Type to search a food…")
        completer = self.food_picker.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)  # "chick" finds "Grilled chicken breast"
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(10)
        self.foods_by_id: dict[str, Food] = {}
        self._foods_by_name: dict[str, Food] = {}
        for food in self.foods.search():
            self.food_picker.addItem(food.name, food.id)
            self.foods_by_id[food.id] = food
            self._foods_by_name.setdefault(food.name.strip().casefold(), food)
        self.food_picker.setCurrentIndex(-1)
        self.ingredient_amount = AmountSpinBox()
        self.ingredient_amount.setAccessibleName("Ingredient amount")
        self.add_ingredient_button = QPushButton("Add ingredient")
        self.add_ingredient_button.setAutoDefault(False)
        self.add_ingredient_button.clicked.connect(self._add_ingredient)
        picker_row = QHBoxLayout()
        picker_row.addWidget(self.food_picker, 1)
        picker_row.addWidget(self.ingredient_amount)
        picker_row.addWidget(self.add_ingredient_button)
        outer.addLayout(picker_row)
        self.picker_message = QLabel("")
        self.picker_message.setObjectName("recipePickerMessage")
        self.picker_message.setStyleSheet("color: #b23b45;")
        self.picker_message.setVisible(False)
        outer.addWidget(self.picker_message)
        self.food_picker.lineEdit().textChanged.connect(self._sync_amount_unit)

        self.ingredient_table = QTableWidget(0, 3)
        self.ingredient_table.setHorizontalHeaderLabels(["Basic food", "Amount", "Remove"])
        self.ingredient_table.setMinimumHeight(210)
        self.ingredient_table.verticalHeader().setVisible(False)
        self.ingredient_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.ingredient_table.horizontalHeader()
        header.setMinimumHeight(36)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.ingredient_table.setColumnWidth(1, 170)
        self.ingredient_table.setColumnWidth(2, 120)
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
        self.save_button.setDefault(True)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.name_input.textChanged.connect(self._refresh_validation)
        self._sync_yield_mode()
        self._render_ingredients()
        self._refresh_validation()
        self.yield_input.valueChanged.connect(self._refresh_validation)
        (self.food_picker if self.name_input.text() else self.name_input).setFocus()

    # ---- ingredient list state -----------------------------------------------------------------------

    def _has_counted(self) -> bool:
        return any(item.food.is_counted for item in self.ingredients)

    def _weighed_total(self) -> Decimal:
        return sum((item.amount_g for item in self.ingredients if not item.food.is_counted), Decimal("0"))

    def _draft(self) -> RecipeDraft:
        return RecipeDraft(
            self.name_input.text(), Decimal(str(self.yield_input.value())), tuple(self.ingredients)
        )

    def _sync_yield_mode(self) -> None:
        """The yield follows the ingredient weights, unless counted items (which weigh nothing known) are used."""
        counted = self._has_counted()
        self.yield_input.setReadOnly(not counted)
        self.yield_input.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.UpDownArrows if counted else QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.yield_input.setToolTip(
            "Enter the weight of the finished recipe" if counted
            else "Automatically calculated from the ingredient amounts below"
        )
        self.yield_hint.setVisible(counted)

    def _update_calculated_yield(self) -> None:
        self._sync_yield_mode()
        if self._has_counted():
            return  # the person gives the yield; keep what they entered
        total = self._weighed_total()
        self.yield_input.setMaximum(max(100_000, float(total)))
        self.yield_input.setValue(float(total))

    # ---- choosing an ingredient -----------------------------------------------------------------------

    def _selected_food(self) -> Food | None:
        """The typed text as a food: an exact name, or the only food whose name contains the text."""
        text = self.food_picker.currentText().strip().casefold()
        if not text:
            return None
        exact = self._foods_by_name.get(text)
        if exact is not None:
            return exact
        matches = [food for key, food in self._foods_by_name.items() if text in key]
        return matches[0] if len(matches) == 1 else None

    def _sync_amount_unit(self, *_args) -> None:
        food = self._selected_food()
        if food is not None:
            wanted = "count" if food.is_counted else "g"
            if wanted != self.ingredient_amount.basis:
                self.ingredient_amount.set_basis(wanted)
        self.picker_message.setVisible(False)

    def _add_ingredient(self) -> None:
        food = self._selected_food()
        if food is None:
            typed = self.food_picker.currentText().strip()
            self.picker_message.setText(
                "Choose an ingredient: type part of its name and pick it from the list."
                if not typed else f"“{typed}” is not one food. Keep typing or pick one from the list."
            )
            self.picker_message.setVisible(True)
            self.food_picker.setFocus()
            return
        self.ingredients.append(RecipeIngredient(food, _decimal(self.ingredient_amount.value())))
        self._render_ingredients()
        self._update_calculated_yield()
        self._refresh_validation()
        # Ready for the next ingredient.
        self.picker_message.setVisible(False)
        self.food_picker.setCurrentIndex(-1)
        self.food_picker.lineEdit().clear()
        self.ingredient_amount.set_basis("g")
        self.food_picker.setFocus()
        self.ingredient_table.scrollToBottom()

    def _remove_ingredient(self, index: int) -> None:
        del self.ingredients[index]
        self._render_ingredients()
        self._update_calculated_yield()
        self._refresh_validation()

    def _amount_changed(self, index: int, value: float) -> None:
        """An amount edited in the table updates the ingredient, the yield and the nutrition straight away."""
        if index >= len(self.ingredients):
            return
        self.ingredients[index] = replace(self.ingredients[index], amount_g=_decimal(value))
        self._update_calculated_yield()
        self._refresh_validation()

    def _render_ingredients(self) -> None:
        self.ingredient_table.setRowCount(len(self.ingredients))
        for index, ingredient in enumerate(self.ingredients):
            name = QTableWidgetItem(ingredient.food.name)
            name.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            name.setToolTip(ingredient.food.name)
            self.ingredient_table.setItem(index, 0, name)
            amount = AmountSpinBox("count" if ingredient.food.is_counted else "g", float(ingredient.amount_g))
            amount.setObjectName(f"ingredientAmount{index}")
            amount.setAccessibleName(f"Amount of {ingredient.food.name}")
            amount.setAlignment(Qt.AlignmentFlag.AlignRight)
            amount.valueChanged.connect(lambda value, row=index: self._amount_changed(row, value))
            self.ingredient_table.setCellWidget(index, 1, amount)
            remove = QPushButton("Remove")
            remove.setObjectName("recipeRemoveButton")
            remove.setAccessibleName(f"Remove {ingredient.food.name}")
            remove.setToolTip(f"Remove {ingredient.food.name} from the recipe")
            remove.clicked.connect(lambda checked=False, row=index: self._remove_ingredient(row))
            self.ingredient_table.setCellWidget(index, 2, remove)
            self.ingredient_table.setRowHeight(index, _ROW_HEIGHT)

    # ---- validation and saving ------------------------------------------------------------------------

    def _refresh_validation(self, *_args) -> None:
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

    def handle_enter(self, focus: QWidget) -> bool:
        """Enter adds the ingredient while you are in the ingredient row, and saves the recipe anywhere else."""
        in_ingredient_row = focus in (
            self.food_picker, self.food_picker.lineEdit(), self.ingredient_amount,
            self.ingredient_amount.lineEdit(),
        )
        if in_ingredient_row:
            self._add_ingredient()
        elif self.ingredient_table.isAncestorOf(focus):
            self.food_picker.setFocus()  # an amount was edited in the table: confirm it, keep working
        else:
            self._validate_and_accept()
        return True

    def _validate_and_accept(self) -> None:
        preview = self.catalogue.validate_recipe(self._draft(), editing_id=self.recipe_id)
        self.error_label.setText("\n".join(issue.message for issue in preview.errors))
        self.warning_label.setText("\n".join(f"Warning: {issue.message}" for issue in preview.warnings))
        if preview.is_valid:
            self.accept()

    def draft(self) -> RecipeDraft:
        return self._draft()
