# Fiber and CSV import improvements implementation plan

## Goal

Implement `docs/SPEC_PLAN_for_new_features.md` for the existing PySide6 and SQLite app, using the supplied diary screenshot as the visual reference. Do not change the database schema: nutrient JSON already stores fiber. Preserve the current local deletion of `docs/implementation-plan.md`.

## Task 1: Complete the diary fiber and visual treatment

**Files:** `src/calorie_tracker/presentation/views/diary_view.py`, `tests/test_presentation.py`

1. Add a failing presentation test that creates an entry with fiber `2.5 g` per 100 g at `50 g`, refreshes the diary, and asserts the daily fiber card shows `1 g` under the existing whole-number macro display policy and the entry detail includes `Fiber 1.3 g` (entry details display one decimal).
2. Add a Fiber daily card and target lookup using the existing macro-card construction; add fiber to the per-entry details. Keep daily targets optional and use `fiber` as the preference key.
3. Add a presentation assertion that each meal heading subtotal reflects its meal calories, and that diary item rows have no blue selection/outline treatment. Retain the existing meal card palette and add-button workflow.
4. Adjust row typography and spacing to follow the screenshot: readable food name and nutrient line, subdued meal subtotal at the top right, and no blue row border. Keep controls keyboard accessible.

**Verification:** focused tests in `tests/test_presentation.py` pass; project test suite passes.

## Task 2: Normalize and map CSV headers

**Files:** new `src/calorie_tracker/infrastructure/csv_headers.py`, `src/calorie_tracker/infrastructure/importer.py`, `src/calorie_tracker/infrastructure/diary_csv_importer.py`, `tests/test_importer.py`, `tests/test_diary_csv_importer.py`

1. Add food importer tests showing normalized whitespace/case/punctuation and reordered columns map the name and calories, protein, fat, carbohydrates, and fiber aliases correctly; unknown columns are ignored, and `meal`/`time` are not classified as food fields.
2. Add diary importer tests showing the same name aliases, amount aliases, and meal/time aliases map in reordered columns; unknown columns are ignored; duplicate aliases for the same field produce a format error.
3. Define a shared `normalize_header(value: str) -> str` function and explicit alias mapping constants. Normalization case-folds and reduces separators/spacing to a consistent token form. Keep alias sets finite and documented in the module.
4. Update `CsvFoodImporter.preview(path: Path | str) -> ImportPreview` to find a header row in the first 50 rows, require name, calories, protein, fat, and carbohydrates, accept blank fiber as zero, map known additional nutrient headers where available, and ignore unknown columns including meal/time. Preserve source row numbers, duplicate checks, exclusions, and idempotent import behavior.
5. Update `CsvDiaryImporter.preview(path: Path | str) -> DiaryCsvPreview` to use the shared header matcher. Require name and amount; treat meal/time as optional, normalize supported meal labels, and preserve the current unique active-food matching and unassigned meal behavior.

**Interfaces:** the header module exports `normalize_header`, `FOOD_FIELD_ALIASES`, and `DIARY_FIELD_ALIASES`; importers continue exposing their current preview/report/result DTOs.

**Alias contract:** food names accept `food_name`, `food name`, `name`, or `product`; nutrients accept `calories`/`kcal`/`calories / 100g`, `protein`/`protein / 100g`, `fat`/`fat / 100g`, `carbs`/`carbohydrates`/`carbohydrates / 100g`, and `fiber`/`dietary fiber`/`fiber / 100g`. Preserve the source's optional `saturated_fat`, `sugars`, `omega-3`, and `omega-6` per-100g fields. Strip recognized per-100g suffixes as part of matching, but never map `*_total` columns as per-100g values. Diary imports additionally accept `grams_eaten (all meals)`, `amount`, `amount_g`, `grams`, or `quantity` for amount, and `meal`, `time`, or `meal_time` for meal assignment. Food imports do not recognize those context-only aliases.

**Verification:** focused importer tests pass; project test suite passes.

## Task 3: Add import example previews and catalogue row correction

**Files:** `src/calorie_tracker/presentation/views/foods_view.py`, `src/calorie_tracker/presentation/views/diary_view.py`, `src/calorie_tracker/presentation/dialogs/food_dialog.py`, new `src/calorie_tracker/presentation/dialogs/csv_import_help_dialog.py`, importer DTOs as needed, `tests/test_presentation.py`, `tests/test_importer.py`

1. Add a food-import parser test that retains recognized name/nutrient values for a row with a missing or invalid required value and identifies the fields needing correction; valid rows remain directly importable.
2. Extend the invalid food-row representation with source row, recognized values, and field errors. Do not discard mapped values when validation fails.
3. Extend `FoodDialog` to accept prefilled name/nutrients and a set of fields needing correction. Mark affected inputs with accessible error text and an error style; validate non-empty name and corrected required nutrients on Save. Existing create/edit behavior remains unchanged.
4. Add a reusable import-help dialog that displays the supported header schema and example row, with a Choose CSV action. Route both import entry points through it before opening the file picker; Cancel closes without opening the picker.
5. Update food import presentation to offer each invalid row for correction in `FoodDialog`. On accepted correction, save it through `services.foods.save`; on cancel, leave it unimported and continue with remaining rows. Do not overwrite an existing catalogue food on name conflict.
6. Keep invalid diary CSV rows in the review table, showing validation errors and allowing import only after they are valid. They are not sent to `FoodDialog` and do not create catalogue entries.
7. Add presentation tests for schema-before-picker behavior, prefilled correction values/field cues, saved corrected foods, and diary invalid-row blocking.

**Verification:** focused importer and presentation tests pass; project test suite passes.

## Review focus

- Duplicate aliases must not silently choose a column.
- Food import must never classify meal/time as a nutrient or overwrite a user food.
- Diary import must not create catalogue records or write invalid/unmatched rows.
- Existing historical diary snapshots remain unchanged; fiber is already included in their nutrient JSON.
- Preserve the user's existing deletion of `docs/implementation-plan.md` and leave unrelated working changes unstaged.
