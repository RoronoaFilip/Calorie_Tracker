# Daily Plate improvements: spec and plan

## Context

The repository uses a layered PySide6 application with SQLite persistence. The `Nutrients` domain value and JSON persistence already include fiber, and `FoodDialog` already edits it. The diary summary and entry rows do not display fiber. The food catalogue importer currently requires fixed headers at row 5 and all mapped nutrient columns; the diary importer scans for fixed `food_name` and `grams_eaten (all meals)` headers. Both import buttons open the file picker directly. The existing food edit form is `FoodDialog`; diary imports use a review table and require a unique active catalogue match.

The tracked `docs/implementation-plan.md` is absent from the worktree (it is already deleted locally), so this feature plan is recorded separately under `docs/superpowers/plans/` without restoring or replacing that file.

## Specification

- Add fiber to daily macro totals and diary entry details. Keep the existing food editor and stored nutrient model as the source of truth.
- Improve typography and sizing for daily values; remove the blue outlines around meal rows/cards.
- Show each meal's calories at the top right of its meal section.
- Make both CSV import entry points show a valid CSV schema example before file selection/import.
- Match CSV fields by normalized header names, independent of column order. Support a compact documented alias set for food name and core nutrient fields; for diary imports, also recognize amount and meal/time fields.
- Ignore unrecognized columns. Food-library imports do not classify or consume meal/time columns.
- For invalid/incomplete food-catalogue rows, prefill `FoodDialog` with recognized values and highlight fields that need correction. Save a corrected row as a catalogue food. Keep invalid diary rows visible in the review table; they require a valid amount, meal, and unique active catalogue match before import.

## Plan

1. Add fiber to diary summary and per-entry nutrient display; tune typography, row treatment, and meal calorie heading to match the supplied screenshot.
2. Add shared normalized header matching with explicit aliases; retain context-specific import fields and ignore unknown columns.
3. Add a schema/example preview before each import file picker. Route invalid food rows through `FoodDialog` prefilled with mapped values and field-level correction cues; keep diary review validation and catalogue matching intact.
4. Review the changes and run the focused tests followed by the project suite.

## Open implementation details

- Preserve the existing nutrient JSON and SQLite schema; fiber is already persisted.
- Keep food imports limited to explicit core nutrient aliases and known additional nutrient fields. Meal/time columns are ignored in catalogue context.
- Food name, calories, protein, fat, and carbohydrates are required to save a catalogue import row; fiber and other supported nutrients may be blank and default to zero. Missing/invalid required values open `FoodDialog` for correction.
- Header aliases remain explicit: food name (`food_name`, `food name`, `name`, `product`); calories (`calories`, `kcal`, `calories / 100g`); protein (`protein`, `protein / 100g`); fat (`fat`, `fat / 100g`); carbohydrates (`carbs`, `carbohydrates`, `carbohydrates / 100g`); fiber (`fiber`, `dietary fiber`, `fiber / 100g`). Preserve known optional `saturated_fat`, `sugars`, `omega-3`, and `omega-6` per-100g columns. Never treat `_total` columns as per-100g values. Diary imports additionally recognize amount (`grams_eaten (all meals)`, `amount`, `amount_g`, `grams`, `quantity`) and meal/time (`meal`, `time`, `meal_time`).
- Diary imports continue to append entries only; require an amount, a valid meal (or existing unassigned-meal workflow), and a unique active catalogue match. No importer creates or edits catalogue foods implicitly.
- Use existing edit UI and error-state patterns rather than creating a parallel form.
