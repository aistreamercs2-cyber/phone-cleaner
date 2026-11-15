"""Пути приложения (работает и из исходников, и из собранного exe)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_SLUG


def app_dir() -> Path:
    """Каталог с настройками, логами и скачанным ADB."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    path = Path(base) / APP_SLUG
    path.mkdir(parents=True, exist_ok=True)
    return path


def platform_tools_dir() -> Path:
    path = app_dir() / "platform-tools"
    path.mkdir(parents=True, exist_ok=True)
    return path


def temp_dir() -> Path:
    path = app_dir() / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file() -> Path:
    return app_dir() / "phone-cleaner.log"


def settings_file() -> Path:
    return app_dir() / "settings.json"


def adb_executable_name() -> str:
    return "adb.exe" if os.name == "nt" else "adb"


def bundled_path(*parts: str) -> Path:
    """Путь к ресурсу, в том числе внутри onefile-сборки PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root.joinpath(*parts)


def find_adb() -> Path | None:
    """Ищем adb: сначала свой скачанный, потом PATH."""
    name = adb_executable_name()
    candidates = [platform_tools_dir() / name]
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if folder.strip():
            candidates.append(Path(folder) / name)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None
