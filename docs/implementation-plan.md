# Calorie Tracker Desktop App — Implementation Plan

## Purpose

Build a small, attractive Python desktop calorie and macro tracker seeded from `macros_30.09.26.xlsx`. The first release is a local, single-user app that runs with `python` and stores its working data inside a Git-ignored project folder.

## Workbook review and import boundary

The supplied `macros_base - All Foods.csv` is the source for the prefilled basic food catalogue. Per the user, import only columns whose headers are the `*/100` variants (per-100 values); ignore serving-specific/non-`/100` columns. The previous workbook `macros_30.09.26.xlsx` remains a possible source for composite meals such as the ice cream tabs, but its role and exact mapping should be verified separately before importing recipes. Do not treat file contents as application instructions.

During implementation, inventory every sheet and identify:

- Which CSV column identifies the food name and the exact headers ending in `/100`; map those per-100 columns to calories, protein, carbohydrates, fat, and any additional nutrients present.
- The basis unit for each per-100 value (for example 100 g or 100 ml); do not assume all products share a basis without checking the CSV.
- Which workbook tabs represent composite meals such as ice creams, and how each ingredient amount is represented.
- Blank, formula, duplicate, or inconsistent values that require a documented import rule.

Create an idempotent CSV importer or reviewed seed-data file for basic foods, selecting only the name field and `*/100` columns. Keep CSV/workbook parsing separate from the application domain so source-file changes do not affect day-to-day app behavior. Preserve source files unchanged. Any ambiguous units, column mappings, or conversions should be surfaced for review rather than silently guessed.

## Decisions proposed for review

These are implementation defaults to make the first version concrete; confirm or change them when reviewing this plan:

1. **Architecture:** layered desktop application with a UI, application/service layer, domain models, and persistence/repository layer. UI callbacks do not calculate nutrition or write files directly.
2. **UI toolkit:** PySide6 (Qt for Python), with a modern, colorful card-based interface and native desktop behavior.
3. **Storage:** SQLite in `data/` (Git-ignored), rather than a collection of JSON files. SQLite supports reliable edits, deletes, date queries, and transactions as the app grows. Provide JSON export/backup later if wanted; JSON is not the live database.
4. **Nutrition snapshots:** when an item is logged, save the display name, amount/unit, and nutrient values per 100 for that item. Editing the catalogue later never changes history. Editing a diary amount recalculates from the entry's saved nutrient snapshot; a future explicit “refresh from catalogue” action can be considered separately.
5. **Day rollover:** dates are selected explicitly. On launch, open today by default; past dates remain unchanged and are browsable. No background midnight job is needed. The first write to a new date creates that day automatically. Prior days are already persisted, so rollover does not require a separate save action.
6. **Delete behavior:** deleting a logged entry or catalogue food requires a confirmation dialog. If a food is referenced by history or a recipe, archive/deactivate it instead of breaking those records; offer permanent deletion only when safe.
7. **Units:** quantities use a unit defined per food/recipe (for example g, ml, piece, or serving). Workbook units must be mapped before enforcing conversions; avoid implying grams and millilitres are interchangeable.

## User-visible behavior

### Main window and navigation

Use a persistent left navigation rail with icon buttons that switch the main application view. Keep the current selection visibly highlighted and pair each icon with a text label (compact sidebar, not icon-only navigation):

- **Diary:** selected date, daily macro totals/progress, and Breakfast, Lunch, Dinner, and Snacks sections.
- **Calendar:** month calendar with indicators for dates containing diary entries; choosing a past date opens its diary, with the selected date clearly shown.
- **Foods:** searchable catalogue and a single create/edit workspace for both basic foods and composite meals.
- **Settings:** lightweight local preferences such as optional macro targets, if included in the first release.

Show a short tooltip on hover for every navigation icon and any icon-only action, with a slight delay to avoid flicker. Tooltips must also appear when the control receives keyboard focus, and must not replace accessible names. Keep text labels beside navigation icons so the available views remain discoverable without hover.

### Daily diary

