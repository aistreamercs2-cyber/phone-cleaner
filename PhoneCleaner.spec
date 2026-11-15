# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-спецификация: PhoneCleaner.exe (Windows) одним файлом.

Сборка:  pyinstaller --noconfirm --clean PhoneCleaner.spec
Результат: dist/PhoneCleaner.exe
"""

from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)  # type: ignore[name-defined]  # noqa: F821 - задаётся PyInstaller

ICON = ROOT / "phone_cleaner" / "assets" / "icon.ico"
if not ICON.is_file():
    ICON = ROOT / "phone_cleaner" / "assets" / "icon.png"

# Qt: не тащим лишние плагины (QML/3D/WebEngine не используются)
EXCLUDED_MODULES = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.QtMultimedia", "PySide6.Qt3DCore",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtSql", "PySide6.QtTest",
    "tkinter", "unittest", "pydoc", "pytest",
]

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "phone_cleaner" / "assets"), "phone_cleaner/assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PhoneCleaner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # GUI без чёрного окна консоли
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.is_file() else None,
    version=None,
)
