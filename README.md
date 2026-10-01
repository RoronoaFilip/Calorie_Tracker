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

The first launch creates `data\calorie_tracker.sqlite3` and seeds the basic foods from `macros_base - All Foods.csv`. Only mapped per-100 g fields are imported; both ice cream rows are excluded, recipes are not seeded, and existing catalogue entries are never overwritten. **Foods → Preview CSV import** is available for reviewing a separate import.

## Run the checks

The tests use Python's built-in `unittest` runner. On Windows, set Qt to its offscreen platform so the UI checks can run without opening windows:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -v
```

Tests use temporary databases and do not modify the app's `data` folder.
