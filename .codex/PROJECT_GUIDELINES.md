# Calorie Tracker project guidelines

These are durable instructions for contributors and coding agents working in this repository. The root `AGENTS.md` points here so these rules are easy to discover.

## Agreed architecture

Use a layered desktop architecture:

1. `presentation/`: PySide6 windows, views, dialogs, and Qt models. It renders state and forwards user actions; it does not own nutrition rules or SQL.
2. `application/`: use cases/services and UI-facing DTOs. It coordinates domain operations and repository interfaces.
3. `domain/`: entities, value objects, validation, units, and nutrition calculations. It must not import PySide6, SQLite, file paths, or infrastructure modules.
4. `infrastructure/`: SQLite schema/migrations/repository implementations and CSV/workbook import adapters.
5. `bootstrap.py`: construct dependencies and connect the layers. Keep `app.py` a thin launch entry point.

Dependencies point inward: presentation → application → domain; infrastructure implements interfaces consumed by application. Avoid circular imports and do not let lower layers import UI code.

## Code quality

- Prefer small, cohesive modules and functions with clear names and type hints on public interfaces.
- Put business logic in domain/application code, not widget callbacks or SQL statements scattered through the UI.
- Use explicit inputs and dependency injection at startup. Avoid global mutable state and premature abstractions.
- Keep error handling close to the boundary that can explain or recover from the error. Show useful user-facing messages; do not swallow persistence failures.
- Module imports must not launch the UI, connect to/create the database, or parse/import source data.
- Keep formatting and naming consistent with the repository's configured tooling. Add tooling only when it solves a concrete maintenance need.

## Data and persistence safety

- Use stable IDs, SQLite foreign keys, parameterized queries, and transactions for multi-record changes.
- Keep SQL behind repository implementations; use schema versioning and explicit migrations.
- Preserve diary nutrition snapshots. Catalogue edits must not rewrite previously logged entries.
- Do not guess unit conversions. Represent basis units explicitly and reject unsupported combinations.
- Never overwrite user data silently during source imports, migrations, or restore. Provide preview/confirmation and a recoverable backup where data may be replaced.
- Keep the live database, backups, logs, exports, local environment, caches, and generated artifacts out of Git. Never commit personal food/diary data; fixtures must be sanitized.

## UI and performance

- Keep the left navigation rail consistent across views, with visible icon labels, active state, keyboard focus, and concise tooltips on hover/focus.
- Keep UI callbacks short. Search should be debounced; lists should use Qt model/view and fetch only needed records.
- Load only the current day/recent foods at startup. Do not parse source CSVs on each launch.
- Update only affected rows and totals after a diary change. Avoid full-window rebuilds and premature caching/threading.
- All common actions must remain keyboard accessible; color alone must not communicate state.

## Git and change hygiene

- Keep commits/diffs focused; do not mix unrelated cleanup with feature changes.
- Never use destructive Git commands to discard user work. Inspect status/diffs before changing tracked files.
- Update README and `docs/implementation-plan.md` when run instructions or agreed product decisions change.
- Keep `python app.py` as the documented launch command unless the user approves a change.
- Do not add network dependencies or make network access necessary for normal operation.
- Add focused unit/integration tests for new domain and persistence behavior; add only a few high-value UI workflow tests. Report exactly what was run and its outcome.

## Product rules for v1

- The main window uses a persistent left navigation rail with visible icon labels for Diary, Calendar, Foods, and Settings. Supply concise tooltips on both hover and keyboard focus; never make hover the only way to identify an action.
- Keep first-release convenience features small: searchable food selection with recent items, repeat-entry, optional daily macro targets, helpful empty/save states, and confirmed delete with brief undo. Do not add online services or account features.
- Import only the explicitly mapped `*/100` columns from the food CSV. Confirm basis units from source data before implementing conversion behavior.
- Recipes use basic foods only in v1, require an explicit final yield and compatible units, and show calculated nutrition before save.
- Diary entries preserve the logged nutrition snapshot. Editing a diary amount uses its saved snapshot; later catalogue edits never silently rewrite history.
- Additions are automatically persisted. Existing-entry edits require explicit Save/Cancel. Deletes require confirmation.
- Keep `AGENTS.md` and `.codex/PROJECT_GUIDELINES.md` tracked. Do not ignore `.codex/`; use it for versioned project guidance, never runtime or personal data.