- Add a catalogue food or recipe to any of the four meal sections, with a quantity/serving selector.
- Adding is saved automatically; there is no separate save button for a new diary entry.
- Show per-entry macros, per-meal subtotals, and day totals, recalculated immediately.
- Existing entries can be edited and explicitly saved or cancelled. New entries are committed on add.
- Deleting an entry always asks for confirmation.
- A day can contain any number of entries in each meal section, including none.
- Import CSV is available from the selected day's diary. It validates the full file, matches food names to active basic catalogue foods, and appends the accepted rows in one transaction without replacing existing entries.
- Diary CSV requires `food_name` and `grams_eaten (all meals)` headers, with an optional `meal` header. When a valid row has no meal, let the user choose Breakfast, Lunch, Dinner, or Snacks for that row, or assign all unassigned rows to Snacks.
- Show row-level validation errors and the accepted header/example format before importing. A malformed file must not partially write diary entries.

### Food and recipe management

One management window supports both basic foods and composite recipes:

- Create a basic food from name, base amount/unit, and its macro values.
- Create a recipe (including ice cream) by adding one or more existing foods/recipes as ingredients and entering each quantity.
- Calculate recipe nutrition from ingredient quantities, and show the resulting recipe total and serving definition before saving.
- Optionally allow a user-entered macro override only if a later requirement calls for it; default is calculated nutrition.
- Edit existing catalogue items and recipes; changes affect future diary additions, not historical snapshots.
- Delete/archive actions require warning/confirmation and protect referenced data.
- Validate required names, positive amounts, and non-negative nutrition values; display helpful errors inline.

## Proposed clean project structure

```text
D:/Calorie_Tracker/
  app.py                         # thin application entry point
  pyproject.toml                 # package metadata and dependencies
  README.md                      # setup and python run instructions
  .gitignore                     # excludes data/, caches, local environment
  docs/
    implementation-plan.md
    architecture.md              # add during implementation
  src/calorie_tracker/
    __init__.py
    bootstrap.py                 # dependency wiring and startup
    domain/
      models.py                  # Food, Recipe, Ingredient, DiaryDay, DiaryEntry
      nutrition.py               # macro calculations and unit rules
      errors.py
    application/
      services/                  # diary, catalogue, and recipe use cases
      dto.py                     # UI-facing input/output shapes
    infrastructure/
      database.py                # SQLite connection, schema, migrations
      repositories/              # persistence implementations
      workbook_importer.py       # isolated workbook-to-seed import
    presentation/
      main_window.py
      views/                     # diary, calendar/history, catalogue
      dialogs/                   # add/edit entry and food/recipe forms
      widgets/                   # reusable macro cards, meal panels
  tests/
    unit/
    integration/
```

The planned package layout is a target, not a requirement to create empty modules. Keep each module cohesive and introduce files as features are implemented.

## Data model (initial)

- **Food:** stable ID, name, base quantity, unit, calories, protein, carbohydrates, fat, active/archive state, timestamps.
- **Recipe:** stable ID, name, final yield and yield unit, active/archive state, timestamps.
- **RecipeIngredient:** recipe ID, referenced basic food ID, quantity, unit. V1 recipes contain basic foods only, avoiding nested-recipe cycles and keeping calculation rules easy to inspect.
- **DiaryDay:** ISO calendar date and timestamps; unique per date.
- **DiaryEntry:** stable ID, date, meal category, referenced catalogue item where available, display-name/nutrition snapshot, quantity, computed macros, timestamps.

Use decimal-safe numeric storage for quantities and macro values where practical; define and document rounding for display. Keep recipe components relational, while diary snapshots retain the values actually logged.

## Persistence and project hygiene

- Store the live database at `data/calorie_tracker.sqlite3` (create `data/` on first run).
- Add `data/` and transient SQLite journal/WAL files to `.gitignore`; never place user diary data in source-controlled seed files.
- Ship/import the initial catalogue through a reproducible seed/import step. Make it idempotent so rerunning it does not duplicate foods.
- Use SQLite transactions for diary updates and recipe changes; schema versioning/migrations are required from the first persisted release.
- Plan a user-triggered backup/export path before relying on the app for long-term tracking. A simple JSON export can be added as a portable backup format without using JSON as the live store.

