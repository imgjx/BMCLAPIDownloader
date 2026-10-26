"""自绘控件：方块图标、平滑进度条、标题栏、版本列表代理。"""

from __future__ import annotations

import math

from .qt import (Property, QAbstractItemView, QBrush, QCheckBox, QColor,
                 QEasingCurve, QFont, QFontMetrics, QHBoxLayout, QLabel,
                 QLinearGradient, QListView, QModelIndex, QPainter,
                 QPainterPath, QPen, QPoint, QPolygonF, QPropertyAnimation,
                 QPushButton, QRectF, QSize, QSizePolicy, QStyle,
                 QStyledItemDelegate, Qt, QTimer, QVBoxLayout, QWidget, Signal)

from . import APP_SUBTITLE, APP_TITLE, theme


# --------------------------------------------------------------------------- #
# 复选框：QSS 一旦给 indicator 上了样式，Qt 就不再画对勾，所以整个自己画
# --------------------------------------------------------------------------- #

class CheckBox(QCheckBox):
    BOX = 17

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetrics(self.font())
        w = self.BOX + 9 + fm.horizontalAdvance(self.text()) + 4
        return QSize(int(w), max(22, fm.height() + 8))

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        h = float(self.height())
        s = float(self.BOX)
        rect = QRectF(0.5, (h - s) / 2.0, s, s)
        hovered = self.underMouse() and self.isEnabled()

        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.ACCENT if self.isEnabled()
                              else theme.SURFACE_TOP))
            p.drawRoundedRect(rect, 5, 5)
            # 对勾
            pen = QPen(QColor("#FFFFFF" if self.isEnabled() else theme.TEXT_MUTE),
                       2.0)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            cy = rect.center().y()
            tick = QPainterPath()
            tick.moveTo(rect.left() + 4.3, cy + 0.3)
            tick.lineTo(rect.left() + 6.9, cy + 3.0)
            tick.lineTo(rect.right() - 3.8, cy - 3.5)
            p.drawPath(tick)
        else:
            p.setPen(QPen(QColor(theme.BORDER_HI), 1.2))
            p.setBrush(QColor(theme.SURFACE_TOP if hovered else theme.SURFACE_HI))
            p.drawRoundedRect(rect, 5, 5)

        # 文字
        f = self.font()
        p.setFont(f)
        p.setPen(QColor(theme.TEXT_DIM if self.isEnabled() else theme.TEXT_MUTE))
        fm = QFontMetrics(f)
        tx = s + 9
        avail = int(max(0.0, self.width() - tx))
        text = fm.elidedText(self.text(), Qt.ElideRight, avail)
        p.drawText(QRectF(tx, 0, float(avail), h),
                   Qt.AlignVCenter | Qt.AlignLeft, text)
        p.end()


# --------------------------------------------------------------------------- #
# 图标：等距小方块（像 MC 里的草方块）
# --------------------------------------------------------------------------- #

class ElidedLabel(QLabel):
    """按宽度自动省略中间部分的标签，适合显示长路径。"""

    def __init__(self, text: str = "", parent: QWidget | None = None,
                 mode=Qt.ElideMiddle):
        super().__init__(parent)
        self._full = text
        self._mode = mode
        self.setTextFormat(Qt.PlainText)
        self.setToolTip(text)
        self._refresh()

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text or ""
        self.setToolTip(self._full)
        self._refresh()

    def fullText(self) -> str:  # noqa: N802
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        fm = self.fontMetrics()
        w = max(30, self.width() - 2)
        super().setText(fm.elidedText(self._full, self._mode, w))


class BlockIcon(QWidget):
    def __init__(self, size: int = 30, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height())
        w, h = s * 0.46, s * 0.26
        cx, cy = s / 2, s / 2
        top = QPolygonF([
            QPoint(int(cx), int(cy - h * 1.35)),
            QPoint(int(cx + w), int(cy - h * 0.45)),
            QPoint(int(cx), int(cy + h * 0.45)),
            QPoint(int(cx - w), int(cy - h * 0.45)),
        ])
        left = QPolygonF([
            QPoint(int(cx - w), int(cy - h * 0.45)),
            QPoint(int(cx), int(cy + h * 0.45)),
            QPoint(int(cx), int(cy + h * 1.75)),
            QPoint(int(cx - w), int(cy + h * 0.85)),
        ])
        right = QPolygonF([
            QPoint(int(cx + w), int(cy - h * 0.45)),
            QPoint(int(cx), int(cy + h * 0.45)),
            QPoint(int(cx), int(cy + h * 1.75)),
            QPoint(int(cx + w), int(cy + h * 0.85)),
        ])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#5ED17A"))          # 草顶
        p.drawPolygon(top)
        p.setBrush(QColor("#8B5A3C"))          # 泥土左
        p.drawPolygon(left)
        p.setBrush(QColor("#6E452C"))          # 泥土右
        p.drawPolygon(right)
        # 顶部高光
        p.setBrush(QColor(255, 255, 255, 38))
        p.drawPolygon(QPolygonF([
            QPoint(int(cx), int(cy - h * 1.35)),
            QPoint(int(cx + w * 0.55), int(cy - h * 0.6)),
            QPoint(int(cx), int(cy - h * 0.1)),
            QPoint(int(cx - w * 0.55), int(cy - h * 0.6)),
        ]))
        p.end()


