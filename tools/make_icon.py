"""生成应用图标（assets/icon.ico），用 Qt 离屏渲染，无需额外依赖。

用法：python tools/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.qt import (QBuffer, QByteArray, QColor, QGuiApplication, QIODevice,  # noqa: E402
                    QImage, QLinearGradient, QPainter, QPainterPath, QPointF,
                    QPolygonF, QRectF, Qt)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    # 圆角底板 + 渐变
    pad = size * 0.045
    rect = QRectF(pad, pad, size - pad * 2, size - pad * 2)
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.235, size * 0.235)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, QColor("#3A4A7A"))
    grad.setColorAt(0.55, QColor("#232B44"))
    grad.setColorAt(1.0, QColor("#161B2A"))
    p.fillPath(path, grad)
    p.setPen(QColor(255, 255, 255, 30))
    p.drawPath(path)

    # 等距草方块
    s = size
    w, h = s * 0.245, s * 0.142
    cx, cy = s * 0.5, s * 0.5

    def poly(pts):
        return QPolygonF([QPointF(x, y) for x, y in pts])

    top = poly([(cx, cy - h * 1.62), (cx + w, cy - h * 0.56),
                (cx, cy + h * 0.5), (cx - w, cy - h * 0.56)])
    left = poly([(cx - w, cy - h * 0.56), (cx, cy + h * 0.5),
                 (cx, cy + h * 2.06), (cx - w, cy + h * 1.0)])
    right = poly([(cx + w, cy - h * 0.56), (cx, cy + h * 0.5),
                  (cx, cy + h * 2.06), (cx + w, cy + h * 1.0)])

    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#5FD97C"))
    p.drawPolygon(top)
    p.setBrush(QColor("#8B5A3C"))
    p.drawPolygon(left)
    p.setBrush(QColor("#6E452C"))
    p.drawPolygon(right)

    # 顶部高光
    p.setBrush(QColor(255, 255, 255, 46))
    p.drawPolygon(poly([(cx, cy - h * 1.62), (cx + w * 0.55, cy - h * 0.85),
                        (cx, cy - h * 0.2), (cx - w * 0.55, cy - h * 0.85)]))
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba.data())


def write_ico(path: Path, sizes: list[int]) -> None:
    images = [(s, png_bytes(render(s))) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b""
    data = b""
    for s, blob in images:
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        data += blob
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entries + data)


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841
    OUT.mkdir(parents=True, exist_ok=True)
    write_ico(OUT / "icon.ico", [16, 24, 32, 48, 64, 128, 256])
    render(256).save(str(OUT / "icon.png"), "PNG")
    print(f"已生成 {OUT / 'icon.ico'} 与 icon.png")


if __name__ == "__main__":
    main()
