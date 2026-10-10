"""What the app can import, written once: used by the ``?`` help page and checked against the real importers.

Headers and the "also accepted" names come straight from the importers' own alias tables, so the help can
never drift from what the importers actually understand (a test imports every example below).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from calorie_tracker.infrastructure.csv_headers import (
    DIARY_FIELD_ALIASES,
    FIELD_LABELS,
    FOOD_FIELD_ALIASES,
    RECIPE_FIELD_ALIASES,
    normalize_header,
)
from calorie_tracker.infrastructure.csv_kind import DIARY_REQUIRED_FIELDS, CsvKind
from calorie_tracker.infrastructure.importer import FOOD_REQUIRED_FIELDS
from calorie_tracker.infrastructure.recipe_csv_importer import REQUIRED_FIELDS as RECIPE_REQUIRED_FIELDS


@dataclass(frozen=True)
class FormatDoc:
    kind: CsvKind
    title: str
    purpose: str
    header: tuple[str, ...]
    required: tuple[str, ...]
    example_row: str
    notes: tuple[str, ...]
    also_accepted: tuple[tuple[str, tuple[str, ...]], ...]  # (canonical column, other names it can have)

    @property
    def header_line(self) -> str:
        return ",".join(self.header)

    @property
    def example_text(self) -> str:
        """Header plus example row: what you could paste into the raw input box."""
        return f"{self.header_line}\n{self.example_row}"


def _also(aliases: Mapping[str, Sequence[str]], header: Sequence[str], alias_field: dict[str, str]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    rows = []
    for column in header:
        field = alias_field.get(column, column)
        names = tuple(
            alias for alias in aliases.get(field, ()) if normalize_header(alias) != normalize_header(column)
        )
        if names:
            rows.append((column, names))
    return tuple(rows)


FORMAT_DOCS: tuple[FormatDoc, ...] = (
    FormatDoc(
        kind=CsvKind.FOODS,
        title="Foods",
        purpose="Adds foods to your catalogue, one row per food.",
        header=("food_name", "basis", "calories", "fat", "saturated_fat", "carbohydrates", "sugars", "protein",
                "fiber", "omega_3", "omega_6"),
        required=FOOD_REQUIRED_FIELDS,
        example_row="Oats,g,380,7,1,60,1,13,10,0.1,1.2",
        notes=(
            "Required columns: " + ", ".join(FIELD_LABELS[field] for field in FOOD_REQUIRED_FIELDS) + ". The others are optional.",
            "Nutrient values are per 100 g. Put count in the basis column when the values are per single item instead.",
            "A food whose name already exists is skipped, never changed.",
        ),
        also_accepted=_also(FOOD_FIELD_ALIASES, ("food_name", "basis", "calories", "fat", "carbohydrates", "protein", "fiber"), {}),
    ),
    FormatDoc(
        kind=CsvKind.DIARY,
        title="Diary entries",
        purpose="Adds what you ate, one row per food and amount.",
        header=("food_name", "grams_eaten", "meal"),
        required=DIARY_REQUIRED_FIELDS,
        example_row="Oats,45.5,Breakfast",
        notes=(
            "Required columns: food name and amount. The meal column is optional (Breakfast, Lunch, Dinner or Snacks); "
            "you can pick or split meals in the review.",
            "Amounts are grams, or a number of items for foods counted per item.",
            "Food names are matched to the foods you already have. A name that is not found gets a suggestion; "
            "only spelling-level matches (case, accents, plural, word order, a small typo) are pre-selected, and you confirm them.",
            "Rows go to the day shown on the Diary page, unless the file is named diary-YYYY-MM-DD.csv.",
        ),
        also_accepted=_also(DIARY_FIELD_ALIASES, ("food_name", "grams_eaten", "meal"), {"grams_eaten": "amount_g"}),
    ),
    FormatDoc(
        kind=CsvKind.RECIPES,
        title="Recipes",
        purpose="Adds recipes, one row per ingredient.",
        header=("recipe_name", "yield_g", "ingredient", "amount"),
        required=RECIPE_REQUIRED_FIELDS,
        example_row="Porridge,350,Oats,100",
        notes=(
            "Required columns: recipe name, ingredient and amount. The final yield is optional when every ingredient is weighed.",
            "The recipe name (and yield) can be written on the first row only. The recipe export also writes a unit column, which is ignored.",
            "Ingredients are matched by name to foods you already have, so foods are imported first.",
            "A recipe whose name already exists is skipped, never overwritten.",
        ),
        also_accepted=_also(RECIPE_FIELD_ALIASES, ("recipe_name", "yield_g", "ingredient", "amount"), {}),
    ),
)

OTHER_FILES: tuple[tuple[str, str], ...] = (
    ("Photos", "A photo of a product's barcode (JPEG, PNG, WebP, HEIC and more) adds one food: the barcode is read on this "
               "computer, the nutrients are looked up online, and you check them before saving."),
    ("Zip files", "A zip can hold CSV files and photos. Only CSV files and photos are used. Files at the top level and the "
                  "files of one folder are all taken; folders inside that folder are ignored; more than one folder is an error."),
    ("Several files at once", "Drop or choose as many files and zips as you like. They are imported one after another in this "
                              "order: foods, photos, recipes, diary entries, so new foods exist before the recipes and diary rows that use them. "
                              "Each one has its own review before anything is saved."),
    ("How CSV files are recognised", "The header row decides: a CSV with food name, calories, protein, fat and carbohydrates columns "
                                     "is foods; food name and amount is diary entries; recipe name, ingredient and amount is recipes. "
                                     "If it cannot tell, it asks you."),
    ("Delimiters and numbers", "Commas, semicolons, tabs and pipes all work. Decimal commas and units such as “45 g” are understood."),
)


# Colours for the help page, so its text is readable on the app's light background in any system theme.
HELP_DOCUMENT_STYLE = (
    "body, p, li, td, b { color: #243041; } "
    "h2 { color: #172538; } h3 { color: #263752; } "
    "code { color: #172538; background-color: #dfe8f5; font-family: Consolas, 'Courier New', monospace; }"
)


def render_help_html(docs: Sequence[FormatDoc] = FORMAT_DOCS, others: Sequence[tuple[str, str]] = OTHER_FILES) -> str:
    """The import help page as HTML (headers, examples and notes), safe to show in a rich-text widget."""
    from html import escape

    parts = [
        "<h2 style='color:#172538;'>What you can import</h2>",
        "<p>Every import button works the same way: choose or drop CSV files, barcode photos or zip files. "
        "You can also paste CSV text. Nothing is saved until you confirm it in a review screen.</p>",
    ]
    for doc in docs:
        parts.append(f"<h3 style='color:#263752;'>{escape(doc.title)} (CSV)</h3><p>{escape(doc.purpose)}</p>")
        parts.append("<p><b>Header row</b><br><code>" + escape(doc.header_line) + "</code></p>")
        parts.append("<p><b>Example row</b><br><code>" + escape(doc.example_row) + "</code></p>")
        parts.append("<ul>" + "".join(f"<li>{escape(note)}</li>" for note in doc.notes) + "</ul>")
        if doc.also_accepted:
            names = "; ".join(
                f"<code>{escape(column)}</code>: " + ", ".join(escape(name) for name in alternatives[:8])
                for column, alternatives in doc.also_accepted
            )
            parts.append(f"<p><b>Other column names that are understood</b><br>{names}</p>")
    parts.append("<h3 style='color:#263752;'>Other files</h3>")
    parts.append("<ul>" + "".join(f"<li><b>{escape(title)}.</b> {escape(text)}</li>" for title, text in others) + "</ul>")
    return "<div style='color:#243041;'>" + "".join(parts) + "</div>"