# --------------------------------------------------------------------------- #
# 平滑进度条
# --------------------------------------------------------------------------- #

class SmoothBar(QWidget):
    """带缓动动画、渐变填充和流光的高进度条。"""

    def __init__(self, height: int = 10, parent: QWidget | None = None):
        super().__init__(parent)
        self._value = 0.0
        self._display = 0.0
        self._target = 0.0
        self._running = False
        self._phase = 0.0
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._anim = QPropertyAnimation(self, b"display", self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    # --- 属性：用于动画 ---
    def get_display(self) -> float:
        return self._display

    def set_display(self, v: float) -> None:
        self._display = max(0.0, min(1.0, v))
        self.update()

    display = Property(float, get_display, set_display)

    def set_value(self, v: float, animated: bool = True) -> None:
        v = max(0.0, min(1.0, v))
        self._target = v
        if not animated:
            self._anim.stop()
            self.set_display(v)
            return
        if abs(v - self._display) < 0.001:
            return
        self._anim.stop()
        self._anim.setStartValue(self._display)
        self._anim.setEndValue(v)
        self._anim.start()

    def set_running(self, running: bool) -> None:
        self._running = running
        if running:
            self._timer.start()
        else:
            self._timer.stop()
            self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.05) % (2 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = h / 2

        # 轨道
        track = QPainterPath()
        track.addRoundedRect(QRectF(0, 0, w, h), r, r)
        p.fillPath(track, QColor("#1E2534"))

        if self._display <= 0.0005:
            p.end()
            return

        fill_w = max(h, w * self._display)
        fill = QPainterPath()
        fill.addRoundedRect(QRectF(0, 0, fill_w, h), r, r)
        p.save()
        p.setClipPath(fill)

        grad = QLinearGradient(0, 0, fill_w, 0)
        grad.setColorAt(0.0, QColor(theme.ACCENT))
        grad.setColorAt(0.6, QColor(theme.PURPLE))
        grad.setColorAt(1.0, QColor(theme.ACCENT_HI))
        p.fillRect(QRectF(0, 0, fill_w, h), QBrush(grad))

        # 顶部高光
        gloss = QLinearGradient(0, 0, 0, h)
        gloss.setColorAt(0, QColor(255, 255, 255, 46))
        gloss.setColorAt(0.5, QColor(255, 255, 255, 0))
        p.fillRect(QRectF(0, 0, fill_w, h), QBrush(gloss))

        # 流光
        if self._running:
            shift = (math.sin(self._phase) * 0.5 + 0.5)
            x = fill_w * shift
            shine = QLinearGradient(x - 60, 0, x + 60, 0)
            shine.setColorAt(0.0, QColor(255, 255, 255, 0))
            shine.setColorAt(0.5, QColor(255, 255, 255, 40))
            shine.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillRect(QRectF(max(0, x - 60), 0, 120, h), QBrush(shine))
        p.restore()

        # 前沿点
        if 0.0 < self._display < 0.999:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 210))
            p.drawEllipse(QRectF(fill_w - h * 0.75, h * 0.28,
                                 h * 0.44, h * 0.44))
        p.end()


class RingGauge(QWidget):
    """环形进度（进度页右上角用）。"""

    def __init__(self, size: int = 96, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._value = 0.0
        self._text = "0%"

    def set_value(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self._text = f"{self._value * 100:.0f}%"
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        pad = 6
        rect = QRectF(pad, pad, side - pad * 2, side - pad * 2)

        pen = QPen(QColor("#232B3C"), 8)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 0, 360 * 16)

        if self._value > 0:
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0, QColor(theme.ACCENT))
            grad.setColorAt(1, QColor(theme.PURPLE))
            pen = QPen(QBrush(grad), 8)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, 90 * 16, -int(360 * 16 * self._value))

        f = QFont(theme.FONT_UI, 13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.TEXT))
        p.drawText(rect, Qt.AlignCenter, self._text)
        p.end()


# --------------------------------------------------------------------------- #
# 标题栏
# --------------------------------------------------------------------------- #

