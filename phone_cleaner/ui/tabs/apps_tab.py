"""Вкладка «Приложения»: список, размеры, удаление, заморозка, восстановление."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ... import parsers
from ...adb import BLOATWARE_FLAT, PROTECTED_PACKAGES, Adb
from ...parsers import human_size
from ..worker import run_task


@dataclass
class AppRow:
    package: str
    path: str | None
    size: int
    data: int
    cache: int
    vendor: str

    @property
    def total(self) -> int:
        return self.size + self.data + self.cache


class AppsTab(QWidget):
    status = Signal(str)

    COLUMNS = ("", "Приложение", "Размер данных", "Кэш", "Метка", "Путь")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.serial: str | None = None
        self.rows: list[AppRow] = []
        self._build()
        self._settings = {}

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Приложения")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Поиск по названию пакета…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.filter_edit.setFixedWidth(260)
        header.addWidget(self.filter_edit)

        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["Все приложения", "Только сторонние", "Только системные", "Кандидаты на удаление"])
        self.scope_combo.currentIndexChanged.connect(self._apply_filter)
        header.addWidget(self.scope_combo)

        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)
        root.addLayout(header)

        hint = QLabel(
            "Отметьте приложения галочками. «Удалить для владельца» — безопасно: систему не ломает, "
            "приложение можно вернуть кнопкой «Восстановить». Полное удаление доступно только для "
            "сторонних приложений."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 36)
        header_view.setSectionResizeMode(1, QHeaderView.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.Interactive)
        header_view.setSectionResizeMode(3, QHeaderView.Interactive)
        header_view.setSectionResizeMode(4, QHeaderView.Interactive)
        header_view.setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 130)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.chk_all = QCheckBox("Выбрать всё")
        self.chk_all.toggled.connect(self._toggle_all)
        actions.addWidget(self.chk_all)

        self.bloat_btn = QPushButton("Отметить бloatware")
        self.bloat_btn.setToolTip("Отметить известные предустановленные приложения-кандидаты")
        self.bloat_btn.clicked.connect(self._mark_bloatware)
        actions.addWidget(self.bloat_btn)

        actions.addStretch(1)
        self.selection_label = QLabel("Выбрано: 0")
        self.selection_label.setObjectName("Muted")
        actions.addWidget(self.selection_label)
        root.addLayout(actions)

        buttons = QHBoxLayout()
        self.uninstall_btn = QPushButton("Удалить для владельца")
        self.uninstall_btn.setObjectName("Danger")
        self.uninstall_btn.clicked.connect(lambda: self._uninstall(for_user=True))
        buttons.addWidget(self.uninstall_btn)

        self.uninstall_full_btn = QPushButton("Удалить полностью")
        self.uninstall_full_btn.setObjectName("Danger")
        self.uninstall_full_btn.clicked.connect(lambda: self._uninstall(for_user=False))
        buttons.addWidget(self.uninstall_full_btn)

        self.freeze_btn = QPushButton("Отключить")
        self.freeze_btn.setToolTip("pm disable-user — приложение исчезает из лончера")
        self.freeze_btn.clicked.connect(lambda: self._freeze(True))
        buttons.addWidget(self.freeze_btn)

        self.enable_btn = QPushButton("Включить обратно")
        self.enable_btn.clicked.connect(lambda: self._freeze(False))
        buttons.addWidget(self.enable_btn)

        self.clear_btn = QPushButton("Очистить данные")
        self.clear_btn.clicked.connect(self._clear_data)
        buttons.addWidget(self.clear_btn)

        self.restore_btn = QPushButton("Восстановить удалённое…")
        self.restore_btn.clicked.connect(self._restore_dialog)
        buttons.addWidget(self.restore_btn)
        root.addLayout(buttons)

        self.table.itemChanged.connect(self._update_selection_label)

    # ------------------------------------------------------------------ data
    def set_serial(self, serial: str | None) -> None:
        self.serial = serial
        if serial:
            self.refresh()
        else:
            self.table.setRowCount(0)
            self.rows.clear()

    def refresh(self) -> None:
        if not self.serial:
            self.status.emit("Телефон не подключён")
            return
        self.refresh_btn.setEnabled(False)
        self.status.emit("Читаю список приложений…")
        serial = self.serial

        def job():
            adb = Adb(serial=serial)
            packages = adb.packages()
            sizes = adb.package_sizes()
            disabled = adb.shell("pm list packages -d").stdout
            disabled_names = {p for p, _ in parsers.parse_pm_list(disabled)}
            rows = []
            for name, path in packages:
                info = sizes.get(name)
                label = "системное" if path and any(
                    seg in path for seg in ("/system/", "/product/", "/vendor/", "/system_ext/", "/apex/")
                ) else "пользовательское"
                if name in PROTECTED_PACKAGES:
                    label = "защищено"
                elif name in disabled_names:
                    label = "отключено"
                vendor = BLOATWARE_FLAT.get(name, "")
                if vendor:
                    label = f"лишнее · {vendor}"
                rows.append(AppRow(
                    package=name,
                    path=path,
                    size=int((info or {}).get("app", 0)),
                    data=int((info or {}).get("data", 0)),
                    cache=int((info or {}).get("cache", 0)),
                    vendor=label,
                ))
            rows.sort(key=lambda r: r.total, reverse=True)
            return rows

        run_task(self, job, self._fill, self._error)

    def _fill(self, rows: list[AppRow]) -> None:
        self.refresh_btn.setEnabled(True)
        selected = {r.package for r in self.selected_rows()}
        self.rows = rows
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if row.package in PROTECTED_PACKAGES:
                check.setFlags(Qt.ItemIsEnabled)
                check.setToolTip("Защищённый системный пакет — удаление заблокировано")
                check.setCheckState(Qt.Unchecked)
            else:
                check.setCheckState(Qt.Checked if row.package in selected else Qt.Unchecked)
            self.table.setItem(index, 0, check)

            name_item = QTableWidgetItem(row.package)
            if row.package in PROTECTED_PACKAGES:
                name_item.setForeground(Qt.gray)
            self.table.setItem(index, 1, name_item)

            self._num_item(index, 2, human_size(row.data) if row.data else "—")
            self._num_item(index, 3, human_size(row.cache) if row.cache else "—")

            label_item = QTableWidgetItem(row.vendor or "—")
            if row.package in PROTECTED_PACKAGES:
                label_item.setForeground(Qt.gray)
            self.table.setItem(index, 4, label_item)
            self.table.setItem(index, 5, QTableWidgetItem(row.path or "—"))
        self.table.blockSignals(False)
        self.table.setSortingEnabled(True)
        self._apply_filter()
        self._update_selection_label()
        total = sum(r.total for r in rows)
        self.status.emit(f"Приложений: {len(rows)} · данных: {human_size(total)}")

    def _num_item(self, row: int, column: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, column, item)

    def _error(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.status.emit(f"Ошибка: {message}")

    def _apply_filter(self) -> None:
        text = self.filter_edit.text().strip().lower()
        scope = self.scope_combo.currentIndex()
        for row_index in range(self.table.rowCount()):
            name_item = self.table.item(row_index, 1)
            if name_item is None:
                continue
            package = name_item.text()
            label = (self.table.item(row_index, 4).text() if self.table.item(row_index, 4) else "")
            visible = not text or text in package.lower() or text in label.lower()
            if visible and scope == 1:
                visible = "пользовательское" in label or "лишнее" in label
            elif visible and scope == 2:
                visible = "системное" in label or "защищено" in label or "отключено" in label
            elif visible and scope == 3:
                visible = "лишнее" in label
            self.table.setRowHidden(row_index, not visible)

    # ------------------------------------------------------------------ selection
    def _toggle_all(self, checked: bool) -> None:
        self.table.blockSignals(True)
        for row_index in range(self.table.rowCount()):
            if self.table.isRowHidden(row_index):
                continue
            item = self.table.item(row_index, 0)
            if item and item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_selection_label()

    def selected_rows(self) -> list[AppRow]:
        chosen: list[AppRow] = []
        by_name = {r.package: r for r in self.rows}
        for row_index in range(self.table.rowCount()):
            item = self.table.item(row_index, 0)
            name_item = self.table.item(row_index, 1)
            if not item or not name_item:
                continue
            if item.checkState() == Qt.Checked:
                row = by_name.get(name_item.text())
                if row:
                    chosen.append(row)
        return chosen

    def _update_selection_label(self, *_: object) -> None:
        chosen = self.selected_rows()
        total = sum(r.total for r in chosen)
        self.selection_label.setText(f"Выбрано: {len(chosen)} · {human_size(total)}")

    def _mark_bloatware(self) -> None:
        self.scope_combo.setCurrentIndex(0)
        self.filter_edit.clear()
        self.table.blockSignals(True)
        for row_index in range(self.table.rowCount()):
            name_item = self.table.item(row_index, 1)
            item = self.table.item(row_index, 0)
            if not name_item or not item:
                continue
            label_item = self.table.item(row_index, 4)
            if label_item and "лишнее" in label_item.text() and item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(Qt.Checked)
        self.table.blockSignals(False)
        self._update_selection_label()

    # ------------------------------------------------------------------ actions
    def _guard(self, rows: list[AppRow]) -> list[str]:
        if not self.serial:
            QMessageBox.warning(self, "Нет телефона", "Сначала подключите телефон.")
            return []
        if not rows:
            QMessageBox.information(self, "Ничего не выбрано", "Отметьте приложения в списке.")
            return []
        return [r.package for r in rows]

    def _uninstall(self, for_user: bool) -> None:
        rows = self.selected_rows()
        packages = self._guard(rows)
        if not packages:
            return
        if not for_user:
            system = [r.package for r in rows if "системное" in r.vendor or "защищено" in r.vendor]
            if system:
                QMessageBox.critical(
                    self, "Нельзя удалить",
                    "Полное удаление системных пакетов заблокировано — это ломает систему.\n"
                    "Используйте «Удалить для владельца» или «Отключить».",
                )
                return
        names = "\n".join(f"• {p}" for p in packages[:20])
        if len(packages) > 20:
            names += f"\n… и ещё {len(packages) - 20}"
        mode = "для владельца (обратимо)" if for_user else "ПОЛНОСТЬЮ"
        answer = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить {mode} {len(packages)} прилож.?\n\n{names}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.status.emit("Удаляю…")
        serial = self.serial

        def job():
            return Adb(serial=serial).uninstall(packages, for_user=for_user)

        run_task(self, job, self._report_result, self._error)

    def _freeze(self, disable: bool) -> None:
        packages = self._guard(self.selected_rows())
        if not packages:
            return
        serial = self.serial
        self.status.emit("Отключаю…" if disable else "Включаю…")

        def job():
            return Adb(serial=serial).freeze(packages, disable=disable)

        run_task(self, job, self._report_result, self._error)

    def _clear_data(self) -> None:
        packages = self._guard(self.selected_rows())
        if not packages:
            return
        if QMessageBox.question(
            self, "Очистить данные",
            f"Удалить все данные и настройки у {len(packages)} прилож.?\n"
            "Приложение останется, но начнёт «с нуля».",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        serial = self.serial

        def job():
            return Adb(serial=serial).clear_data(packages)

        run_task(self, job, self._report_result, self._error)

    def _report_result(self, report: list[tuple[str, bool, str]]) -> None:
        good = [r for r in report if r[1]]
        bad = [r for r in report if not r[1]]
        self.status.emit(f"Готово: успешно {len(good)}, ошибок {len(bad)}")
        if bad:
            text = "\n".join(f"• {p}: {msg}" for p, _, msg in bad[:15])
            QMessageBox.warning(self, "Часть операций не удалась", text)
        self.refresh()

    def _restore_dialog(self) -> None:
        if not self.serial:
            QMessageBox.warning(self, "Нет телефона", "Сначала подключите телефон.")
            return
        package, ok = self._ask_package()
        if not ok or not package:
            return
        serial = self.serial
        self.status.emit(f"Восстанавливаю {package}…")

        def job():
            return Adb(serial=serial).restore(package)

        def done(result: tuple[bool, str]) -> None:
            success, message = result
            self.status.emit(message)
            if success:
                QMessageBox.information(self, "Готово", f"{package} восстановлено")
            else:
                QMessageBox.warning(self, "Не удалось", message)
            self.refresh()

        run_task(self, job, done, self._error)

    def _ask_package(self) -> tuple[str, bool]:
        from PySide6.QtWidgets import QInputDialog
        return QInputDialog.getText(
            self, "Восстановить приложение",
            "Имя пакета (например com.facebook.katana):",
        )
