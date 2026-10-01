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

Open **Diary**, choose any date with the date picker or **Calendar**, then select **Import CSV**. The importer validates the full file and shows matching foods, skipped rows, and errors before saving. It matches food names exactly against active basic foods in the catalogue; imported entries are appended to the selected day, and existing entries are kept.

The diary CSV requires these headers (the header can be on the first row or follow a short report preamble):

```csv
food_name,grams_eaten (all meals),meal
Oats,45.5,Breakfast
Banana,120,Snacks
```

The `meal` column is optional. If it is missing or blank, choose Breakfast, Lunch, Dinner, or Snacks for each valid row, or put all unassigned rows in Snacks. Amounts are in grams and must be greater than zero. Food names must match one active catalogue food exactly, ignoring capitalization. Invalid amounts, unknown or duplicate food names, and invalid meal values are shown in the review table and skipped. A file with invalid headers or malformed CSV syntax shows the required format and an example before any entries are saved.

## Run the checks

The tests use Python's built-in `unittest` runner. On Windows, set Qt to its offscreen platform so the UI checks can run without opening windows:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -v
```

Tests use temporary databases and do not modify the app's `data` folder.