class TitleBar(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(56)
        self._win = parent
        self._drag_pos: QPoint | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 10, 0)
        lay.setSpacing(10)

        lay.addWidget(BlockIcon(28))

        box = QVBoxLayout()
        box.setSpacing(0)
        box.setContentsMargins(0, 0, 0, 0)
        name = QLabel(APP_TITLE)
        name.setObjectName("AppName")
        sub = QLabel(APP_SUBTITLE)
        sub.setObjectName("AppSub")
        box.addWidget(name)
        box.addWidget(sub)
        lay.addLayout(box)
        lay.addStretch(1)

        self.btn_min = self._mk("–", "最小化")
        self.btn_max = self._mk("□", "最大化")
        self.btn_close = self._mk("×", "关闭")
        self.btn_close.setObjectName("WinBtnClose")
        for b in (self.btn_min, self.btn_max, self.btn_close):
            b.setFixedSize(34, 30)
            lay.addWidget(b)

        self.btn_min.clicked.connect(self._win.showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(self._win.close)

    def _mk(self, text: str, tip: str) -> QPushButton:
        b = QPushButton(text, self)
        b.setObjectName("WinBtn")
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _toggle_max(self) -> None:
        if self._win.isMaximized():
            self._win.showNormal()
            self.btn_max.setText("□")
        else:
            self._win.showMaximized()
            self.btn_max.setText("❐")

    # 拖动窗口
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - \
                self._win.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            if self._win.isMaximized():
                self._win.showNormal()
                self.btn_max.setText("□")
            self._win.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self._toggle_max()


# --------------------------------------------------------------------------- #
# 版本列表
# --------------------------------------------------------------------------- #

class VersionList(QListView):
    """带 hover / 选中效果的版本列表。"""

    ROW_H = 58

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("VersionList")
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QListView.NoFrame)
        self.setSpacing(0)

    def sizeHint(self) -> QSize:
        return QSize(420, 520)


class VersionDelegate(QStyledItemDelegate):
    ROW_H = 58

    def __init__(self, parent=None):
        super().__init__(parent)
        self.installed: set[str] = set()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), self.ROW_H)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        """包一层异常保护：绘制里出任何错都不能让整个程序退出。"""
        painter.save()
        try:
            self._paint(painter, option, index)
        except Exception:  # noqa: BLE001
            pass
        finally:
            painter.restore()

    def _paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        info = index.data(Qt.UserRole)
        if info is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(option.rect).adjusted(4, 3, -4, -3)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        path = QPainterPath()
        path.addRoundedRect(rect, 11, 11)
        if selected:
            painter.fillPath(path, QColor(110, 139, 255, 34))
            painter.setPen(QPen(QColor(110, 139, 255, 150), 1))
            painter.drawPath(path)
        elif hovered:
            painter.fillPath(path, QColor(255, 255, 255, 12))
        else:
            painter.fillPath(path, QColor(255, 255, 255, 0))

        # 左侧强调条
        if selected:
            bar = QPainterPath()
            bar.addRoundedRect(QRectF(rect.left() + 0, rect.top() + 14,
                                      3.2, rect.height() - 28), 2, 2)
            painter.fillPath(bar, QColor(theme.ACCENT))

        # 版本号
        f = QFont(theme.FONT_UI)
        f.setPointSizeF(10.5)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QColor(theme.TEXT if not selected else "#FFFFFF"))
        fm = QFontMetrics(f)
        left = rect.left() + 18
        cy = rect.center().y()

        is_installed = info.id in self.installed
        # 注意：elidedText 的宽度必须是 int，PyQt5 不做隐式转换
        avail = int(rect.width()) - 210
        vid_text = fm.elidedText(info.id, Qt.ElideRight, max(80, avail))
        vid_w = fm.horizontalAdvance(vid_text)
        painter.drawText(QPoint(int(left), int(cy + fm.ascent() / 2 - 2)), vid_text)

        # 类型徽章
        color, alpha = theme.TYPE_COLORS.get(info.type, (theme.TEXT_DIM, 0.14))
        bg = QColor(color)
        bg.setAlphaF(alpha)
        badge_f = QFont(theme.FONT_UI)
        badge_f.setPointSizeF(8.5)
        painter.setFont(badge_f)
        bfm = QFontMetrics(badge_f)
        label = info.type_label
        bw = bfm.horizontalAdvance(label) + 16
        bh = 19
        bx = left + vid_w + 12
        by = cy - bh / 2 - 1
        bpath = QPainterPath()
        bpath.addRoundedRect(QRectF(bx, by, bw, bh), 6, 6)
        painter.fillPath(bpath, bg)
        painter.setPen(QColor(color))
        painter.drawText(QRectF(bx, by, bw, bh), Qt.AlignCenter, label)

        # 已安装标记
        if is_installed:
            ix = bx + bw + 10
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.OK))
            painter.drawEllipse(QRectF(ix, cy - 3, 6, 6))
            painter.setPen(QColor(theme.OK))
            sf = QFont(theme.FONT_UI)
            sf.setPointSizeF(8.5)
            painter.setFont(sf)
            painter.drawText(QPoint(int(ix + 11), int(cy + 4)), "已安装")

        # 日期
        df = QFont(theme.FONT_UI)
        df.setPointSizeF(9)
        painter.setFont(df)
        painter.setPen(QColor(theme.TEXT_MUTE))
        painter.drawText(QRectF(rect.right() - 100, cy - 9, 88, 18),
                         Qt.AlignRight | Qt.AlignVCenter, info.date)

        painter.restore()
