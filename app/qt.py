"""Qt 绑定层：统一从这里导入，避免各文件直接绑死某个绑定。

本项目使用 **PyQt5**（Qt 5.15）。原因：Qt 6 需要 Windows 10 1607+ 的
`SetThreadDescription`，在较老的 Windows / Windows Server 上会直接
"DLL load failed"，而 Qt 5.15 支持 Windows 7 及以上，覆盖面更广。
"""

from __future__ import annotations

from PyQt5.QtCore import (  # noqa: F401
    QAbstractListModel, QBuffer, QByteArray, QEasingCurve, QIODevice,
    QModelIndex, QObject, QPoint, QPointF, QPropertyAnimation, QRect,
    QRectF, QSize, Qt, QThread, QTimer,
    pyqtProperty as Property,
    pyqtSignal as Signal,
    pyqtSlot as Slot,
)
from PyQt5.QtGui import (  # noqa: F401
    QBrush, QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QImage,
    QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
)
from PyQt5.QtWidgets import (  # noqa: F401
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox,
    QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListView, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QSizeGrip, QSizePolicy, QSlider, QStackedWidget, QStyle,
    QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout, QWidget,
)

__all__ = [n for n in dir() if not n.startswith("_")]
