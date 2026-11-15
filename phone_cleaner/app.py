"""Запуск приложения: настройка логов, темы и главного окна."""

from __future__ import annotations

import logging
import os
import sys

from . import APP_NAME, APP_VERSION
from .paths import app_dir, log_file


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file(), encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )
    logging.getLogger(__name__).info("Запуск %s %s", APP_NAME, APP_VERSION)


def selftest() -> int:
    """Быстрая проверка сборки: GUI создаётся и закрывается без телефона."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        print(f"НЕТ PySide6: {exc}")
        return 2
    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    window = MainWindow()
    window.show()
    app.processEvents()
    tabs = window.tabs.count()
    window.close()
    print(f"OK: окно создано, вкладок {tabs}, версия {APP_VERSION}")
    return 0 if tabs >= 4 else 1


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv)
    if "--selftest" in args:
        setup_logging()
        return selftest()

    setup_logging()
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        print("PySide6 не установлен. Выполните: pip install -r requirements.txt", file=sys.stderr)
        return 2

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(args)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("PhoneCleaner")
    app.setDesktopFileName("PhoneCleaner")

    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    apply_theme(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
