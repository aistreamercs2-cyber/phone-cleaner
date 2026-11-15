"""Тесты слоя ADB без реального телефона: подменяем subprocess.run."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from phone_cleaner import adb as adb_module
from phone_cleaner.adb import PROTECTED_PACKAGES, Adb, quote_path


class FakeCompleted:
    def __init__(self, stdout: str = "", stderr: str = "", code: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = code


@pytest.fixture()
def fake_adb(tmp_path, monkeypatch):
    exe = tmp_path / "adb"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)

    calls: list[list[str]] = []
    responses: dict[str, FakeCompleted] = {}

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        joined = " ".join(cmd)
        for needle, response in responses.items():
            if needle in joined:
                return response
        return FakeCompleted(stdout="")

    monkeypatch.setattr(adb_module.subprocess, "run", fake_run)
    client = Adb(adb_path=exe, serial="SERIAL123")
    return client, calls, responses


def test_list_devices_parses(fake_adb):
    client, calls, responses = fake_adb
    responses["devices"] = FakeCompleted("List of devices attached\nSERIAL123\tdevice\n")
    devices = client.list_devices()
    assert [d.serial for d in devices] == ["SERIAL123"]
    # list_devices всегда спрашивает все устройства: без -s
    assert calls[0] == [str(client.adb_path), "devices", "-l"]


def test_uninstall_skips_protected(fake_adb):
    client, calls, responses = fake_adb
    responses["pm uninstall"] = FakeCompleted("Success\n")
    report = client.uninstall({"com.android.systemui", "com.example.junk"}, for_user=True)
    names = {name: ok for name, ok, _ in report}
    assert names["com.android.systemui"] is False
    assert names["com.example.junk"] is True
    assert any("com.android.systemui" not in c for c in calls)
    assert "com.android.systemui" in PROTECTED_PACKAGES


def test_package_sizes_uses_diskstats(fake_adb):
    client, _, responses = fake_adb
    responses["diskstats"] = FakeCompleted(
        'Package Names: ["com.a"]\nApp Sizes: [10]\nApp Data Sizes: [20]\nCache Sizes: [5]\n'
    )
    sizes = client.package_sizes()
    assert sizes["com.a"] == {"app": 10, "data": 20, "cache": 5}


def test_restore_parses_success(fake_adb):
    client, _, responses = fake_adb
    responses["install-existing"] = FakeCompleted("Package com.a installed for user: 0\n")
    ok, message = client.restore("com.a")
    assert ok is True
    assert "installed" in message


def test_timeout_returns_code_124(fake_adb, monkeypatch):
    client, _, _ = fake_adb

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="adb", timeout=1)

    monkeypatch.setattr(adb_module.subprocess, "run", boom)
    result = client.shell("sleep 100")
    assert result.code == 124
    assert not result.ok


def test_quote_path_keeps_globs():
    assert quote_path("/sdcard/Android/data/*/cache") == "/sdcard/Android/data/*/cache"
    assert quote_path("/sdcard/My Files") == "'/sdcard/My Files'"


def test_screenshot_writes_file(fake_adb, tmp_path, monkeypatch):
    client, _, _ = fake_adb

    def fake_run(cmd, **kwargs):
        return FakeCompleted(stdout=b"\x89PNG fake", stderr=b"")

    monkeypatch.setattr(adb_module.subprocess, "run", fake_run)
    destination = tmp_path / "shot.png"
    client.screenshot(destination)
    assert destination.read_bytes().startswith(b"\x89PNG")
