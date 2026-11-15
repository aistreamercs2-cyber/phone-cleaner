"""Вкладка «Управление»: кнопки-команды и консоль ADB."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ...adb import Adb, CommandRunner, parse_shell_command
from ...paths import temp_dir
from ..worker import run_task

QUICK_COMMANDS = [
    ("📶 Wi-Fi", "svc wifi {v}"),
    ("📡 Данные", "svc data {v}"),
    ("✈️ Авиарежим", "cmd connectivity airplane-mode {v}"),
    ("🔇 Без звука", "cmd audio set-stream-volume 3 0"),
    ("🔊 Звук 50%", "cmd audio set-stream-volume 3 50"),
    ("💡 Фонарик", "cmd flashlight {v}"),
    ("🌙 Тёмная тема", "cmd uimode night {v2}"),
    ("🔒 Блокировка", "input keyevent 26"),
    ("📷 Камера", "am start -a android.media.action.STILL_IMAGE_CAMERA"),
    ("🌐 Браузер", "am start -a android.intent.action.VIEW -d https://google.com"),
    ("⚙️ Настройки", "am start -a android.settings.SETTINGS"),
    ("📱 Батарея", "am start -a android.intent.action.POWER_USAGE_SUMMARY"),
    ("🗂 Все приложения", "am start -a android.settings.APPLICATION_SETTINGS"),
    ("🔄 Перезагрузка", "__reboot"),
    ("🛑 Recovery", "__reboot recovery"),
    ("🚀 Bootloader", "__reboot bootloader"),
]

SQLITE_SAFE_HELP = (
    "Можно вводить команды как с префиксом adb (shell ls /sdcard), так и просто "
    "shell-команды Android (pm list packages, dumpsys battery, input keyevent 3)."
)


class ControlTab(QWidget):
    status = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.serial: str | None = None
        self._runner: CommandRunner | None = None
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Управление телефоном")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.screenshot_btn = QPushButton("📸 Скриншот")
        self.screenshot_btn.clicked.connect(self._screenshot)
        header.addWidget(self.screenshot_btn)
        self.record_btn = QPushButton("🎥 Запись экрана 15 с")
        self.record_btn.clicked.connect(self._record)
        header.addWidget(self.record_btn)
        self.wake_btn = QPushButton("🔆 Разбудить")
        self.wake_btn.clicked.connect(lambda: self._simple("input keyevent 224"))
        header.addWidget(self.wake_btn)
        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setSpacing(8)
        for index, (label, command) in enumerate(QUICK_COMMANDS):
            button = QPushButton(label)
            button.setToolTip(command)
            button.clicked.connect(lambda _=False, c=command, l=label: self._quick(l, c))
            grid.addWidget(button, index // 4, index % 4)
        scroll.setWidget(holder)
        scroll.setFixedHeight(190)
        root.addWidget(scroll)

        console_box = QGroupBox("Консоль ADB")
        console_layout = QVBoxLayout(console_box)

        row = QHBoxLayout()
        self.history = QComboBox()
        self.history.setEditable(True)
        self.history.setInsertPolicy(QComboBox.NoInsert)
        self.history.lineEdit().setPlaceholderText(
            "adb-команда, например: pm list packages -3   |   dumpsys battery   |   input keyevent 3"
        )
        self.history.lineEdit().returnPressed.connect(self._run_console)
        row.addWidget(self.history, 1)

        run_btn = QPushButton("Выполнить")
        run_btn.setObjectName("Primary")
        run_btn.clicked.connect(self._run_console)
        row.addWidget(run_btn)

        self.stop_btn = QPushButton("Стоп")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        row.addWidget(self.stop_btn)
        console_layout.addLayout(row)

        presets = QHBoxLayout()
        for label, command in (
            ("Список пакетов", "pm list packages"),
            ("Батарея", "dumpsys battery"),
            ("Память", "df -h"),
            ("Модель", "getprop ro.product.model"),
            ("Экран", "wm size"),
            ("Android", "getprop ro.build.version.release"),
        ):
            preset = QPushButton(label)
            preset.setToolTip(command)
            preset.clicked.connect(lambda _=False, c=command: (self.history.setEditText(c), self._run_console()))
            presets.addWidget(preset)
        presets.addStretch(1)
        console_layout.addLayout(presets)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(5000)
        self.console.setPlaceholderText("Здесь появится вывод команд…")
        console_layout.addWidget(self.console, 1)

        bottom = QHBoxLayout()
        clear_btn = QPushButton("Очистить вывод")
        clear_btn.clicked.connect(self.console.clear)
        bottom.addWidget(clear_btn)
        hint = QLabel(SQLITE_SAFE_HELP)
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        bottom.addWidget(hint, 1)
        console_layout.addLayout(bottom)

        root.addWidget(console_box, 1)

        install_row = QHBoxLayout()
        install_btn = QPushButton("📦 Установить APK")
        install_btn.clicked.connect(self._install_apk)
        install_row.addWidget(install_btn)
        logcat_btn = QPushButton("📜 Логи (logcat 200 строк)")
        logcat_btn.clicked.connect(lambda: (self.history.setEditText("logcat -d -t 200"), self._run_console()))
        install_row.addWidget(logcat_btn)
        install_row.addStretch(1)
        root.addLayout(install_row)

    # ------------------------------------------------------------------ helpers
    def set_serial(self, serial: str | None) -> None:
        self.serial = serial

    def _append(self, text: str) -> None:
        self.console.appendPlainText(text)

    def _quick(self, label: str, command: str) -> None:
        if not self.serial:
            QMessageBox.warning(self, "Нет телефона", "Сначала подключите телефон.")
            return
        if command == "__reboot" or command.startswith("__reboot "):
            mode = command.replace("__reboot", "").strip()
            if QMessageBox.question(self, "Перезагрузка",
                                    f"Перезагрузить телефон{' в ' + mode if mode else ''}?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            serial = self.serial
            run_task(self, lambda: Adb(serial=serial).reboot(mode), lambda _: self.status.emit("Команда отправлена"),
                     lambda m: QMessageBox.critical(self, "Ошибка", m))
            return

        serial = self.serial
        resolved = self._resolve_toggle(command)
        self._execute_console(resolved)

    def _resolve_toggle(self, command: str) -> str:
        if "{v}" in command:
            current = self._query_state(command)
            value = "disable" if current else "enable"
            command = command.replace("{v}", value)
        if "{v2}" in command:
            command = command.replace("{v2}", "yes")
        return command

    def _query_state(self, command: str) -> bool:
        try:
            adb = Adb(serial=self.serial)
            if command.startswith("svc wifi"):
                out = adb.shell("dumpsys wifi | head -30").stdout
                return "Wi-Fi is enabled" in out or "Wi-Fi enabled" in out
            if command.startswith("svc data"):
                out = adb.shell("dumpsys telephony.registry | grep -i dataConnectionState").stdout
                return "2" in out
            if "airplane" in command:
                out = adb.shell("settings get global airplane_mode_on").stdout
                return out.strip() == "1"
            if "flashlight" in command:
                return False
        except (OSError, RuntimeError):
            return False
        return False

    def _run_console(self) -> None:
        text = self.history.currentText().strip()
        if not text:
            return
        self._execute_console(text)

    def _execute_console(self, text: str) -> None:
        if not self.serial:
            QMessageBox.warning(self, "Нет телефона", "Сначала подключите телефон.")
            return
        if self._runner and self._runner.running:
            QMessageBox.information(self, "Подождите", "Предыдущая команда ещё выполняется.")
            return
        self.history.setEditText(text)
        if self.history.findText(text) < 0:
            self.history.addItem(text)
        args = parse_shell_command(text)
        if not args:
            return
        self._append(f"$ adb {' '.join(args)}")
        self.status.emit("Выполняю…")
        self.stop_btn.setEnabled(True)
        self._runner = CommandRunner(
            Adb(serial=self.serial),
            self._append,
            lambda code: (self._append(f"— завершено, код {code}\n"), self.stop_btn.setEnabled(False),
                          self.status.emit("Готово")),
        )
        self._runner.start(args)

    def _stop(self) -> None:
        if self._runner:
            self._runner.stop()
            self._append("— остановлено пользователем\n")
        self.stop_btn.setEnabled(False)

    # ------------------------------------------------------------------ extras
    def _simple(self, command: str) -> None:
        self._execute_console(command)

    def _screenshot(self) -> None:
        if not self.serial:
            return
        serial = self.serial
        self.status.emit("Делаю скриншот…")

        def job():
            path = temp_dir() / "screenshot.png"
            return Adb(serial=serial).screenshot(path)

        def done(path: Path) -> None:
            self._append(f"Скриншот сохранён: {path}")
            self.status.emit(f"Скриншот: {path}")
            QMessageBox.information(self, "Готово", f"Скриншот сохранён:\n{path}")

        run_task(self, job, done, lambda m: QMessageBox.critical(self, "Ошибка", m))

    def _record(self) -> None:
        if not self.serial:
            return
        local = temp_dir() / "screen.mp4"
        serial = self.serial
        self._append("$ adb shell screenrecord --time-limit 15 …")
        self.status.emit("Записываю экран 15 секунд…")

        def job():
            adb = Adb(serial=serial)
            adb.shell("screenrecord --time-limit 15 /sdcard/pc_record.mp4", timeout=60)
            return adb.pull_file("/sdcard/pc_record.mp4", local).code

        def done(code: int) -> None:
            if code == 0:
                self._append(f"Видео сохранено: {local}")
                QMessageBox.information(self, "Готово", f"Видео сохранено:\n{local}")
            else:
                QMessageBox.warning(self, "Не удалось", "Телефон не отдал запись экрана.")

        run_task(self, job, done, lambda m: QMessageBox.critical(self, "Ошибка", m))

    def _install_apk(self) -> None:
        if not self.serial:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Выберите APK", "", "Android package (*.apk)")
        if not path:
            return
        serial = self.serial
        self._append(f"$ adb install -r {path}")
        self.status.emit("Устанавливаю APK…")

        def job():
            result = Adb(serial=serial).install_apk(path)
            return result.output

        def done(output: str) -> None:
            self._append(output)
            if "Success" in output:
                QMessageBox.information(self, "Готово", "APK установлен")
            else:
                QMessageBox.warning(self, "Не удалось", output[-800:])

        run_task(self, job, done, lambda m: QMessageBox.critical(self, "Ошибка", m))
