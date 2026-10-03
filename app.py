"""Thin local desktop application launcher."""

from pathlib import Path
import sys


def main() -> int:
    project_root = Path(__file__).resolve().parent
    source_dir = project_root / "src"
    if not getattr(sys, "frozen", False) and str(source_dir) not in sys.path:
        sys.path.insert(0, str(source_dir))

    if sys.platform == "win32":
        # Gives the app its own taskbar identity so the taskbar shows our icon (not Python's).
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DailyPlate.CalorieTracker")
        except Exception:
            pass

    from calorie_tracker.bootstrap import build_services, default_database_path
    from calorie_tracker.paths import seed_csv_path
    from calorie_tracker.presentation.app_icon import load_app_icon
    from calorie_tracker.presentation.main_window import MainWindow
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("Daily Plate")
    application.setWindowIcon(load_app_icon())  # also used by every dialog
    services = build_services(
        default_database_path(),
        seed_source_path=seed_csv_path(),
    )
    window = MainWindow(services)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
