from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
import logging
from pathlib import Path

from .application.catalogue import CatalogueService
from .application.diary import DiaryService
from .infrastructure.database import Database
from .infrastructure.importer import CsvFoodImporter
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


def build_services(database_path: Path | str) -> ApplicationServices:
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
    return ApplicationServices(database, foods, recipes, diary_repository, settings, catalogue, diary, importer)


def default_database_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "calorie_tracker.sqlite3"