## Implementation phases

1. **Source mapping:** inspect CSV headers and rows; map food names and `*/100` fields to normalized nutrition fields and verify basis units. Separately inspect workbook tabs/formulas for composite meals and map ingredient amounts. Resolve ambiguous rows and document normalization.
2. **Project foundation:** create the package, dependency metadata, `python` entry point, configuration, logging, SQLite schema, migrations, repositories, and `.gitignore`.
3. **Domain and services:** implement nutrition calculations, recipe composition/cycle validation, diary CRUD, auto-persist behavior, and historical snapshots.
4. **Catalogue UI:** implement the combined food/recipe management workspace, ingredient picker, validation, edit/save, and guarded delete/archive flows.
5. **Diary UI:** implement meal sections, food/recipe picker, quantity entry, automatic add, totals, edit/save/cancel, and confirmed delete.
6. **Calendar/history UI:** implement month navigation, populated-day markers, date selection, and past-day diary display/editing.
7. **Polish and release:** apply consistent visual styling, accessible focus/keyboard behavior, empty/error states, README setup/run guidance, and verify the app runs with `python` from the project directory.

## Acceptance criteria

- Running `python` with the documented project command opens the desktop application.
- The imported catalogue includes verified workbook foods and composite meals, including the ice cream meals, with correct units and macro calculations.
- A user can create a basic food and a composite recipe in the same management area.
- A user can add foods/recipes to Breakfast, Lunch, Dinner, or Snacks and sees entry, meal, and day totals update immediately.
- Diary additions persist automatically; editing requires save/cancel; deleting requires confirmation.
- The app can select today or any past date from a calendar, and saved history remains available after closing and reopening.
- User data is stored under the project `data/` folder and excluded from Git.
- The UI layer is separated from business rules and persistence; the implementation follows the agreed single architecture.

## Questions resolved for the first implementation

The request leaves the exact UI toolkit, architecture style, live storage format, and handling of historical values open. This plan proposes PySide6, a layered architecture, SQLite with JSON export as a future backup option, and immutable nutrition snapshots for logged history. The prefill source is now the CSV, limited to `*/100` fields as requested. Its exact headers and unit basis, plus any recipe mapping from the earlier workbook, still need inspection before importer implementation. No remaining question blocks the plan; these are implementation discovery items.

## Additional implementation guidance

### Define nutrition and quantity semantics before building screens

The importer and diary must agree on what a quantity means. Before writing the importer, inspect the CSV headers and establish a field map with source header, normalized nutrient, basis, and unit. Preserve the original source header in the import report. Only the user-approved `*/100` columns supply prefilled nutrition values; never accidentally pick a serving or portion column by fuzzy matching.

For a verified per-100 g food, store its nutrient values per 100 g and let diary quantity be entered in grams. Compute each entry as `per_100_value × quantity_g / 100`. If a food is per 100 ml, retain that basis and accept ml; never convert g to ml without a density value. Recipe ingredients must use compatible, explicit units. Do not convert piece, tablespoon, or cup to mass unless a food-specific conversion is supplied. The first version can keep the quantity workflow simple by supporting g and ml and documenting that limitation.

Recipe final yield is automatically calculated as the sum of ingredient amounts. The app calculates nutrition per 100 g from the summed ingredient nutrients and that total yield; the recipe editor displays the calculated yield as read-only.

Keep full precision in storage/calculation; round only in display (for example calories to whole numbers and macros to one decimal place). Document this consistently so adding rounded rows does not produce totals that disagree with the displayed day total.

### Make imports safe and explainable

