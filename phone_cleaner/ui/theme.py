"""Тёмная тема и вспомогательные виджеты."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

ACCENT = "#4c9aff"
BG = "#12141a"
PANEL = "#1b1e26"
PANEL_2 = "#232733"
TEXT = "#e6e9ef"
MUTED = "#9aa3b2"
DANGER = "#ef5350"
OK = "#3ddc84"

STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QCheckBox {{ background: transparent; }}
QFrame#Panel, QWidget#Panel {{
    background: {PANEL};
    border: 1px solid #2b3040;
    border-radius: 12px;
}}
QLabel#Title {{ font-size: 26px; font-weight: 700; }}
QLabel#Subtitle {{ color: {MUTED}; font-size: 14px; }}
QLabel#SectionTitle {{ font-size: 16px; font-weight: 600; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#Hint {{ color: {MUTED}; font-size: 12px; }}
QPushButton {{
    background: {PANEL_2};
    border: 1px solid #333a4b;
    border-radius: 9px;
    padding: 8px 16px;
    min-height: 20px;
}}
QPushButton:hover {{ background: #2b3140; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: #20242f; }}
QPushButton:disabled {{ color: #6b7280; border-color: #262b38; background: #191d25; }}
QPushButton#Primary {{
    background: {ACCENT};
    border: none;
    color: #0b1220;
    font-weight: 700;
}}
QPushButton#Primary:hover {{ background: #6bb0ff; }}
QPushButton#Danger {{ background: #3a1f24; border-color: #6d2b31; color: #ffb4b4; }}
QPushButton#Danger:hover {{ background: #4a252b; border-color: {DANGER}; }}
QTabWidget::pane {{ border: 1px solid #2b3040; border-radius: 12px; background: {PANEL}; top: -1px; }}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 10px 18px;
    margin-right: 4px;
    border-radius: 8px;
}}
QTabBar::tab:selected {{ background: {PANEL}; color: {TEXT}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {{
    background: #141822;
    border: 1px solid #2b3040;
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {ACCENT};
    selection-color: #08111f;
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {PANEL_2}; selection-background-color: {ACCENT}; }}
QTableWidget, QTreeWidget, QListWidget {{
    background: #141822;
    alternate-background-color: #171b25;
    border: 1px solid #2b3040;
    border-radius: 10px;
    gridline-color: #232836;
}}
QTableWidget::item:selected, QTreeWidget::item:selected {{ background: #24344d; color: {TEXT}; }}
QHeaderView::section {{
    background: {PANEL_2};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid #2b3040;
    padding: 8px;
    font-weight: 600;
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator, QTableWidget::indicator {{
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid #3a4152;
    background: #141822;
}}
QCheckBox::indicator:checked, QTableWidget::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QProgressBar {{
    background: #141822;
    border: 1px solid #2b3040;
    border-radius: 7px;
    height: 14px;
    text-align: center;
    font-size: 11px;
    color: {MUTED};
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #333a4b; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #46506a; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #333a4b; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; }}
QToolTip {{ background: {PANEL_2}; color: {TEXT}; border: 1px solid #3a4152; padding: 6px; border-radius: 6px; }}
QGroupBox {{
    border: 1px solid #2b3040;
    border-radius: 10px;
    margin-top: 18px;
    padding-top: 10px;
    font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {MUTED}; }}
QMenu {{ background: {PANEL_2}; border: 1px solid #3a4152; padding: 6px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; color: #08111f; }}
"""


def apply_theme(app) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor("#141822"))
    palette.setColor(QPalette.AlternateBase, QColor("#171b25"))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(PANEL_2))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor("#08111f"))
    palette.setColor(QPalette.ToolTipBase, QColor(PANEL_2))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)


class StepLabel(QLabel):
    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setObjectName("Muted")
        self.setAlignment(Qt.AlignCenter)


class StatusDot(QLabel):
    """Цветная точка-индикатор состояния."""

    def __init__(self) -> None:
        super().__init__("●")
        self.set_color(MUTED)
        font = QFont()
        font.setPointSize(font.pointSize() + 8)
        self.setFont(font)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(f"color: {color}; background: transparent;")


class Card(QWidget):
    def __init__(self, title: str, value: str = "—") -> None:
        super().__init__()
        self.setObjectName("Panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)
        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("Hint")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("SectionTitle")
        self.value_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class StorageBar(QWidget):
    """Полоса заполненности хранилища."""

    def __init__(self) -> None:
        super().__init__()
        from PySide6.QtWidgets import QHBoxLayout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.caption = QLabel("—")
        self.caption.setObjectName("Hint")
        row = QHBoxLayout()
        row.addWidget(self.bar, 1)
        layout.addLayout(row)
        layout.addWidget(self.caption)

    def set_usage(self, percent: int, caption: str, danger: bool = False) -> None:
        self.bar.setValue(max(0, min(100, percent)))
        color = DANGER if danger or percent >= 90 else ACCENT
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: #141822; border: 1px solid #2b3040; border-radius: 5px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 5px; }}"
        )
        self.caption.setText(caption)
