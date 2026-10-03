import csv
from pathlib import Path

from calorie_tracker.domain.diary import DiaryEntry

HEADER = (
    "date", "meal", "food_name", "grams_eaten",
    "calories", "protein", "carbohydrates", "fat", "fiber",
)


def export_diary_csv(entries: tuple[DiaryEntry, ...], path: Path | str) -> int:
    """Write every diary entry to a spreadsheet-friendly CSV and return the number of rows."""
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADER)
        for entry in entries:
            nutrients = entry.nutrients
            writer.writerow((
                entry.diary_date, entry.meal, entry.display_name, f"{entry.amount_g.normalize():f}",
                f"{nutrients.calories:.1f}", f"{nutrients.protein:.2f}",
                f"{nutrients.carbohydrates:.2f}", f"{nutrients.fat:.2f}", f"{nutrients.fiber:.2f}",
            ))
    return len(entries)