- Parse CSV with a standard CSV reader, not string splitting; support quoted commas, Unicode names, and the detected file encoding/decimal convention.
- Validate the header map before importing and produce a human-readable import summary: rows read, imported, skipped, duplicate names, blank names, malformed numbers, and ignored non-`/100` fields.
- Do not silently replace an existing live catalogue on app startup. Import once into an initial database, with a deliberate re-import/merge action if needed.
- Make repeated imports idempotent using a stable source key where available; otherwise show duplicate candidates for review instead of destructive name-based merging.
- Preserve a source reference (file name and source row or stable key) on seeded foods so a user can trace and refresh an entry later.
- Keep user-created foods distinguishable from imported foods. If the CSV changes later, show a preview of additions/changes before applying updates, and never overwrite user edits without a clear choice.

### Add safeguards for recipes and catalogue edits

- Use stable IDs and foreign keys; names are labels and may be duplicated or changed.
- In v1, recipes contain basic foods only. This keeps recipe math transparent and avoids nested-recipe cycle handling; nested recipes can be added later if real usage needs them.
- Validate positive ingredient amounts and yields, non-negative nutrition values, a non-empty name, and at least one ingredient for a recipe.
- Show the nutrition calculation and serving basis before recipe save. Warn when ingredient units do not match or an ingredient is archived/unavailable.
- Editing a food updates future recipe calculations and future diary additions, but never rewrites saved diary snapshots. Provide a deliberate recipe recalculation action if ingredients changed.
- Archive catalogue items that are already used by a recipe or diary entry. Archiving prevents new selection but keeps history and recipe integrity. Do not offer permanent removal when referenced.

### Clarify save, edit, and date behavior

- Auto-save each newly added diary entry as one transaction and show brief saved/error feedback. If persistence fails, keep the user's unsaved form visible and explain how to retry; never imply an entry was saved when it was not.
- Existing-entry editing uses Save and Cancel. Save atomically replaces that entry's quantity and nutrition snapshot; Cancel discards the draft.
- Confirm deletion with the item name and meal/date context. Offer Undo after a successful delete for a short period, in addition to the required confirmation, if feasible.
- Use local calendar dates as diary keys; do not shift a diary date through UTC timezone conversion. The selected date must remain visible when viewing history.
- Opening the app selects the computer's current local date but does not create a blank persisted day just by opening it. Create a day record with the first entry, and preserve it after the last entry is removed only if the user has intentionally saved a note or other day-level data.
- Past dates are editable in v1 (as proposed) and clearly labeled. Consider a future optional read-only/lock mode only if requested.

### Small improvements included in the first release

Include these directly because they reduce daily friction without requiring external services or large new subsystems:

1. **Fast searchable food picker:** search by name as the user types, with a recent-items section above results. Support keyboard focus and Enter to add the selected food.
2. **Repeat last entry:** a one-click action on a diary row to add the same food and quantity again to that meal, with immediate automatic save and a short undo toast.
3. **Optional daily macro targets:** users can set or leave blank calorie, protein, carbohydrate, and fat targets. Show simple progress bars on the diary; targets are personal settings, not recommendations.
4. **Helpful empty states and save feedback:** guide first entry in each meal; show a brief saved confirmation after automatic add and actionable messages on storage failure.
5. **Undo a diary deletion:** keep the required confirmation dialog, then offer a brief Undo action after deletion. Catalogue items used in history are archived rather than permanently removed.
6. **Tooltips and keyboard access:** icon tooltips on hover and focus, persistent text labels in the left rail, logical keyboard tab order, and keyboard activation of common controls.

Keep backup/export in the first release if it fits after the core flows; it is useful but not a daily interaction. Defer barcode scanning, online food databases, cloud sync, accounts, wearable integrations, weight tracking, and multi-user support. Avoid building charts, advanced dashboards, or extra nutrient analysis until the basic logging workflow is reliable.

### Reliability, privacy, and maintainability

- Treat all data as local and private. No network calls or analytics are needed for v1.
- Store database transactions safely; enable SQLite foreign keys and use atomic writes/transactions. Handle locked/corrupt/unwritable database errors with a useful message and recovery guidance.
- Add a schema version and migration path. Keep a tested backup before destructive migrations.
- Store preferences (theme, targets, preferred quantity unit, last selected date) separately from source catalogue content, but in the same local database for simplicity.
- Add structured application logging to a local logs folder with rotation and no unnecessary nutrition/personal data in log messages. Ignore database, logs, exports, caches, and virtual environments in Git.
- Keep dependencies minimal and pinned/declared in `pyproject.toml`; document the supported Python version and install/run steps. The launch command should be explicit, e.g. `python app.py` from the project root, and work without requiring a global package install beyond documented dependencies.
- Include a sample sanitized backup/import fixture for development; never commit the user's actual diary database.

