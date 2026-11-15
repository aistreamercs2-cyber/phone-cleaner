"""Главное окно: мастер подключения + меню очистки."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
    QTabWidget, QVBoxLayout, QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..adb import Adb
from ..adb_installer import adb_version
from ..paths import find_adb, platform_tools_dir
from .onboarding import OnboardingWidget
from .tabs.apps_tab import AppsTab
from .tabs.control_tab import ControlTab
from .tabs.files_tab import FilesTab
from .tabs.info_tab import InfoTab
from .theme import ACCENT, DANGER, MUTED, OK, StatusDot
from .worker import run_task


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1200, 820)
        self.setMinimumSize(980, 680)
        self.serial: str | None = None
        self._monitor_timer = QTimer(self)
        self._monitor_timer.setInterval(4000)
        self._monitor_timer.timeout.connect(self._check_device)
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.onboarding = OnboardingWidget()
        self.onboarding.ready.connect(self.on_device_ready)
        self.onboarding.finished.connect(self.show_main)
        self.stack.addWidget(self.onboarding)

        self.main_page = self._build_main_page()
        self.stack.addWidget(self.main_page)

        self._build_menu()
        self.statusBar().showMessage("Готово")

    def _build_main_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.dot = StatusDot()
        top.addWidget(self.dot)
        self.device_label = QLabel("Телефон не подключён")
        self.device_label.setObjectName("SectionTitle")
        top.addWidget(self.device_label)

        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(260)
        self.device_combo.currentIndexChanged.connect(self._choose_serial)
        top.addWidget(self.device_combo)

        top.addStretch(1)
        self.version_label = QLabel("")
        self.version_label.setObjectName("Hint")
        top.addWidget(self.version_label)

        rescan_btn = QPushButton("Найти телефон")
        rescan_btn.clicked.connect(self._check_device)
        top.addWidget(rescan_btn)

        adb_btn = QPushButton("⚙️ ADB")
        adb_btn.clicked.connect(self._toggle_adb_menu_placeholder)
        top.addWidget(adb_btn)
        layout.addLayout(top)

        self.tabs = QTabWidget()
        self.info_tab = InfoTab()
        self.apps_tab = AppsTab()
        self.files_tab = FilesTab()
        self.control_tab = ControlTab()
        self.tabs.addTab(self.apps_tab, "🧹 Приложения")
        self.tabs.addTab(self.files_tab, "🗂 Файлы")
        self.tabs.addTab(self.control_tab, "🎛 Управление")
        self.tabs.addTab(self.info_tab, "📱 Телефон")
        layout.addWidget(self.tabs, 1)

        for tab in (self.info_tab, self.apps_tab, self.files_tab, self.control_tab):
            tab.status.connect(self.statusBar().showMessage)

        self._update_adb_label()
        self._monitor_timer.start()
        return page

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("Файл")
        back_action = QAction("⟵ Вернуться к мастеру подключения", self)
        back_action.triggered.connect(lambda: self.stack.setCurrentWidget(self.onboarding))
        file_menu.addAction(back_action)
        file_menu.addSeparator()
        quit_action = QAction("Выход", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        adb_menu = bar.addMenu("ADB")
        restart_action = QAction("Перезапустить ADB-сервер", self)
        restart_action.triggered.connect(self._restart_adb)
        adb_menu.addAction(restart_action)
        update_action = QAction("Переустановить ADB (последний релиз)", self)
        update_action.triggered.connect(self._reinstall_adb)
        adb_menu.addAction(update_action)
        folder_action = QAction("Открыть папку ADB", self)
        folder_action.triggered.connect(self._open_adb_folder)
        adb_menu.addAction(folder_action)

        help_menu = bar.addMenu("Справка")
        about_action = QAction("О программе", self)
        about_action.triggered.connect(self._about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------ device
    def on_device_ready(self, serial: str) -> None:
        self.serial = serial
        self.show_main()
        self._check_device()

    def show_main(self) -> None:
        self.stack.setCurrentWidget(self.main_page)
        self._check_device()

    def _choose_serial(self, index: int) -> None:
        data = self.device_combo.itemData(index)
        if data:
            self.serial = str(data)
            self._apply_serial()

    def _apply_serial(self) -> None:
        for tab in (self.info_tab, self.apps_tab, self.files_tab, self.control_tab):
            tab.set_serial(self.serial)

    def _check_device(self) -> None:
        adb_path = find_adb()
        if not adb_path:
            self.dot.set_color(MUTED)
            self.device_label.setText("ADB не установлен")
            return

        def job():
            adb = Adb(adb_path=adb_path, serial="")
            return adb.list_devices()

        def done(devices) -> None:
            ready = [d for d in devices if d.is_ready]
            current = self.device_combo.currentData()
            self.device_combo.blockSignals(True)
            self.device_combo.clear()
            for device in devices:
                label = device.title
                if device.state == "unauthorized":
                    label += " — разрешите отладку"
                self.device_combo.addItem(label, device.serial)
            self.device_combo.blockSignals(False)

            if ready:
                self.dot.set_color(OK)
                chosen = ready[0].serial
                for device in ready:
                    if device.serial == current:
                        chosen = device.serial
                if self.serial != chosen:
                    self.serial = chosen
                index = self.device_combo.findData(chosen)
                if index >= 0:
                    self.device_combo.setCurrentIndex(index)
                self.device_label.setText(ready[0].title if len(ready) == 1 else f"Подключено: {len(ready)}")
                self._apply_serial()
            elif devices:
                self.dot.set_color(DANGER if any(d.state == "unauthorized" for d in devices) else MUTED)
                self.device_label.setText("Телефон не авторизован — разрешите отладку по USB")
            else:
                self.dot.set_color(MUTED)
                self.device_label.setText("Телефон не подключён")
                self.serial = None

        run_task(self, job, done, lambda m: self.statusBar().showMessage(f"ADB: {m}"))

    # ------------------------------------------------------------------ ADB tools
    def _update_adb_label(self) -> None:
        path = find_adb()
        if path:
            self.version_label.setText(f"ADB: {adb_version(path)}")
        else:
            self.version_label.setText("ADB не установлен")

    def _restart_adb(self) -> None:
        def job():
            adb = Adb(serial="")
            adb.kill_server()
            adb.server_start()
            return True

        run_task(self, job, lambda _: (self.statusBar().showMessage("ADB-сервер перезапущен"), self._check_device()),
                 lambda m: QMessageBox.critical(self, "Ошибка ADB", m))

    def _reinstall_adb(self) -> None:
        from ..adb_installer import install_latest_adb
        from .onboarding import OnboardingWidget  # noqa: F401 - для совместимости импорта

        self.statusBar().showMessage("Скачиваю последний ADB с GitHub…")

        def job():
            return install_latest_adb(force=True)

        def done(path):
            self._update_adb_label()
            QMessageBox.information(self, "Готово", f"ADB обновлён:\n{path}\n\n{adb_version(path)}")

        run_task(self, job, done, lambda m: QMessageBox.critical(self, "Не удалось", m))

    def _open_adb_folder(self) -> None:
        import os
        import subprocess
        import sys
        folder = platform_tools_dir()
        try:
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            QMessageBox.information(self, "Папка ADB", f"{folder}\n\n({exc})")

    def _toggle_adb_menu_placeholder(self) -> None:
        path = find_adb()
        text = f"ADB: {adb_version(path)}\nПуть: {path}\nПапка: {platform_tools_dir()}" if path else "ADB не установлен"
        QMessageBox.information(self, "ADB", text)

    def _about(self) -> None:
        QMessageBox.about(
            self, "О программе",
            f"<h3>{APP_NAME} {APP_VERSION}</h3>"
            "<p>Чистка и управление Android-телефоном через ADB.</p>"
            "<p>ADB скачивается автоматически с GitHub (последний релиз) при первом запуске.</p>"
            "<p><b>Важно:</b> удаление системных приложений делается в режиме "
            "«для владельца» — это обратимо и не ломает систему.</p>",
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        self._monitor_timer.stop()
        self.onboarding.stop()
        for tab in (self.info_tab, self.apps_tab, self.files_tab, self.control_tab):
            for task in list(getattr(tab, "_running_tasks", [])):
                if task.isRunning():
                    task.wait(3000)
        super().closeEvent(event)
