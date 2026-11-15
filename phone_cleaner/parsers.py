"""Чистые функции-парсеры вывода adb (легко тестировать)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class DeviceEntry:
    serial: str
    state: str
    props: dict[str, str] = field(default_factory=dict)

    @property
    def model(self) -> str:
        raw = self.props.get("model") or self.props.get("device") or ""
        return raw.replace("_", " ").strip()

    @property
    def is_ready(self) -> bool:
        return self.state == "device"

    @property
    def title(self) -> str:
        if self.model:
            return f"{self.model} ({self.serial})"
        return self.serial


def parse_devices(output: str) -> list[DeviceEntry]:
    """Разбирает вывод `adb devices -l`."""
    devices: list[DeviceEntry] = []
    for line in (output or "").splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        props: dict[str, str] = {}
        for token in parts[2:]:
            if ":" in token:
                key, _, value = token.partition(":")
                props[key] = value
        devices.append(DeviceEntry(serial=serial, state=state, props=props))
    return devices


_PROP_LINE = re.compile(r"^\[(?P<key>[^\]]+)\]:\s*\[(?P<value>.*)\]$")


def parse_getprop(output: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in (output or "").splitlines():
        match = _PROP_LINE.match(line.strip())
        if match:
            props[match.group("key")] = match.group("value")
    return props


def parse_pm_list(output: str) -> list[tuple[str, str | None]]:
    """Разбирает `pm list packages -f`. Возвращает (package, apk_path)."""
    result: list[tuple[str, str | None]] = []
    for line in (output or "").splitlines():
        line = line.strip()
        if not line.startswith("package:"):
            continue
        body = line[len("package:"):]
        if "=" in body:
            path, _, name = body.rpartition("=")
            result.append((name.strip(), path.strip() or None))
        else:
            result.append((body.strip(), None))
    return result


_NUM_LIST = re.compile(r"\[\s*|\s*\]")


def _parse_int_list(raw: str) -> list[int]:
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [int(x) for x in data]
    except (ValueError, TypeError):
        values = re.findall(r"-?\d+", raw)
        return [int(v) for v in values]


def parse_diskstats(output: str) -> dict[str, dict[str, int]]:
    """Разбирает `dumpsys diskstats` → {package: {app, data, cache}} в байтах."""
    text = output or ""
    names: list[str] = []
    app_sizes: list[int] = []
    data_sizes: list[int] = []
    cache_sizes: list[int] = []

    match = re.search(r"Package Names:\s*(\[[^\]]*\])", text)
    if match:
        try:
            names = [str(n) for n in json.loads(match.group(1))]
        except ValueError:
            names = re.findall(r'"([^"]+)"', match.group(1))

    for key, target in (("App Sizes", "app"), ("App Data Sizes", "data"), ("Cache Sizes", "cache")):
        found = re.search(rf"{key}:\s*(\[[^\]]*\])", text)
        if not found:
            continue
        values = _parse_int_list(found.group(1))
        if target == "app":
            app_sizes = values
        elif target == "data":
            data_sizes = values
        else:
            cache_sizes = values

    result: dict[str, dict[str, int]] = {}
    for index, name in enumerate(names):
        result[name] = {
            "app": app_sizes[index] if index < len(app_sizes) else 0,
            "data": data_sizes[index] if index < len(data_sizes) else 0,
            "cache": cache_sizes[index] if index < len(cache_sizes) else 0,
        }
    return result


def parse_du(output: str) -> list[tuple[str, int]]:
    """Разбирает `du -ak` → [(path, bytes)]."""
    rows: list[tuple[str, int]] = []
    for line in (output or "").splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 2:
            parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        size, path = parts
        try:
            rows.append((path.strip(), int(size) * 1024))
        except ValueError:
            continue
    return rows


def parse_battery(output: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in (output or "").splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            data[key.strip().lower()] = value.strip()
    return data


_SIZE_UNITS = {"B": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}


def parse_df(output: str) -> list[dict[str, str]]:
    """Разбирает `df -h` в список словарей {filesystem, size, used, avail, use, mounted}."""
    rows: list[dict[str, str]] = []
    for line in (output or "").splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        rows.append({
            "filesystem": parts[0],
            "size": parts[1],
            "used": parts[2],
            "avail": parts[3],
            "use": parts[4],
            "mounted": " ".join(parts[5:]),
        })
    return rows


def parse_size_text(text: str) -> int:
    """«12.3M» → байты."""
    text = (text or "").strip()
    match = re.match(r"^([\d.,]+)\s*([BKMGT]?)i?B?$", text, re.IGNORECASE)
    if not match:
        return 0
    number = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "B").upper()
    return int(number * _SIZE_UNITS.get(unit, 1))


def human_size(num_bytes: float) -> str:
    num = float(num_bytes or 0)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if abs(num) < 1024 or unit == "ТБ":
            return f"{num:,.0f} {unit}" if unit == "Б" else f"{num:,.1f} {unit}".replace(",", " ")
        num /= 1024
    return f"{num:.1f} ТБ"


def parse_wm_size(output: str) -> tuple[int, int]:
    match = re.search(r"(\d+)x(\d+)", output or "")
    if match:
        return int(match.group(1)), int(match.group(2))
    return 0, 0
