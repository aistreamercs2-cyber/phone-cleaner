"""Вкладка «Файлы»: обзор хранилища и удаление мусорных папок/кэшей."""

from __future__ import annotations

import posixpath

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...adb import Adb
from ...parsers import human_size
from ..theme import StorageBar
from ..worker import run_task

# Типичные места, где скапливается мусор на Android
JUNK_PATHS = {
    "Кэш приложений (Android/data/*/cache)": "/sdcard/Android/data/*/cache",
    "Кэш загрузок (Android/data/*/files/cache)": "/sdcard/Android/data/*/files/cache",
    "Telegram-кэш": "/sdcard/Android/data/org.telegram.messenger/cache",
    "WhatsApp-медиа": "/sdcard/WhatsApp/Media/WhatsApp Voice Notes",
    "Папка Download": "/sdcard/Download",
    "Папка DCIM/.thumbnails": "/sdcard/DCIM/.thumbnails",
    "Папка Movies": "/sdcard/Movies",
    "Папка Music": "/sdcard/Music",
    "Корзина (Trash)": "/sdcard/.trash",
}


class FilesTab(QWidget):
    status = Signal(str)

    COLUMNS = ("", "Папка", "Размер", "Тип")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.serial: str | None = None
        self.current_path = "/sdcard"
        self.entries: list[tuple[str, int]] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Хранилище и файлы")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)
        root.addLayout(header)

        self.storage_bar = StorageBar()
        root.addWidget(self.storage_bar)

        path_row = QHBoxLayout()
        self.quick_combo = QComboBox()
        self.quick_combo.addItems(list(JUNK_PATHS.keys()))
        self.quick_combo.addItem("Своя папка…")
        self.quick_combo.currentIndexChanged.connect(self._quick_jump)
        path_row.addWidget(self.quick_combo)

        self.path_edit = QLineEdit(self.current_path)
        self.path_edit.returnPressed.connect(self._navigate)
        path_row.addWidget(self.path_edit, 1)
        go_btn = QPushButton("Перейти")
        go_btn.clicked.connect(self._navigate)
        path_row.addWidget(go_btn)
        up_btn = QPushButton("↑ Вверх")
        up_btn.clicked.connect(self._go_up)
        path_row.addWidget(up_btn)
        root.addLayout(path_row)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 36)
        head.setSectionResizeMode(1, QHeaderView.Stretch)
        head.setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.setColumnWidth(2, 140)
        head.setSectionResizeMode(3, QHeaderView.Interactive)
        self.table.setColumnWidth(3, 160)
        self.table.doubleClicked.connect(lambda _: self._open_selected())
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        open_btn = QPushButton("Открыть папку")
        open_btn.clicked.connect(self._open_selected)
        buttons.addWidget(open_btn)

        self.delete_btn = QPushButton("Удалить выбранное")
        self.delete_btn.setObjectName("Danger")
        self.delete_btn.clicked.connect(self._delete_selected)
        buttons.addWidget(self.delete_btn)

        self.junk_btn = QPushButton("Найти мусор")
        self.junk_btn.clicked.connect(self._scan_junk)
        buttons.addWidget(self.junk_btn)

        clear_cache_btn = QPushButton("Очистить кэш всех приложений")
        clear_cache_btn.clicked.connect(self._trim_caches)
        buttons.addWidget(clear_cache_btn)
        buttons.addStretch(1)
        root.addLayout(buttons)

        self.hint = QLabel(
            "Совет: сначала удалите данные приложений на вкладке «Приложения» — это освобождает больше всего места."
        )
        self.hint.setObjectName("Hint")
        root.addWidget(self.hint)

    # ------------------------------------------------------------------ data
    def set_serial(self, serial: str | None) -> None:
        self.serial = serial
        if serial:
            self.refresh()
            self._navigate()

    def refresh(self) -> None:
        if not self.serial:
            return
        self.refresh_btn.setEnabled(False)
        serial = self.serial

        def job():
            adb = Adb(serial=serial)
            return adb.storage()

        def done(storage: list[dict[str, str]]) -> None:
            self.refresh_btn.setEnabled(True)
            target = None
            for row in storage:
                if row["mounted"] in ("/data", "/storage/emulated"):
                    target = row
                    break
            if not target and storage:
                target = storage[0]
            if not target:
                return
            percent = 0
            try:
                percent = int(target["use"].rstrip("%"))
            except ValueError:
                pass
            self.storage_bar.set_usage(
                percent,
                f"{target['mounted']}: занято {target['used']} из {target['size']} · свободно {target['avail']}",
            )
            self.status.emit(f"Свободно {target['avail']}")

        run_task(self, job, done, lambda m: self.status.emit(f"Ошибка: {m}"))

    def _navigate(self) -> None:
        if not self.serial:
            return
        path = self.path_edit.text().strip() or "/sdcard"
        self.current_path = path
        self.path_edit.setText(path)
        serial = self.serial
        self.status.emit(f"Читаю {path}…")

        def job():
            adb = Adb(serial=serial)
            quoted = path.replace(" ", "\\ ")
            result = adb.shell("ls -la " + quoted + " 2>/dev/null | tail -n +2")
            rows = []
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 7:
                    continue
                permissions, name = parts[0], " ".join(parts[7:])
                if name in (".", ".."):
                    continue
                rows.append((name, permissions))
            sizes = dict()
            du = adb.du(path)
            for item, size in du:
                key = posixpath.basename(item.rstrip("/"))
                sizes[key] = size
            return [(name, sizes.get(name, 0), perms) for name, perms in rows]

        run_task(self, job, self._fill, lambda m: self.status.emit(f"Ошибка: {m}"))

    def _fill(self, rows: list[tuple[str, int, str]]) -> None:
        self.entries = [(name, size) for name, size, _ in rows]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for index, (name, size, perms) in enumerate(rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check.setCheckState(Qt.Unchecked)
            self.table.setItem(index, 0, check)

            self.table.setItem(index, 1, QTableWidgetItem(name))
            size_item = QTableWidgetItem(human_size(size) if size else "—")
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(index, 2, size_item)
            kind = "папка" if perms.startswith("d") else "файл"
            self.table.setItem(index, 3, QTableWidgetItem(kind))
        self.table.setSortingEnabled(True)
        total = sum(size for _, size in self.entries)
        self.status.emit(f"{self.current_path}: {len(rows)} объектов · {human_size(total)}")

    def _quick_jump(self) -> None:
        index = self.quick_combo.currentIndex()
        keys = list(JUNK_PATHS)
        if index < 0:
            return
        if index >= len(keys):
            from PySide6.QtWidgets import QInputDialog
            text, ok = QInputDialog.getText(self, "Своя папка", "Путь на телефоне:", text=self.current_path)
            if ok and text.strip():
                self.path_edit.setText(text.strip())
                self._navigate()
            return
        self.path_edit.setText(JUNK_PATHS[keys[index]])
        self._navigate()

    def _go_up(self) -> None:
        parent = posixpath.dirname(self.current_path.rstrip("/")) or "/sdcard"
        self.path_edit.setText(parent)
        self._navigate()

    def _selected(self) -> list[str]:
        names: list[str] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if item and name_item and item.checkState() == Qt.Checked:
                names.append(posixpath.join(self.current_path, name_item.text()))
        return names

    def _open_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        name_item = self.table.item(row, 1)
        kind_item = self.table.item(row, 3)
        if not name_item or (kind_item and kind_item.text() != "папка"):
            return
        self.current_path = posixpath.join(self.current_path, name_item.text())
        self.path_edit.setText(self.current_path)
        self._navigate()

    def _delete_selected(self) -> None:
        paths = self._selected()
        if not paths:
            QMessageBox.information(self, "Ничего не выбрано", "Отметьте галочками папки или файлы.")
            return
        if QMessageBox.question(
            self, "Удалить безвозвратно",
            "Будут удалены:\n" + "\n".join(f"• {p}" for p in paths[:15]) +
            ("\n…" if len(paths) > 15 else ""),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        serial = self.serial

        def job():
            return Adb(serial=serial).delete_paths(paths)

        def done(report: list[tuple[str, bool, str]]) -> None:
            good = sum(1 for r in report if r[1])
            bad = [r for r in report if not r[1]]
            self.status.emit(f"Удалено {good}, ошибок {len(bad)}")
            if bad:
                QMessageBox.warning(self, "Ошибки",
                                    "\n".join(f"• {p}: {m}" for p, _, m in bad[:10]))
            self._navigate()
            self.refresh()

        run_task(self, job, done, lambda m: QMessageBox.critical(self, "Ошибка", m))

    def _scan_junk(self) -> None:
        if not self.serial:
            return
        serial = self.serial
        self.status.emit("Сканирую стандартные папки мусора…")

        def job():
            adb = Adb(serial=serial)
            found = []
            for label, path in JUNK_PATHS.items():
                rows = adb.du(path)
                if rows:
                    total = rows[-1][1]
                    if total > 0:
                        found.append((label, path, total))
            return found

        def done(found: list[tuple[str, str, int]]) -> None:
            if not found:
                QMessageBox.information(self, "Чисто", "Мусорных папок не найдено.")
                return
            found.sort(key=lambda r: r[2], reverse=True)
            total = sum(r[2] for r in found)
            text = "\n".join(f"• {human_size(size):>10}  {label}" for label, _, size in found)
            answer = QMessageBox.question(
                self, "Найден мусор",
                f"{text}\n\nВсего: {human_size(total)}\n\nОчистить найденные папки (кроме Download)?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            paths = [path for label, path, _ in found if "Download" not in path]
            adb = Adb(serial=serial)
            run_task(self, lambda: adb.delete_paths(paths), lambda report: (
                self.status.emit(f"Освобождено примерно {human_size(total)}"),
                self._navigate(), self.refresh(),
            ), lambda m: self.status.emit(f"Ошибка: {m}"))

        run_task(self, job, done, lambda m: self.status.emit(f"Ошибка: {m}"))

    def _trim_caches(self) -> None:
        if not self.serial:
            return
        if QMessageBox.question(
            self, "Очистить кэш",
            "Очистить кэш всех приложений? Данные и настройки сохранятся.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        serial = self.serial

        def job():
            adb = Adb(serial=serial)
            return adb.shell("pm trim-caches 999G", timeout=300).output

        run_task(self, job, lambda out: (self.status.emit("Кэш очищен"), self.refresh()),
                 lambda m: self.status.emit(f"Ошибка: {m}"))
