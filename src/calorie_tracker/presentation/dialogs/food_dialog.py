from decimal import Decimal
import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.domain.nutrition import BASIS_COUNT, BASIS_GRAMS, Nutrients
from calorie_tracker.domain.recipes import Food


NUTRIENT_LABELS = (
    ("calories", "Calories"), ("fat", "Fat (g)"), ("saturated_fat", "Saturated fat (g)"),
    ("carbohydrates", "Carbohydrates (g)"), ("sugars", "Sugars (g)"), ("protein", "Protein (g)"),
    ("fiber", "Fiber (g)"), ("omega_3", "Omega-3 (g)"), ("omega_6", "Omega-6 (g)"),
)


BANNER_LEVELS = ("info", "success", "warning")
_THUMBNAIL_SIZE = (150, 110)


class FoodDialog(QDialog):
    """Add/edit a food. ``banner`` ((level, text)) and ``image_path`` explain where a prefilled food came from."""

    def __init__(
        self,
        parent=None,
        food: Food | None = None,
        *,
        imported_food: Food | None = None,
        correction_fields: tuple[str, ...] = (),
        correction_errors: tuple[str, ...] = (),
        title: str | None = None,
        banner: tuple[str, str] | None = None,
        image_path: str | None = None,
    ):
        super().__init__(parent)
        if title:
            self.setWindowTitle(title)
        elif food:
            self.setWindowTitle("Edit food")
        elif imported_food:
            self.setWindowTitle("Correct imported food")
        else:
            self.setWindowTitle("Add food")
        self.setMinimumWidth(560 if banner else 460)
        initial_food = food or imported_food
        self._food_id = initial_food.id if initial_food else str(uuid.uuid4())
        self._correction_fields = set(correction_fields)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        self.banner_frame: QFrame | None = None
        self.banner_label: QLabel | None = None
        self.photo_label: QLabel | None = None
        if banner or image_path:
            self._build_banner(banner, image_path, layout)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setVerticalSpacing(9)
        form.setHorizontalSpacing(14)
        self.name_input = QLineEdit(initial_food.name if initial_food else "")
        self.name_input.setAccessibleName("Food name")
        self.name_input.setMinimumWidth(300)
        self.name_input.setCursorPosition(0)
        self.name_input.textChanged.connect(self.name_input.setToolTip)  # long names stay readable on hover
        self.name_input.setToolTip(self.name_input.text())
        form.addRow("Food name", self.name_input)
        # How the values below are given: per 100 g (default) or per single item (an egg, a slice...).
        self.basis_per_100g = QRadioButton("Per 100 g")
        self.basis_per_100g.setObjectName("basisPer100g")
        self.basis_per_item = QRadioButton("Per item (count)")
        self.basis_per_item.setObjectName("basisPerItem")
        self.basis_per_100g.setToolTip("Nutrients are given for 100 g. You log how many grams you ate.")
        self.basis_per_item.setToolTip(
            "Nutrients are given for one item, e.g. one large egg. You log how many items you ate (halves are fine)."
        )
        basis_row = QHBoxLayout()
        basis_row.addWidget(self.basis_per_100g)
        basis_row.addWidget(self.basis_per_item)
        basis_row.addStretch(1)
        basis_box = QWidget()
        basis_box.setLayout(basis_row)
        basis_row.setContentsMargins(0, 0, 0, 0)
        self.basis_widget = basis_box
        starting_basis = initial_food.basis if initial_food else BASIS_GRAMS
        (self.basis_per_item if starting_basis == BASIS_COUNT else self.basis_per_100g).setChecked(True)
        form.addRow("Nutrients are given", basis_box)
        self._nutrient_row_labels: dict[str, QLabel] = {}
        self.nutrient_inputs = {}
        for key, label in NUTRIENT_LABELS:
            field = QDoubleSpinBox()
            field.setRange(0, 1_000_000)
            field.setDecimals(4)
            field.setSingleStep(1 if key == "calories" else 0.1)
            field.setMinimumWidth(160)  # room for the number plus the stepper buttons
            field.setAlignment(Qt.AlignmentFlag.AlignRight)
            field.setAccessibleName(f"{label} per 100g")
            if initial_food:
                field.setValue(float(getattr(initial_food.nutrients_per_100g, key)))
            self.nutrient_inputs[key] = field
            row_label = QLabel(label)
            self._nutrient_row_labels[key] = row_label
            form.addRow(row_label, field)
        layout.addLayout(form)
        self.basis_per_item.toggled.connect(self._basis_toggled)
        self._update_basis_labels()
        self.error_label = QLabel("")
        self.error_label.setObjectName("foodValidationErrors")
        self.error_label.setStyleSheet("color: #b53d48;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        if correction_errors:
            self.error_label.setText("\n".join(correction_errors))
        self._set_correction_state("food_name", self.name_input)
        self._set_correction_state("basis", self.basis_widget)
        self.name_input.textChanged.connect(lambda _: self._mark_corrected("food_name"))
        for key, field in self.nutrient_inputs.items():
            self._set_correction_state(key, field)
            field.valueChanged.connect(lambda _value, nutrient=key: self._mark_corrected(nutrient))
            field.lineEdit().textEdited.connect(lambda _text, nutrient=key: self._mark_corrected(nutrient))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setDefault(True)
        save_button.setObjectName("primaryButton")
        self.name_input.setFocus()

    def _build_banner(self, banner: tuple[str, str] | None, image_path: str | None, layout: QVBoxLayout) -> None:
        level, text = banner if banner else ("info", "")
        if level not in BANNER_LEVELS:
            raise ValueError(f"Unknown banner level: {level}")
        frame = QFrame()
        frame.setObjectName("dialogBanner")
        frame.setProperty("level", level)
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(12)
        if image_path:
            pixmap = QPixmap(image_path)
            photo = QLabel()
            photo.setObjectName("foodPhotoPreview")
            photo.setAccessibleName("Photo you imported")
            photo.setFixedSize(*_THUMBNAIL_SIZE)
            photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if pixmap.isNull():
                photo.setText("Photo")
            else:
                photo.setPixmap(pixmap.scaled(
                    *_THUMBNAIL_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
                ))
            row.addWidget(photo, 0, Qt.AlignmentFlag.AlignTop)
            self.photo_label = photo
        if text:
            label = QLabel(text)
            label.setObjectName("dialogBannerText")
            label.setWordWrap(True)
            label.setMinimumWidth(280)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
            row.addWidget(label, 1)
            self.banner_label = label
        layout.addWidget(frame)
        self.banner_frame = frame

    @property
    def basis(self) -> str:
        return BASIS_COUNT if self.basis_per_item.isChecked() else BASIS_GRAMS

    def _update_basis_labels(self) -> None:
        unit = "item" if self.basis == BASIS_COUNT else "100 g"
        for key, label in NUTRIENT_LABELS:
            self._nutrient_row_labels[key].setText(f"{label} / {unit}")
            self.nutrient_inputs[key].setAccessibleName(f"{label} per {unit}")

    def _basis_toggled(self, *_args) -> None:
        self._update_basis_labels()
        self._mark_corrected("basis")

    def handle_enter(self, _focus: QWidget) -> bool:
        """Enter in any field saves the food (called by the app-wide Enter handling)."""
        self._validate_and_accept()
        return True

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
        widget = self._correction_widget(name)
        widget.setStyleSheet("")
        widget.setAccessibleDescription("")
        widget.setToolTip("")
        if not self._correction_fields:
            self.error_label.clear()
        else:
            labels = ", ".join(self._field_label(field) for field in sorted(self._correction_fields))
            self.error_label.setText(f"Still needs correction: {labels}.")

    def _correction_widget(self, name: str):
        if name == "food_name":
            return self.name_input
        if name == "basis":
            return self.basis_widget
        return self.nutrient_inputs[name]

    @staticmethod
    def _field_label(name: str) -> str:
        labels = {"food_name": "food name"}
        return labels.get(name, name.replace("_", " "))

    def food(self) -> Food:
        values = {name: Decimal(str(field.value())) for name, field in self.nutrient_inputs.items()}
        return Food(self._food_id, self.name_input.text().strip(), Nutrients(**values), True, self.basis)
