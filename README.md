# Daily Plate

**A private calorie and macro tracker that lives entirely on your computer.**

Log what you eat, build your own food and recipe catalogue, and see how each day adds up against your targets. There are no accounts, no cloud and no ads. Your data is a single file on your own disk.

## What you can do

### Track your day
- Log foods and recipes into **Breakfast, Lunch, Dinner and Snacks**: by gram amount, or by **count** for foods you add "per item" (an egg, a slice of bread; halves and thirds are fine).
- **Quick add** several entries on several meals at once: fill in a table of food (type to search), amount and meal, then check it on the same review table as a CSV import.
- See calories and nutrients add up per meal and for the whole day.
- Set **daily targets** in Settings. Progress bars on the Diary page show how you're doing; leave a target unset and its bar is hidden.
- Find foods fast with search and a **Recently used** list.
- Made a mistake? **Undo delete** brings back the last entry you removed.
- Ate one food across several meals? **Split** an amount, for example 500 g of potatoes as 200 g at lunch and 300 g at dinner.

### Build your own catalogue
- Add foods with their nutrients **per 100 g** (default) or **per item**: calories, fat, saturated fat, carbohydrates, sugars, protein, fibre, omega-3 and omega-6.
- Create **recipes** from your foods (search the ingredient list by typing; amounts can be edited in place). The final yield and nutrition per 100 g are calculated from the ingredients for you.
- Archive foods you no longer use. Past diary days keep the values they were logged with, so history never changes behind your back.
- Starts with a ready-made set of basic foods.

### Bring your data in
- **One import for everything.** Every import button (Foods, Diary, Manage your data, or **Ctrl+O**) opens the same dialog. Choose or drop **as many files as you like**: CSV files, barcode photos, and **zip files** holding them. You can also drop files **anywhere in the app**, on any page. Each CSV is recognised by its header row (foods, diary entries or recipes; if it can't tell, it asks), and everything is imported one after another, foods first, each with its own review. Nothing is saved until you confirm. The **?** button beside every import button lists every supported CSV structure.
- **Import a day from CSV.** Column names are matched flexibly, and the separators `, ; tab |`, decimal commas (`45,5`) and units (`45 g`) are understood. A review table shows how every row was read. Rows go to the day shown on the Diary page, unless the file is named `diary-YYYY-MM-DD.csv`.
- **Best-guess food names.** A name that isn't in your foods gets ranked suggestions. Only spelling-level matches (capitals, accents, plural, word order, one small typo, such as `eggs` for `Egg`) are pre-selected, flagged "guessed", and you confirm them; anything that could change the nutrition (`skim milk` for `Milk`) is only suggested.
- **Raw input.** In the import dialog, *Raw input* lets you paste CSV text (starting with its header row). As you type, the text is highlighted to show what will be imported, which header columns are used, and where the problems are.
- **Import foods from CSV.** Same idea for your catalogue. Existing foods are never overwritten.
- **Companion phone app.** The separate `dailyplate-phone` web app (installable on a phone, no server) captures barcode photos, meals and new foods and bundles them into one zip you send to your computer, for example through Messenger. Drop that zip anywhere in this app. Its files are named `foods.csv`, `diary-YYYY-MM-DD.csv` and `photos/…`, and `tests/test_phone_export.py` proves they import.
- **Zip files.** Only CSV files and photos are used. Files at the top level plus the files of one folder are all taken; folders inside that folder are ignored; more than one folder is an error.
- **Add a food from a barcode photo.** Drop a photo of a product's barcode anywhere in the app (JPEG, PNG, WebP and other common formats). The barcode is read on your computer and the nutrients are looked up on [Open Food Facts](https://world.openfoodfacts.org). The food form opens pre-filled so you can check it, and nothing is added until you press Save. If you're offline, the form still opens blank, with a notice that there's no internet connection.
- **Fix broken CSVs on the spot.** If a column is missing or a value is invalid, a popup shows the whole file as an editable table. Correct the cells (including column names) and resubmit, or skip the bad rows. Your original file is never changed.

- **Export foods and recipes to CSV** from Settings, and **import recipes from CSV** with the same import button (one row per ingredient, ingredients matched by name, existing recipes never overwritten). Import foods first on a new computer.

### Look back
- A **Calendar** of past days: a green tick for days with entries and a red cross for days without, starting from your first logged day. Click a date to open it.

### Keep your data safe
- **Export and restore backups** from Settings.
- **Export your diary to CSV** whenever you like, and open the data folder straight from the app.
- Everything stays local. The only time the app uses the internet is the barcode lookup, and only when you import a barcode photo; just the barcode number is sent, never the photo.

## Tips

- You can drag CSV files, photos or zip files onto any page of the app, several at once.
- **Esc** (or **Ctrl+W**) closes any pop-up window; **Enter** saves a food/recipe or adds the chosen item.
- **Ctrl+F** (Cmd+F on macOS) focuses the search on Foods & recipes, which is also focused when you open it. Ctrl+N adds a food, Ctrl+Shift+N a recipe.
- **Ctrl+1…6** switch pages. On the Diary: **Alt+←/→** change day, **Ctrl+T** today, **Alt+1…4** add to a meal, **Ctrl+Shift+A** quick add.
- Clicking or tabbing into a field selects its text, so typing replaces it.
- **F1**, or the **Help** page, explains every shortcut. Ctrl+1…6 switch pages.

---

## Local setup

**Requirements:** Python 3.14 and Windows (the commands below use PowerShell).

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python app.py
```

The first launch creates `data\calorie_tracker.sqlite3` and fills it with the basic foods from `food_macros_seed.csv`.

Barcode photos need the `zxing-cpp` and `Pillow` packages, which install with the command above. If `zxing-cpp` has no build for your platform, the rest of the app still works and the barcode option explains what's missing.

**Run the tests**

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -v
```

Tests use temporary databases and never touch your `data` folder.

**Build a single .exe:** see [`exe/BUILD_EXE.md`](exe/BUILD_EXE.md) and run `exe\build_exe.ps1`.