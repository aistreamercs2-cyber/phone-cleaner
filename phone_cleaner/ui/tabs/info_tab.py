"""Вкладка «Телефон»: характеристики, батарея, хранилище, быстрые замеры."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from ...adb import Adb
from ...parsers import human_size
from ..theme import Card, StorageBar
from ..worker import run_task


class InfoTab(QWidget):
    status = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.serial: str | None = None
        self._cards: dict[str, Card] = {}
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Информация о телефоне")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)
        root.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(10)
        specs = [
            ("model", "Устройство"), ("brand", "Бренд"), ("android", "Android"), ("sdk", "API"),
            ("serial", "Серийный номер"), ("abi", "Архитектура"), ("battery", "Батарея"),
            ("temperature", "Температура"),
        ]
        for index, (key, label) in enumerate(specs):
            card = Card(label)
            self._cards[key] = card
            grid.addWidget(card, index // 4, index % 4)
        root.addLayout(grid)

        self.storage_bar = StorageBar()
        root.addWidget(self.storage_bar)

        table_title = QLabel("Разделы хранилища")
        table_title.setObjectName("SectionTitle")
        root.addWidget(table_title)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Точка монтирования", "Всего", "Занято", "Свободно", "Заполнено"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

    def set_serial(self, serial: str | None) -> None:
        self.serial = serial
        if serial:
            self.refresh()

    def refresh(self) -> None:
        if not self.serial:
            return
        serial = self.serial
        self.refresh_btn.setEnabled(False)
        self.status.emit("Читаю данные телефона…")

        def job():
            adb = Adb(serial=serial)
            return adb.device_info(), adb.storage()

        def done(payload) -> None:
            self.refresh_btn.setEnabled(True)
            info, storage = payload
            for key, card in self._cards.items():
                card.set_value(str(info.get(key, "—")))
            target = next((r for r in storage if r["mounted"] in ("/data", "/storage/emulated")), None)
            if target:
                try:
                    percent = int(target["use"].rstrip("%"))
                except ValueError:
                    percent = 0
                self.storage_bar.set_usage(
                    percent,
                    f"Занято {target['used']} из {target['size']} · свободно {target['avail']}",
                )
            self.table.setRowCount(len(storage))
            for row, item in enumerate(storage):
                values = [item["mounted"], item["size"], item["used"], item["avail"], item["use"]]
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(value))
            self.status.emit(f"{info.get('model', 'Телефон')} · Android {info.get('android', '?')}")

        run_task(self, job, done, lambda m: (self.refresh_btn.setEnabled(True), self.status.emit(f"Ошибка: {m}")))
