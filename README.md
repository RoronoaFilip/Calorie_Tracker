# Calorie Tracker

A local desktop calorie and macro tracker. Food records and diary entries stay in a SQLite database on this computer.

## Set up the project

From the project directory, create and activate the virtual environment in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

The project dependencies are declared in `pyproject.toml` and installed into `.venv`.

## Run the app

```powershell
python app.py
```

The first launch creates `data\calorie_tracker.sqlite3` and seeds the basic foods from `food_macros_seed.csv`. Only mapped per-100 g fields are imported; both ice cream rows are excluded, recipes are not seeded, and existing catalogue entries are never overwritten. **Foods → CSV Import** is available for reviewing a separate catalogue import.

## Import diary entries for a day

Open **Diary**, choose any date with the date picker or **Calendar**, then select **Import CSV** — or simply **drag a `.csv` file onto the Diary page**. The importer validates the full file and shows how it read your columns, every row with a colour-coded status, and "did you mean" hints for unknown foods. Nothing is saved until you choose Import. Foods are matched by name against active basic foods in the catalogue (ignoring capitalization and extra spaces); imported entries are appended to the selected day, and existing entries are kept.

The CSV needs a food column and an amount column; the header can be on the first row or follow a short report preamble, and the columns can be in any order:

```csv
food_name,grams_eaten,meal
Oats,45.5,Breakfast
Banana,120,Snacks
```

Accepted names include `food_name` / `food` / `name` / `product`, and `grams_eaten` / `grams eaten` / `grams` / `amount` / `quantity` (the older `grams_eaten (all meals)` also works). Comma, semicolon, tab or pipe separators, decimal commas (`45,5`) and units (`45 g`) are understood.

The `meal` column is optional. In the review table, every row has a **Choose meal / Change meal…** button (or double-click the row) that you can use as often as you like: pick one meal, or **Split between meals…** to share an amount, e.g. 500 g of potatoes as 200 g Lunch + 300 g Dinner. **Show only rows that need attention** hides rows that are ready. Existing diary entries have a **Split** button too.

## Import foods from CSV

**Foods → CSV Import** (or drag a `.csv` onto the Foods page) opens the same kind of review: how columns were detected (typo-tolerant, marked "approximate" when guessed), every row coloured by status, and then a correction form for rows with bad values. Existing foods are never overwritten.

## Handy details

- **Ctrl+W** closes any pop-up window (never the main window).
- The **Calendar** shows a green tick on past days with entries and a red cross on past days without any, starting from your first logged day.
- **Settings → Your data** shows where your data lives, opens that folder, and exports the whole diary to CSV.

## Build a single .exe

See [`exe/BUILD_EXE.md`](exe/BUILD_EXE.md) (run `exe\build_exe.ps1` on Windows).

## Run the checks

The tests use Python's built-in `unittest` runner. On Windows, set Qt to its offscreen platform so the UI checks can run without opening windows:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -v
```

Tests use temporary databases and do not modify the app's `data` folder.
