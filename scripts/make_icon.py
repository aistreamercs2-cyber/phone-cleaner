"""Рисует иконку приложения (PNG + ICO) без внешних зависимостей."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
)

SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw_icon(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)

    scale = size / 256
    # фон: скруглённый квадрат с градиентом
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#2f6fdb"))
    gradient.setColorAt(1.0, QColor("#12203a"))
    painter.setBrush(gradient)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(QRectF(6 * scale, 6 * scale, 244 * scale, 244 * scale), 56 * scale, 56 * scale)

    # телефон
    phone = QPainterPath()
    phone.addRoundedRect(QRectF(84 * scale, 44 * scale, 88 * scale, 168 * scale), 20 * scale, 20 * scale)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor("#ffffff"), max(2.0, 12 * scale)))
    painter.drawPath(phone)
    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(QRectF(112 * scale, 62 * scale, 34 * scale, 8 * scale), 4 * scale, 4 * scale)

    # «чистка»: галочка/блеск
    painter.setPen(QPen(QColor("#3ddc84"), max(2.0, 14 * scale), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    check = QPainterPath(QPointF(108 * scale, 132 * scale))
    check.lineTo(124 * scale, 148 * scale)
    check.lineTo(152 * scale, 112 * scale)
    painter.drawPath(check)

    # блик-искра в углу
    painter.setPen(QPen(QColor("#8fd0ff"), max(1.0, 7 * scale), Qt.SolidLine, Qt.RoundCap))
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        painter.drawLine(
            QPointF((196 + dx * 16) * scale, (188 + dy * 16) * scale),
            QPointF((196 + dx * 26) * scale, (188 + dy * 26) * scale),
        )
    painter.end()
    return image


def build_ico(images: dict[int, QImage], destination: Path) -> None:
    """Собирает .ico из PNG-кадров (формат PNG внутри ICO поддерживается с Vista)."""
    pngs: list[tuple[int, bytes]] = []
    for size in sorted(images):
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        buffer = QByteArray()
        device = QBuffer(buffer)
        device.open(QIODevice.WriteOnly)
        images[size].save(device, "PNG")
        device.close()
        pngs.append((size, bytes(buffer.data())))

    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries = b""
    payload = b""
    for size, data in pngs:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)
    destination.write_bytes(header + entries + payload)


def main() -> int:
    app = QGuiApplication(sys.argv[:1])  # noqa: F841 - нужен для QImage/шрифтов
    out_dir = Path(__file__).resolve().parent.parent / "phone_cleaner" / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)

    images = {size: draw_icon(size) for size in SIZES}
    images[256].save(str(out_dir / "icon.png"), "PNG")
    build_ico(images, out_dir / "icon.ico")
    print(f"Иконки сохранены в {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
