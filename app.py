"""Thin local desktop application launcher."""

from pathlib import Path
import sys


def main() -> int:
    project_root = Path(__file__).resolve().parent
    source_dir = project_root / "src"
    if str(source_dir) not in sys.path:
        sys.path.insert(0, str(source_dir))

    from calorie_tracker.bootstrap import build_services, default_database_path
    from calorie_tracker.presentation.main_window import MainWindow
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication(sys.argv)
    services = build_services(default_database_path())
    window = MainWindow(services)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