### UI and accessibility details

- Design the primary diary for fast logging: date at top, macro summary visible without scrolling, meal sections in a stable order, add action close to each meal, and the last-used meal/quantity available as a convenience without silently changing the selected meal.
- Ensure the main window resizes, works at common laptop resolutions, and keeps buttons/forms usable under display scaling.
- Use text labels and icons together; color must not be the only way to distinguish macros or warnings. Provide visible keyboard focus, logical tab order, accessible control names, and keyboard shortcuts for common actions where appropriate.
- Make destructive actions visually distinct and place confirmation context near the action. Keep validation messages specific to the field that needs correction.
- Provide a consistent light theme first; a dark theme can be added after the layout and contrast are verified.

## Revised delivery sequence and completion gates

1. **Inspect and map the sources.** Record actual CSV headers, examples, encoding, decimal format, per-100 basis, duplicate/blank rows, and workbook recipe structure. Deliver a concise source data dictionary and a list of unresolved mappings. Do not invent source fields.
2. **Confirm domain rules.** Finalize supported units, recipe yield rules, precision/display rounding, whether nested recipes are in v1, historical snapshot fields, and target preferences. Encode these rules in domain-level documentation before UI implementation.
3. **Foundation and persistence.** Add package structure, launch command, SQLite schema/migrations, repositories, preferences, logging, error handling, and Git ignores. Verify a clean first launch creates the local data folder and database.
4. **Importer and catalogue.** Implement previewable, idempotent import restricted to the approved `*/100` columns. Add search, favorites/recent items, food CRUD, recipe composition, validation, and archive safeguards.
5. **Diary workflow.** Implement meal/day selection, automatic add, totals, edit/save/cancel, confirmed delete, and undo. Persist snapshots and handle failed writes visibly.
6. **Calendar and history.** Add calendar navigation, populated-date indicators, selection of any past day, and copy-previous-day/meal convenience if it does not delay the core diary workflow.
7. **Backup, polish, and release.** Add validated backup/restore, daily target settings, responsive/accessibility pass, user documentation, and a clean-machine run-through.

At each gate, keep the app runnable. Prefer small increments: import and display foods before adding recipe editing; save one diary entry before building the whole calendar; establish storage behavior before polishing charts.

## Additional acceptance criteria

- Import uses only the explicitly mapped `*/100` fields, reports skipped/duplicate/malformed rows, and never silently overwrites user data.
- Per-100 nutrition scales correctly by entered quantity; incompatible units are rejected or explicitly supported with a conversion, never guessed.
- Recipe nutrition reflects ingredient quantities and final yield according to the documented rule, and cycles cannot be saved if nested recipes are supported.
- Full precision is retained in calculations, with consistent rounding in entry, meal, and day views.
- Editing/deleting/importing failures leave data consistent and provide a visible recovery path; backup restore cannot proceed without validation and a safety copy.
- Logging, favorites, targets, and backup/restore remain local; no network account is required.
- A fresh checkout can be set up and launched using the documented Python command, and no user data is tracked by Git.

## Visual design specification

Design the application as a calm, bright daily dashboard rather than a spreadsheet. Use a warm off-white/light gray main canvas, white content cards, dark readable text, rounded corners used consistently, and a restrained accent palette. Assign stable macro colors (for example calories coral, protein blue, carbohydrates amber, fat violet) and use the same colors in summary cards and progress bars. Use color with labels and values so meaning never depends on color alone. Use one consistent icon set and a clean sans-serif typeface; avoid decorative gradients, crowded charts, and excessive shadows.

### Window frame and left navigation

