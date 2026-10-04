from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
import logging
from pathlib import Path

from . import paths
from .application.catalogue import CatalogueService
from .application.diary import DiaryService
from .application.product_import import BarcodeReader, ProductImportService, ProductLookup
from .infrastructure.database import Database
from .infrastructure.backup import BackupService
from .infrastructure.barcode_reader import ZxingBarcodeReader
from .infrastructure.open_food_facts import OpenFoodFactsLookup
from .infrastructure.importer import CsvFoodImporter
from .infrastructure.diary_csv_importer import CsvDiaryImporter
from .infrastructure.recipe_csv_importer import CsvRecipeImporter
from .infrastructure.catalogue_query import CatalogueQuery
from .infrastructure.repositories import (
    DiaryRepository,
    FoodRepository,
    RecipeRepository,
    SettingsRepository,
)


@dataclass(frozen=True)
class ApplicationServices:
    database: Database
    foods: FoodRepository
    recipes: RecipeRepository
    diary_repository: DiaryRepository
    settings: SettingsRepository
    catalogue: CatalogueService
    diary: DiaryService
    importer: CsvFoodImporter
    diary_importer: CsvDiaryImporter
    backup: BackupService
    product_import: ProductImportService
    recipe_importer: CsvRecipeImporter
    catalogue_query: CatalogueQuery


def _configure_logging(data_dir: Path) -> None:
    logger = logging.getLogger("calorie_tracker")
    if not logger.handlers:
        logs_dir = data_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            logs_dir / "application.log", maxBytes=512_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def build_services(
    database_path: Path | str,
    seed_source_path: Path | str | None = None,
    *,
    barcode_reader: BarcodeReader | None = None,
    product_lookup: ProductLookup | None = None,
) -> ApplicationServices:
    path = Path(database_path)
    database = Database(path)
    database.initialize()
    _configure_logging(path.parent)
    foods = FoodRepository(database)
    recipes = RecipeRepository(database, foods)
    diary_repository = DiaryRepository(database)
    settings = SettingsRepository(database)
    catalogue = CatalogueService(foods, recipes)
    diary = DiaryService(foods, recipes, diary_repository)
    importer = CsvFoodImporter(foods)
    diary_importer = CsvDiaryImporter(foods)
    if seed_source_path is not None and settings.get_json("initial_food_seed_v1") is None:
        source = Path(seed_source_path)
        if source.is_file():
            try:
                preview = importer.preview(source)
                result = importer.apply(preview)
                settings.set_json("initial_food_seed_v1", {
                    "source": source.name,
                    "imported": result.imported,
                    "completed": True,
                })
                logging.getLogger("calorie_tracker").info(
                    "Initial food catalogue seeded: imported=%s existing=%s conflicts=%s",
                    result.imported, result.already_present, result.name_conflicts,
                )
            except (OSError, ValueError):
                logging.getLogger("calorie_tracker").exception(
                    "Initial food catalogue seed failed for %s", source
                )
    backup = BackupService(database, path.parent / "backups")
    return ApplicationServices(
        database, foods, recipes, diary_repository, settings, catalogue, diary,
        importer, diary_importer, backup,
        ProductImportService(barcode_reader or ZxingBarcodeReader(), product_lookup or OpenFoodFactsLookup()),
        CsvRecipeImporter(foods, recipes),
        CatalogueQuery(database),
    )


def default_database_path() -> Path:
    return paths.default_database_path()
