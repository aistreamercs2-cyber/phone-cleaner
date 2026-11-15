"""Стартовый экран-мастер: установка ADB → подключение телефона → отладка по USB."""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from ..adb import Adb
from ..adb_installer import adb_version, install_latest_adb
from ..parsers import DeviceEntry
from ..paths import platform_tools_dir
from .theme import ACCENT, DANGER, MUTED, OK, StepLabel, StatusDot
from .worker import Task, run_task


class OnboardingWidget(QWidget):
    """Три шага. Сигнал ready(serial) — когда телефон найден и авторизован."""

    ready = Signal(str)
    finished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.adb_path = None
        self._poll_task = None
        self._monitoring = False
        self._build()
        self._start_adb_install()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 28, 40, 28)
        root.setSpacing(16)

        title = QLabel("Phone Cleaner")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        subtitle = QLabel("Наведём порядок в телефоне: удалим лишние приложения и мусор через ADB")
        subtitle.setObjectName("Subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        root.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("Panel")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 22)
        card_layout.setSpacing(14)
        root.addWidget(card, 1)

        # --- шаг 1
        self.dot1 = StatusDot()
        self.title1 = QLabel("Шаг 1 — установка ADB")
        self.title1.setObjectName("SectionTitle")
        self.step1 = StepLabel("Подготовка…")
        self.progress1 = QProgressBar()
        self.progress1.setRange(0, 100)
        self.progress1.setValue(0)
        self.retry_btn = QPushButton("Повторить установку ADB")
        self.retry_btn.clicked.connect(self._start_adb_install)
        self.retry_btn.hide()
        row1 = QHBoxLayout()
        row1.addWidget(self.dot1)
        row1.addWidget(self.title1)
        row1.addStretch(1)
        row1.addWidget(self.retry_btn)
        card_layout.addLayout(row1)
        card_layout.addWidget(self.step1)
        card_layout.addWidget(self.progress1)

        # --- шаг 2
        self.dot2 = StatusDot()
        self.title2 = QLabel("Шаг 2 — подключите телефон к компьютеру")
        self.title2.setObjectName("SectionTitle")
        self.step2 = StepLabel(
            "Кабелем USB к ПК. На телефоне выберите «Передача файлов» (MTP) — так надёжнее."
        )
        row2 = QHBoxLayout()
        row2.addWidget(self.dot2)
        row2.addWidget(self.title2)
        row2.addStretch(1)
        card_layout.addLayout(row2)
        card_layout.addWidget(self.step2)

        # --- шаг 3
        self.dot3 = StatusDot()
        self.title3 = QLabel("Шаг 3 — включите отладку по USB")
        self.title3.setObjectName("SectionTitle")
        self.step3 = StepLabel(
            "Настройки → О телефоне → 7 раз нажмите «Номер сборки» → "
            "Настройки → Для разработчиков → «Отладка по USB»."
        )
        self.step3.setWordWrap(True)
        row3 = QHBoxLayout()
        row3.addWidget(self.dot3)
        row3.addWidget(self.title3)
        row3.addStretch(1)
        self.open_settings_btn = QPushButton("Открыть настройки разработчика")
        self.open_settings_btn.clicked.connect(self._open_dev_settings)
        self.open_settings_btn.setEnabled(False)
        row3.addWidget(self.open_settings_btn)
        card_layout.addLayout(row3)
        card_layout.addWidget(self.step3)

        self.auth_hint = QLabel("")
        self.auth_hint.setObjectName("Hint")
        self.auth_hint.setAlignment(Qt.AlignCenter)
        self.auth_hint.setWordWrap(True)
        card_layout.addWidget(self.auth_hint)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.devices_label = QLabel("Ищу устройства…")
        self.devices_label.setObjectName("Muted")
        bottom.addWidget(self.devices_label)
        bottom.addStretch(1)
        card_layout.addLayout(bottom)

        footer = QHBoxLayout()
        self.skip_btn = QPushButton("Продолжить без телефона")
        self.skip_btn.clicked.connect(self.finished.emit)
        footer.addStretch(1)
        footer.addWidget(self.skip_btn)
        root.addLayout(footer)

    # ------------------------------------------------------------------ step 1
    def _start_adb_install(self) -> None:
        self.retry_btn.hide()
        self.progress1.setVisible(True)
        self.progress1.setValue(0)
        self.step1.setText("Скачиваю последний релиз ADB с GitHub…")
        self.dot1.set_color(ACCENT)

        task = Task(self._install_adb_task, parent=self)
        task.progress.connect(self._adb_progress)
        task.succeeded.connect(self._adb_ready)
        task.failed.connect(self._adb_failed)
        keep = getattr(self, "_tasks", None)
        if keep is None:
            keep = []
            self._tasks = keep
        keep.append(task)
        task.finished.connect(lambda: keep.remove(task) if task in keep else None)
        task.start()

    def _install_adb_task(self, task: Task) -> object:
        return install_latest_adb(cb=lambda message, value: task.emit_progress(message, value))

    def _adb_progress(self, message: str, value: float) -> None:
        self.step1.setText(message)
        if value >= 0:
            self.progress1.setValue(int(value * 100))

    def _adb_ready(self, path) -> None:
        self.adb_path = path
        version = adb_version(path)
        self.progress1.setValue(100)
        self.progress1.hide()
        self.step1.setText(f"ADB установлен: {version}\n{platform_tools_dir()}")
        self.dot1.set_color(OK)
        self.dot2.set_color(ACCENT)
        self.step3.setText(
            "Ждём телефон. Если он уже подключён — включите «Отладку по USB» в настройках разработчика."
        )
        self.open_settings_btn.setEnabled(False)
        self._start_monitoring()

    def _adb_failed(self, message: str) -> None:
        self.dot1.set_color(DANGER)
        self.step1.setText(message)
        self.retry_btn.show()
        self.progress1.hide()

    # ------------------------------------------------------------------ step 2/3
    def _start_monitoring(self) -> None:
        if self._monitoring:
            return
        self._monitoring = True
        self._poll()

    def _poll(self) -> None:
        if not self._monitoring or not self.adb_path:
            return
        adb_path = self.adb_path

        def job():
            adb = Adb(adb_path=adb_path, serial="")
            return adb.list_devices()

        def done(devices: list[DeviceEntry]) -> None:
            self._handle_devices(devices)
            if self._monitoring:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(2000, self._poll)

        def failed(message: str) -> None:
            self.devices_label.setText(f"ADB: {message}")
            if self._monitoring:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(3000, self._poll)

        run_task(self, job, done, failed)

    def _handle_devices(self, devices: list[DeviceEntry]) -> None:
        if not devices:
            self.dot2.set_color(MUTED)
            self.dot3.set_color(MUTED)
            self.devices_label.setText("Устройства не найдены — подключите кабель USB")
            self.auth_hint.setText("")
            self.open_settings_btn.setEnabled(False)
            return

        device = devices[0]
        self.open_settings_btn.setEnabled(True)

        if device.state == "unauthorized":
            self.dot2.set_color(OK)
            self.dot3.set_color(DANGER)
            self.devices_label.setText(f"Найден телефон: {device.serial}")
            self.step3.setText(
                "Телефон подключён, но не авторизован.\n"
                "Разблокируйте экран и нажмите «Разрешить» в окне "
                "«Разрешить отладку по USB?» (поставьте галочку «Всегда разрешать»)."
            )
            self.auth_hint.setText("Если окно не появляется: отключите и снова подключите кабель.")
            return

        if device.state == "offline":
            self.devices_label.setText(f"Телефон {device.serial} в состоянии offline")
            self.auth_hint.setText("Попробуйте переподключить кабель или перезапустить ADB.")
            return

        if not device.is_ready:
            self.devices_label.setText(f"{device.serial}: {device.state}")
            return

        # всё готово
        self.dot2.set_color(OK)
        self.dot3.set_color(OK)
        self.auth_hint.setText("")
        self.open_settings_btn.setEnabled(True)
        model = device.model or device.serial
        self.devices_label.setText(f"✅ {model} — отладка включена")
        self.step3.setText("Отладка по USB включена и разрешена. Открываю меню очистки…")
        self._monitoring = False
        serial = device.serial
        from PySide6.QtCore import QTimer
        QTimer.singleShot(800, lambda: self.ready.emit(serial))

    def stop(self) -> None:
        """Останавливает опрос устройств и ждёт активные задачи."""
        self._monitoring = False
        for task in list(getattr(self, "_tasks", [])):
            if task.isRunning():
                task.wait(4000)

    def _open_dev_settings(self) -> None:
        """Пробуем открыть настройки разработчика на телефоне."""
        if not self.adb_path:
            return
        try:
            adb = Adb(adb_path=self.adb_path, serial=None)
            devices = [d for d in adb.list_devices() if d.is_ready]
            if devices:
                adb.serial = devices[0].serial
            for action in ("android.settings.APPLICATION_DEVELOPMENT_SETTINGS",
                           "android.settings.SETTINGS"):
                result = adb.shell(f"am start -a {action}")
                if "Error" not in result.output:
                    break
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(self, "Не удалось", f"Не получается открыть настройки: {exc}")
