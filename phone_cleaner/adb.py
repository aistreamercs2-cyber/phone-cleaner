"""Обёртка над adb: процессы, устройства, пакеты, команды, скриншоты."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from . import parsers
from .paths import adb_executable_name, find_adb, platform_tools_dir, temp_dir

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Пакеты, которые нельзя удалять — от них зависит работа системы/телефона.
PROTECTED_PACKAGES = {
    "android", "com.android.systemui", "com.android.settings", "com.android.phone",
    "com.android.providers.settings", "com.android.providers.media", "com.android.providers.contacts",
    "com.android.providers.telephony", "com.android.providers.downloads", "com.android.shell",
    "com.android.packageinstaller", "com.android.permissioncontroller", "com.android.inputmethod.latin",
    "com.google.android.gms", "com.google.android.gsf", "com.google.android.packageinstaller",
    "com.google.android.permissioncontroller", "com.android.launcher3", "com.google.android.apps.nexuslauncher",
}

# Известный «мусор» — предзаполненный список для вкладки очистки.
BLOATWARE = {
    "facebook": ("com.facebook.katana", "com.facebook.appmanager", "com.facebook.services",
                 "com.facebook.system", "com.facebook.orca"),
    "Google": ("com.google.android.apps.tachyon", "com.google.android.videos", "com.google.android.music",
               "com.google.android.apps.magazines", "com.google.android.apps.podcasts",
               "com.google.android.apps.docs", "com.google.android.apps.photos"),
    "Samsung": ("com.samsung.android.app.spage", "com.samsung.android.bixby.agent",
                "com.samsung.android.bixby.wakeup", "com.samsung.android.app.social",
                "com.samsung.android.game.gamehome", "com.samsung.android.kidsinstaller",
                "com.sec.android.app.sbrowser", "com.samsung.android.mateagent"),
    "Xiaomi": ("com.miui.player", "com.miui.videoplayer", "com.miui.notes", "com.miui.weather2",
               "com.xiaomi.mipicks", "com.mi.globalbrowser", "com.miui.gallery"),
    "Microsoft": ("com.microsoft.skydrive", "com.microsoft.office.outlook", "com.microsoft.office.word",
                  "com.linkedin.android", "com.microsoft.appmanager"),
    "Операторы/прочее": ("com.zhiliaoapp.musically", "com.netflix.partner.activation",
                         "com.booking", "com.tripadvisor.tripadvisor", "com.amazon.appmanager"),
}
BLOATWARE_FLAT = {name: vendor for vendor, names in BLOATWARE.items() for name in names}


class AdbError(RuntimeError):
    pass


@dataclass
class Result:
    args: list[str]
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def output(self) -> str:
        return (self.stdout or "") + (("\n" + self.stderr) if self.stderr.strip() else "")


class Adb:
    """Тонкая обёртка. Все команды выполняются в отдельных процессах."""

    def __init__(self, adb_path: Path | None = None, serial: str | None = None) -> None:
        self.adb_path = Path(adb_path) if adb_path else find_adb()
        self.serial = serial

    # ---------------------------------------------------------------- process
    def _base(self) -> list[str]:
        if not self.adb_path or not Path(self.adb_path).is_file():
            raise AdbError("ADB не найден. Сначала установите ADB на первом шаге.")
        return [str(self.adb_path)]

    def run(self, *args: str, serial: str | None = None, timeout: int = 60,
            binary: bool = False) -> Result:
        cmd = self._base()
        target = serial if serial is not None else self.serial
        if target:
            cmd += ["-s", target]
        cmd += [str(a) for a in args]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=timeout,
                creationflags=CREATE_NO_WINDOW,
                text=not binary,
                errors=None if binary else "replace",
            )
        except subprocess.TimeoutExpired:
            return Result(cmd, 124, "" if not binary else "", "Превышено время ожидания")
        except OSError as exc:
            raise AdbError(str(exc)) from exc
        out = proc.stdout if binary else (proc.stdout or "")
        err = proc.stderr if binary else (proc.stderr or "")
        return Result(cmd, proc.returncode, out, err)

    def shell(self, command: str, timeout: int = 60, serial: str | None = None) -> Result:
        return self.run("shell", command, timeout=timeout, serial=serial)

    def server_start(self) -> Result:
        return self.run("start-server", timeout=120)

    def kill_server(self) -> Result:
        return self.run("kill-server", timeout=30)

    # ---------------------------------------------------------------- devices
    def list_devices(self) -> list[parsers.DeviceEntry]:
        result = self.run("devices", "-l", serial="", timeout=30)
        if result.code != 0:
            self.run("start-server", serial="", timeout=60)
            result = self.run("devices", "-l", serial="", timeout=30)
        return parsers.parse_devices(result.stdout)

    def wait_for_device(self, timeout_ms: int = 20000) -> bool:
        return self.run("wait-for-device", timeout=timeout_ms // 1000 + 5).code == 0

    def props(self, serial: str | None = None) -> dict[str, str]:
        return parsers.parse_getprop(self.shell("getprop", serial=serial).stdout)

    def device_info(self, serial: str | None = None) -> dict[str, str]:
        props = self.props(serial)
        info = {
            "model": props.get("ro.product.model", "—"),
            "brand": props.get("ro.product.brand", "—"),
            "manufacturer": props.get("ro.product.manufacturer", "—"),
            "android": props.get("ro.build.version.release", "—"),
            "sdk": props.get("ro.build.version.sdk", "—"),
            "serial": props.get("ro.serialno", serial or "—"),
            "abi": props.get("ro.product.cpu.abi", "—"),
            "encrypted": props.get("ro.crypto.state", "—"),
        }
        bat = self.shell("dumpsys battery", serial=serial).stdout
        battery = parsers.parse_battery(bat)
        if battery.get("level"):
            info["battery"] = f"{battery['level']}%"
        if battery.get("temperature"):
            try:
                temp = int(battery["temperature"]) / 10
                info["temperature"] = f"{temp:.1f} °C"
            except ValueError:
                pass
        storage = self.storage(serial)
        if storage:
            data = next((s for s in storage if s["mounted"] in ("/data", "/storage/emulated")), storage[0])
            info["storage"] = f"{data['used']} из {data['size']} ({data['use']})"
        return info

    def storage(self, serial: str | None = None) -> list[dict[str, str]]:
        return parsers.parse_df(self.shell("df -h", serial=serial).stdout)

    # ---------------------------------------------------------------- packages
    def packages(self, serial: str | None = None, include_system: bool = True) -> list[tuple[str, str | None]]:
        args = ["pm", "list", "packages", "-f"]
        if not include_system:
            args.append("-3")
        result = self.shell(" ".join(args), serial=serial)
        return parsers.parse_pm_list(result.stdout)

    def package_sizes(self, serial: str | None = None) -> dict[str, dict[str, int]]:
        raw = self.shell("dumpsys diskstats", serial=serial).stdout
        if "Package Names" not in raw:
            return {}
        return parsers.parse_diskstats(raw)

    def is_system_package(self, package: str, serial: str | None = None) -> bool:
        result = self.shell(f"pm path {package}", serial=serial)
        return "/system/" in result.stdout or "/product/" in result.stdout or "/vendor/" in result.stdout

    def uninstall(self, packages: Iterable[str], keep_data: bool = False,
                  for_user: bool = True, serial: str | None = None) -> list[tuple[str, bool, str]]:
        """Удаляет пакеты. for_user=True — удаление для владельца (безопасно, обратимо)."""
        report: list[tuple[str, bool, str]] = []
        for package in packages:
            if package in PROTECTED_PACKAGES:
                report.append((package, False, "защищённый системный пакет — пропущен"))
                continue
            flag = "--user 0" if for_user else ""
            args = f"pm uninstall {flag} {package}".replace("  ", " ")
            if keep_data:
                args += " -k"
            result = self.shell(args, timeout=120, serial=serial)
            text = result.output.strip() or "нет ответа"
            report.append((package, "Success" in text, text.splitlines()[-1] if text else ""))
        return report

    def restore(self, package: str, serial: str | None = None) -> tuple[bool, str]:
        result = self.shell(f"cmd package install-existing {package}", timeout=120, serial=serial)
        return "installed" in result.output.lower(), result.output.strip()

    def clear_data(self, packages: Iterable[str], serial: str | None = None) -> list[tuple[str, bool, str]]:
        report = []
        for package in packages:
            result = self.shell(f"pm clear {package}", timeout=120, serial=serial)
            report.append((package, "Success" in result.output, result.output.strip()))
        return report

    def freeze(self, packages: Iterable[str], disable: bool = True,
               serial: str | None = None) -> list[tuple[str, bool, str]]:
        report = []
        verb = "disable-user --user 0" if disable else "enable"
        for package in packages:
            result = self.shell(f"pm {verb} {package}", timeout=60, serial=serial)
            text = result.output.strip()
            report.append((package, "new state" in text.lower() or "disabled" in text.lower()
                           or "enabled" in text.lower() or result.ok, text))
        return report

    # ---------------------------------------------------------------- files
    def du(self, path: str = "/sdcard", serial: str | None = None) -> list[tuple[str, int]]:
        return parsers.parse_du(self.shell(f"du -ak {quote_path(path)} 2>/dev/null", timeout=180,
                                           serial=serial).stdout)

    def delete_paths(self, paths: Iterable[str], serial: str | None = None) -> list[tuple[str, bool, str]]:
        report = []
        for path in paths:
            result = self.shell(f"rm -rf {quote_path(path)}", timeout=120, serial=serial)
            report.append((path, result.ok, result.output.strip()))
        return report

    def clear_cache(self, packages: Iterable[str], serial: str | None = None) -> list[tuple[str, bool, str]]:
        report = []
        for package in packages:
            result = self.shell(f"pm trim-caches 999G {package}", timeout=60, serial=serial)
            if not result.ok:
                result = self.shell(f"rm -rf /data/data/{package}/cache/*", timeout=60, serial=serial)
            report.append((package, result.ok, result.output.strip()))
        return report

    # ---------------------------------------------------------------- power / control
    def reboot(self, mode: str = "", serial: str | None = None) -> Result:
        return self.run("reboot", mode, serial=serial, timeout=30) if mode else self.run("reboot", serial=serial)

    def install_apk(self, apk_path: str, serial: str | None = None) -> Result:
        return self.run("install", "-r", apk_path, timeout=600, serial=serial)

    def screenshot(self, destination: Path | None = None, serial: str | None = None) -> Path:
        destination = destination or (temp_dir() / "screenshot.png")
        result = self.run("exec-out", "screencap -p", binary=True, timeout=120, serial=serial)
        data = result.stdout if isinstance(result.stdout, bytes) else b""
        if not data:
            raise AdbError("Не удалось сделать скриншот")
        destination.write_bytes(data)
        return destination

    def pull_file(self, remote: str, local: Path, serial: str | None = None) -> Result:
        return self.run("pull", remote, str(local), timeout=1800, serial=serial)

    def push_file(self, local: Path, remote: str, serial: str | None = None) -> Result:
        return self.run("push", str(local), remote, timeout=1800, serial=serial)


class CommandRunner:
    """Неблокирующий запуск длинных adb-команд с построчным выводом."""

    def __init__(self, adb: Adb, on_line: Callable[[str], None],
                 on_done: Callable[[int], None] | None = None) -> None:
        self.adb = adb
        self.on_line = on_line
        self.on_done = on_done
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start(self, args: list[str], serial: str | None = None) -> None:
        cmd = self.adb._base()
        target = serial if serial is not None else self.adb.serial
        if target:
            cmd += ["-s", target]
        cmd += [str(a) for a in args]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", bufsize=1, creationflags=CREATE_NO_WINDOW,
        )
        with self._lock:
            self._proc = proc

        def reader() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                self.on_line(line.rstrip("\n"))
            code = proc.wait()
            if self.on_done:
                self.on_done(code)

        threading.Thread(target=reader, daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass


def quote_path(path: str) -> str:
    """Кавычки для shell, но маски (*, ?) оставляем — иначе glob не раскроется."""
    if "*" in path or "?" in path:
        return path
    return shlex.quote(path)


def parse_shell_command(command: str) -> list[str]:
    """Разбирает пользовательскую команду: "shell ls /sdcard" или "ls /sdcard"."""
    command = (command or "").strip()
    if not command:
        return []
    try:
        parts = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        parts = command.split()
    if not parts:
        return []
    first = parts[0].lower()
    known = {"shell", "install", "uninstall", "push", "pull", "reboot", "devices", "logcat", "screencap",
             "screenrecord", "exec-out", "forward", "reverse", "root", "unroot", "remount", "backup",
             "restore", "bugreport", "get-state", "get-serialno", "tcpip", "usb", "wait-for-device",
             "start-server", "kill-server", "version", "help", "emu", "jdwp", "keygen", "sideload", "disable-verity"}
    if first in known:
        return parts
    return ["shell", *parts]


_ABI_CLEAN = re.compile(r"[^a-z0-9_\-.]")


def safe_filename(name: str) -> str:
    return _ABI_CLEAN.sub("_", name)[:120] or "file"
