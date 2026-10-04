from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QLocale, Qt, QTimer
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.application.targets import DEFAULT_DRIFT, DRIFT_KEY, load_drift, normalize_drift
from calorie_tracker.bootstrap import ApplicationServices

AUTOSAVE_DELAY_MS = 400

DRIFT_EXPLANATION = (
    "Acceptable drift is the range of your target, in percent, that counts as on track. The percentage on "
    "your Diary is green inside the range and red outside it. For example 85% to 110% of a 2000 kcal target "
    "makes 1700 to 2200 kcal green. By default only 100% is green."
)


class SettingsView(QWidget):
    TARGETS = (
        ("calories", "Calories", "kcal"),
        ("protein", "Protein", "g"),
        ("carbohydrates", "Carbohydrates", "g"),
        ("fat", "Fat", "g"),
        ("fiber", "Fiber", "g"),
    )

    def __init__(self, services: ApplicationServices, notify):
        super().__init__()
        self.services = services
        self.notify = notify
        self.setObjectName("mainContent")
        # The whole page scrolls, so nothing is squeezed when the window is small.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("settingsScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("settingsContent")
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 34, 40, 36)
        layout.setSpacing(15)
        heading = QLabel("Settings")
        heading.setStyleSheet("font-size: 26px; font-weight: 650; color: #172538;")
        layout.addWidget(heading)
        description = QLabel(
            "Daily targets drive the progress bars and percentages on your Diary. "
            "Changes are saved as you type. Clear a field to leave that target not set."
        )
        description.setStyleSheet("color: #738094;")
        description.setWordWrap(True)
        layout.addWidget(description)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        for column, text in ((1, "Daily target"), (2, "Acceptable drift (% of target)")):
            title = QLabel(text)
            title.setStyleSheet("font-weight: 650; color: #344154;")
            grid.addWidget(title, 0, column, 1, 1 if column == 1 else 4)

        number_validator = QDoubleValidator(0.0, 1_000_000.0, 1, self)
        number_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        number_validator.setLocale(QLocale.c())  # a dot is the decimal separator
        self.target_inputs: dict[str, QLineEdit] = {}
        self.drift_low_inputs: dict[str, QLineEdit] = {}
        self.drift_high_inputs: dict[str, QLineEdit] = {}
        for row, (key, label, unit) in enumerate(self.TARGETS, start=1):
            grid.addWidget(QLabel(f"{label} ({unit})"), row, 0)
            target = QLineEdit()
            target.setObjectName(f"target{key.title()}")
            target.setAccessibleName(f"Daily {label.lower()} target")
            target.setPlaceholderText("Not set")
            target.setValidator(number_validator)
            target.setMinimumWidth(130)
            grid.addWidget(target, row, 1)
            low = self._drift_input(f"driftLow{key.title()}", f"Lower bound of the acceptable {label.lower()} drift")
            high = self._drift_input(f"driftHigh{key.title()}", f"Upper bound of the acceptable {label.lower()} drift")
            grid.addWidget(low, row, 2)
            grid.addWidget(QLabel("% to"), row, 3)
            grid.addWidget(high, row, 4)
            grid.addWidget(QLabel("%"), row, 5)
            self.target_inputs[key] = target
            self.drift_low_inputs[key] = low
            self.drift_high_inputs[key] = high
        card_layout.addLayout(grid)
        explanation = QLabel(DRIFT_EXPLANATION)
        explanation.setObjectName("driftExplanation")
        explanation.setWordWrap(True)
        explanation.setStyleSheet("color: #536175;")
        card_layout.addWidget(explanation)
        layout.addWidget(card)
        layout.addStretch(1)

        self._loading = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(AUTOSAVE_DELAY_MS)
        self._save_timer.timeout.connect(self.save_targets)
        self.reload_targets()
        for control in (*self.target_inputs.values(), *self.drift_low_inputs.values(), *self.drift_high_inputs.values()):
            control.textChanged.connect(self._schedule_save)

    @staticmethod
    def _drift_input(object_name: str, accessible_name: str) -> QLineEdit:
        control = QLineEdit()
        control.setObjectName(object_name)
        control.setAccessibleName(accessible_name)
        control.setPlaceholderText(str(DEFAULT_DRIFT[0]))
        control.setValidator(QIntValidator(0, 1000, control))
        control.setAlignment(Qt.AlignmentFlag.AlignRight)
        control.setFixedWidth(84)
        return control

    # ---- values ------------------------------------------------------------------------------------------

    @staticmethod
    def _number(text: str) -> float | None:
        """A positive number from the text, or None when the field is empty (not set) or not a positive number."""
        text = text.strip().replace(",", ".")
        if not text:
            return None
        try:
            value = Decimal(text)
        except InvalidOperation:
            return None
        return float(value) if value.is_finite() and value > 0 else None

    @staticmethod
    def _whole(text: str) -> int | None:
        text = text.strip()
        return int(text) if text.isdigit() else None

    def set_target(self, key: str, value: float) -> None:
        """Type a target into the field; zero or less clears it (not set)."""
        self.target_inputs[key].setText(f"{value:g}" if value and value > 0 else "")

    def _schedule_save(self, *_args) -> None:
        if not self._loading:
            self._save_timer.start()

    def save_targets(self) -> None:
        """Write the fields to the settings. This runs by itself shortly after every change."""
        self._save_timer.stop()
        targets: dict[str, float] = {}
        drifts: dict[str, list[int]] = {}
        for key, _label, _unit in self.TARGETS:
            value = self._number(self.target_inputs[key].text())
            if value is not None:
                targets[key] = value
            low, high = normalize_drift(
                self._whole(self.drift_low_inputs[key].text()), self._whole(self.drift_high_inputs[key].text())
            )
            if (low, high) != DEFAULT_DRIFT:
                drifts[key] = [low, high]
        self.services.settings.set_json("daily_targets", targets)
        self.services.settings.set_json(DRIFT_KEY, drifts)
        window = self.window()
        diary = getattr(window, "diary_view", None)
        if diary is not None and window is not self:
            diary.refresh()  # the percentages on the Diary follow the new targets

    def hideEvent(self, event) -> None:
        if self._save_timer.isActive():
            self.save_targets()  # leaving the page must not lose a change that was still waiting to be saved
        super().hideEvent(event)

    def reload_targets(self) -> None:
        current = self.services.settings.get_json("daily_targets") or {}
        self._loading = True
        try:
            for key, control in self.target_inputs.items():
                value = current.get(key)
                control.setText(f"{float(value):g}" if value else "")
                low, high = load_drift(self.services.settings, key)
                self.drift_low_inputs[key].setText("" if low == DEFAULT_DRIFT[0] else str(low))
                self.drift_high_inputs[key].setText("" if high == DEFAULT_DRIFT[1] else str(high))
        finally:
            self._loading = False
