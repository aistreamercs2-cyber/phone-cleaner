"""Скачивание и установка самого свежего ADB (platform-tools) с GitHub.

Порядок источников (всегда берётся *последний* релиз, версии не прибиты гвоздями):

Windows
  1. GitHub-релиз K3V1991/ADBKit  → zip с adb.exe
  2. Файлы adb.exe / dll прямо из тега того же релиза
  3. Официальный platform-tools от Google (запасной вариант)

Linux / macOS
  1. GitHub-релиз lzhiyong/android-sdk-tools → статический adb под вашу архитектуру
  2. Официальный platform-tools от Google (запасной вариант)
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import APP_NAME, APP_VERSION
from .paths import adb_executable_name, platform_tools_dir

USER_AGENT = f"{APP_NAME.replace(' ', '')}/{APP_VERSION}"
TIMEOUT = 60
CHUNK = 256 * 1024

GOOGLE_URL = "https://dl.google.com/android/repository/platform-tools-latest-{os}.zip"
ADBKIT_REPO = "K3V1991/ADBKit"
SDK_TOOLS_REPO = "lzhiyong/android-sdk-tools"
ADBKIT_FILES = ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll")

ProgressCb = Callable[[str, float], None]


class AdbInstallError(RuntimeError):
    pass


@dataclass
class Asset:
    name: str
    url: str
    source: str


def _emit(cb: ProgressCb | None, message: str, progress: float = -1) -> None:
    if cb:
        cb(message, progress)


def _os_key() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "darwin"
    return "linux"


def _api(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def latest_release(repo: str) -> dict | None:
    try:
        return _api(f"https://api.github.com/repos/{repo}/releases/latest")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return None


def download(url: str, destination: Path, cb: ProgressCb | None = None, label: str = "Загрузка") -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp, open(destination, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(CHUNK)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total > 0:
                _emit(cb, f"{label} — {done * 100 // total}%  ({done // 1024} / {total // 1024} КБ)", done / total)
            else:
                _emit(cb, f"{label} — {done // 1024} КБ", -1)
    return destination


def _install_perm(path: Path) -> None:
    if os.name != "nt":
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _extract_adb(archive: Path, target: Path, cb: ProgressCb | None = None) -> None:
    """Достаёт adb и вспомогательные файлы из zip любой вложенности."""
    keep = {n.lower() for n in (*ADBKIT_FILES, "adb", "fastboot", "fastboot.exe")}
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        for index, member in enumerate(members):
            base = Path(member.filename).name
            if base.lower() not in keep:
                continue
            _emit(cb, f"Распаковка {base}…", index / max(1, len(members)))
            out_path = target / base
            with zf.open(member) as src, open(out_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            _install_perm(out_path)


def verify_adb(adb_path: Path) -> bool:
    try:
        result = subprocess.run(
            [str(adb_path), "version"],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0 and "Android Debug Bridge" in (result.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return False


def adb_version(adb_path: Path) -> str:
    try:
        result = subprocess.run(
            [str(adb_path), "version"], capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        lines = [ln.strip() for ln in (result.stdout or "").splitlines() if ln.strip()]
        return lines[1] if len(lines) > 1 else (lines[0] if lines else "неизвестно")
    except (OSError, subprocess.SubprocessError):
        return "неизвестно"


def _windows_sources(cb: ProgressCb | None):
    release = latest_release(ADBKIT_REPO)
    if release:
        tag = release.get("tag_name") or ""
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if name.lower().endswith(".zip"):
                yield ("zip", Asset(name, asset["browser_download_url"], f"GitHub {ADBKIT_REPO} {tag}"))
        if tag:
            yield ("raw", Asset("adb.exe (raw)", "", f"GitHub {ADBKIT_REPO} {tag}"))
    # второй GitHub-источник
    release2 = latest_release("K3V1991/ADB-and-FastbootPlusPlus")
    if release2:
        for asset in release2.get("assets", []):
            name = asset.get("name", "")
            if name.lower().endswith(".zip"):
                yield ("zip", Asset(name, asset["browser_download_url"],
                                    f"GitHub K3V1991/ADB-and-FastbootPlusPlus {release2.get('tag_name')}"))

    # запасной вариант — официальный архив Google
    yield ("zip", Asset("platform-tools (Google)", GOOGLE_URL.format(os="windows"), "Google"))


def _unix_sources(cb: ProgressCb | None):
    os_key = _os_key()
    release = latest_release(SDK_TOOLS_REPO)
    arch = platform.machine().lower()
    want = "aarch64" if arch in ("aarch64", "arm64") else "x86_64"
    if release:
        for asset in release.get("assets", []):
            name = asset.get("name", "").lower()
            if name.endswith(".zip") and f"{want}" in name:
                if os_key == "darwin" or "darwin" in name or "mac" in name or os_key == "linux":
                    yield ("zip", Asset(asset["name"], asset["browser_download_url"],
                                        f"GitHub {SDK_TOOLS_REPO} {release.get('tag_name')}"))
    yield ("zip", Asset("platform-tools (Google)", GOOGLE_URL.format(os=os_key), "Google"))


def _raw_hook_download(tag: str, target: Path, cb: ProgressCb | None) -> None:
    """Скачивает adb.exe и dll по отдельности из тега релиза на GitHub."""
    for i, name in enumerate(ADBKIT_FILES):
        url = f"https://raw.githubusercontent.com/{ADBKIT_REPO}/{tag}/{name}"
        _emit(cb, f"Загрузка {name}…", i / len(ADBKIT_FILES))
        download(url, target / name, cb, f"Загрузка {name}")
        _install_perm(target / name)


def install_latest_adb(force: bool = False, cb: ProgressCb | None = None) -> Path:
    """Ставит самый свежий ADB и возвращает путь к исполняемому файлу."""
    target = platform_tools_dir()
    adb_path = target / adb_executable_name()

    if adb_path.is_file() and not force and verify_adb(adb_path):
        _emit(cb, f"ADB уже установлен — {adb_version(adb_path)}", 1.0)
        return adb_path

    errors: list[str] = []
    sources = _windows_sources(cb) if os.name == "nt" else _unix_sources(cb)

    for kind, asset in sources:
        try:
            if kind == "raw":
                release = latest_release(ADBKIT_REPO) or {}
                tag = release.get("tag_name")
                if not tag:
                    continue
                _emit(cb, f"Источник: {asset.source}", 0.0)
                _raw_hook_download(tag, target, cb)
            else:
                _emit(cb, f"Источник: {asset.source}", 0.0)
                with tempfile.TemporaryDirectory(dir=str(target.parent)) as tmp:
                    archive = Path(tmp) / "adb-download.zip"
                    download(asset.url, archive, cb, f"Загрузка {asset.name}")
                    _emit(cb, "Распаковка…", 0.95)
                    _extract_adb(archive, target, cb)
            if adb_path.is_file() and verify_adb(adb_path):
                _emit(cb, f"Готово: {adb_version(adb_path)}", 1.0)
                return adb_path
            errors.append(f"{asset.source}: в архиве нет рабочего adb")
        except (urllib.error.URLError, urllib.error.HTTPError, zipfile.BadZipFile, OSError,
                TimeoutError, ValueError) as exc:
            errors.append(f"{asset.source}: {exc}")

    raise AdbInstallError(
        "Не удалось автоматически установить ADB.\n\n"
        "Проверьте подключение к интернету или скачайте platform-tools вручную\n"
        "и положите adb в папку:\n"
        f"{target}\n\n"
        "Подробности:\n" + "\n".join(f"• {e}" for e in errors)
    )