- Desktop window opens at a practical laptop size and resizes cleanly. The left rail remains fixed while the main content scrolls.
- Place the app name/mark at the top of the rail, followed by vertically stacked icon-and-label buttons for **Diary**, **Calendar**, **Foods**, and **Settings**. Keep the labels visible at all times.
- Use a tinted rounded background and accent marker for the active view; inactive items have a quiet neutral style and clear hover/focus state.
- Every icon button has a short tooltip on hover and keyboard focus (for example, “Calendar — browse past days”). Tooltips supplement the visible label and accessible name.
- Place a small version/about or help affordance at the bottom only if needed; keep the core navigation uncluttered.

### Diary view

- Header row: selected date in a prominent format, previous/next-day arrows, a **Today** shortcut, and a calendar affordance.
- Below the header, show four compact macro summary cards in one row when width allows, with consumed amount, optional target, and a thin progress bar. On narrower windows, wrap cards instead of clipping.
- Meal sections appear in stable order: Breakfast, Lunch, Dinner, Snacks. Each section is a white card with a meal icon/title, subtotal, food rows, and a visible **Add food** button. Empty sections show one-line guidance and the add action.
- A food row shows food/recipe name, quantity with unit, calories and P/C/F values, plus compact Edit, Repeat, and Delete actions. Keep row actions discoverable with hover/focus tooltips and do not hide essential actions exclusively on hover.
- The add-food flow uses an inline popover/dialog anchored to the meal. It contains a focused search box, recent foods, matching results, and an explicit quantity/unit field before adding. Enter selects/adds when the interaction is unambiguous.

### Calendar, catalogue, and settings

- Calendar view uses a month grid with previous/next controls, a clear Today shortcut, and subtle dots or small totals for dates with entries. Selecting a date opens the diary view for that date. Make today, the selected date, and dates with data visually distinct.
- Foods view has a search field, filter chips or simple category filter if useful, and a readable list/table with name, basis unit, and per-100 nutrition. Put **Add food** and **Create recipe** in a prominent top action area. Food and recipe create/edit use one shared management window with a clear type selector, not separate disconnected tools.
- Recipe editor presents an ingredient list with amount/unit, an **Add ingredient** searchable picker, calculated read-only yield, and calculated nutrition per 100 g. Keep calculations visible before save.
- Settings stay intentionally small: optional daily macro targets, preferred display precision/unit where applicable, and a local backup/export action if included. Avoid burying daily logging controls here.
- Date pickers and other arrow controls use visible, accessible indicators. Calendar month/year popup menus use a light palette with readable text.
- Calendar history has an outlined month grid with larger date numbers and a darker hovered day; the today marker has no hover tooltip. Clickable controls use a pointing-hand cursor.

## Fast interaction and performance rules

Treat responsiveness as a design requirement. For the expected personal-scale catalogue and diary, a straightforward local SQLite database is sufficient; optimize the query and widget behavior before considering caches or concurrency.

- Use Qt model/view widgets for searchable catalogue/history lists rather than creating a large tree of one widget per database row.
- Add database indexes for diary date, diary entry date/meal, normalized food name, and recipe ingredient references where query patterns justify them. Use parameterized queries and fetch only the selected date or visible result page.
- Search locally with a short debounce (about 150–250 ms) and cap/render visible results; do not query/rebuild the full UI on every keystroke.
- Keep common reads local and small. Recalculate affected entry/meal/day totals incrementally after an add/edit/delete; do not reload every historical day.
- Keep startup work bounded: open the database, run only required migrations, load today's diary and a small recent-food list. Do not parse/import the CSV on each launch.
- Avoid blocking the UI thread for routine SQLite calls or recipe calculations. If a future import/export becomes noticeably long, run that operation off the UI thread and report progress; do not add thread machinery preemptively.
- Use stable Qt model IDs and update affected rows only. Do not reconstruct the full window when switching between navigation views if preserving state is simple.
- Keep performance goals measurable: navigation feels immediate, search results appear without a visible pause, and common add/edit/delete actions update totals promptly on a normal laptop with a catalogue of several thousand foods.

## Project instructions and hygiene files

