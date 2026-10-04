# Daily Plate

**A private calorie and macro tracker that lives entirely on your computer.**

Log what you eat, build your own food and recipe catalogue, and see how each day adds up against your targets. There are no accounts, no cloud and no ads. Your data is a single file on your own disk.

## What you can do

### Track your day
- Log foods and recipes into **Breakfast, Lunch, Dinner and Snacks**: by gram amount, or by **count** for foods you add "per item" (an egg, a slice of bread; halves and thirds are fine).
- **Quick add** several entries on several meals at once: type one line each ("Oats 45 breakfast", "Egg 1/2 lunch") and fix anything that was not understood on the review table.
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
- **Import a day from CSV.** Drop a spreadsheet export onto the Diary page. Column names are matched flexibly, and the separators `, ; tab |`, decimal commas (`45,5`) and units (`45 g`) are understood. A review table shows how every row was read, with "did you mean" hints for foods it can't find. Nothing is saved until you confirm.
- **Import foods from CSV.** Same idea for your catalogue. Existing foods are never overwritten.
- **Add a food from a barcode photo.** Drop a photo of a product's barcode onto the Foods page (JPEG, PNG, WebP and other common formats). The barcode is read on your computer and the nutrients are looked up on [Open Food Facts](https://world.openfoodfacts.org). The food form opens pre-filled so you can check it, and nothing is added until you press Save. If you're offline, the form still opens blank, with a notice that there's no internet connection.
- **Fix broken CSVs on the spot.** If a column is missing or a value is invalid, a popup shows the whole file as an editable table. Correct the cells (including column names) and resubmit, or skip the bad rows. Your original file is never changed.

- **Export foods and recipes to CSV** from Settings, and **import recipes from CSV** (one row per ingredient, ingredients matched by name, existing recipes never overwritten). Import foods first on a new computer.

### Look back
- A **Calendar** of past days: a green tick for days with entries and a red cross for days without, starting from your first logged day. Click a date to open it.

### Keep your data safe
- **Export and restore backups** from Settings.
- **Export your diary to CSV** whenever you like, and open the data folder straight from the app.
- Everything stays local. The only time the app uses the internet is the barcode lookup, and only when you import a barcode photo; just the barcode number is sent, never the photo.

## Tips

- You can drag a CSV or photo almost anywhere on the Foods page, and a CSV anywhere on the Diary page.
- **Esc** (or **Ctrl+W**) closes any pop-up window; **Enter** saves a food/recipe or adds the chosen item.
- **Ctrl+F** (Cmd+F on macOS) focuses the search on Foods & recipes, which is also focused when you open it. Ctrl+N adds a food, Ctrl+Shift+N a recipe.
- **Ctrl+1…4** switch pages. On the Diary: **Alt+←/→** change day, **Ctrl+T** today, **Alt+1…4** add to a meal, **Ctrl+Shift+A** quick add.
- Clicking or tabbing into a field selects its text, so typing replaces it.
- **F1**, or **Settings → Keyboard shortcuts**, opens a pop-up explaining every shortcut.

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