Keep durable project-specific agent guidance in the hidden project folder `.codex/`. Add a root `AGENTS.md` as the always-discoverable index, because tools commonly search for `AGENTS.md` at the project root; it points contributors to `.codex/PROJECT_GUIDELINES.md`. The hidden folder is for concise project rules, not application data. Keep user data under `data/` and Git-ignored.

The hidden guidelines should require contributors to:

- Preserve the agreed layered architecture: presentation depends on application services, application uses domain rules and repository interfaces, infrastructure implements persistence/import; domain code does not import Qt or SQLite.
- Keep UI code focused on rendering and user interaction; put nutrition calculations and validation in domain/application code.
- Prefer small cohesive modules, typed public interfaces, descriptive names, explicit error handling, and dependency injection at bootstrap. Avoid giant modules, hidden globals, circular imports, and premature abstractions.
- Keep source imports and side effects at the application boundary; importing a module must not open a window, mutate the database, or parse source files.
- Keep SQLite access behind repositories, use transactions for multi-row changes, enforce foreign keys, and version schema changes with migrations.
- Never commit the live database, backups, logs, virtual environments, caches, generated files, or personal CSV contents. Track only sanitized fixtures and source code/configuration.
- Update the plan/README when a product or architecture decision changes. Do not introduce a new dependency for a feature available in the standard library or chosen UI toolkit without a concrete need.
- Add focused unit and integration checks for behavior as implementation proceeds; keep UI tests limited to high-value workflows. Do not claim validation that was not run.
- Keep `python app.py` as the documented launch path and do not make network access necessary for normal use.

## Revised first-release scope

**Must ship:** left icon-and-label navigation with hover/focus tooltips; diary by date and meal; food and recipe catalogue; CSV import restricted to mapped `*/100` columns; automatic diary add; edit/save/cancel and confirmed delete; macro totals; calendar history; local SQLite persistence; search with recent foods; repeat-entry action; optional macro targets; Git ignores and project guidance.

**Include if it remains small after the above works:** undo toast, JSON/database backup and restore, favorites, compact meal/day copy. Keep these behind the core workflow in implementation order. Avoid letting bonus features delay accurate importing, data integrity, or routine logging.

## Decisions to carry into implementation

Use this short list as the implementation checklist when sections above are detailed:

- **App shape:** PySide6, one main window, left icon-and-label navigation, and four views: Diary, Calendar, Foods, Settings. Show concise tooltips on hover and keyboard focus.
- **Architecture:** practical layered structure with presentation, application services, domain rules, and SQLite/import infrastructure. Keep `app.py` as a small launcher; do not add a framework or abstraction layer beyond what these boundaries need.
- **Data:** SQLite is the live local store under Git-ignored `data/`. JSON is an optional export/backup format, not the primary database.
- **Food values:** import only explicitly mapped `*/100` CSV columns. Confirm the units/basis from the actual file before enabling conversions. Store full precision and round only for display.
- **Recipes:** in v1, compose from basic foods only; calculate final yield from ingredient grams and show calculated nutrition per 100 g before save.
- **History:** diary records retain a snapshot of nutrition at log time. Editing a logged amount uses its saved snapshot. Catalogue edits only affect future entries.
- **Fast logging:** searchable picker with recent items, one-click repeat, automatic add, and immediate totals. Add save confirmation; show failures without losing the form.
- **Safety:** edits have Save/Cancel, deletes have confirmation, referenced catalogue entries are archived, and backups never replace data without validation and a safety copy.
- **Scope discipline:** implement the core diary, catalogue/recipe editor, calendar, and persistence first. Add only the small convenience features listed as first-release items; keep integrations, accounts, and advanced analytics out of v1.

## Suggested repository hygiene

Keep `AGENTS.md` and `.codex/PROJECT_GUIDELINES.md` tracked in Git so their instructions travel with the project. The `.codex` directory is hidden in typical file browsers, but it must not be Git-ignored. Put only durable project guidance there; keep runtime databases, logs, caches, and exports under `data/` or their designated local folders and ignore those runtime paths. Keep sample fixtures sanitized and small.
