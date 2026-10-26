"""主窗口：侧边栏 + 版本列表 + 安装面板 + 进度页 + 设置页。"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from .qt import (QAbstractItemView, QAbstractListModel, QApplication,
                 QButtonGroup, QComboBox, QDialog, QFileDialog, QFont, QFrame,
                 QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListView,
                 QListWidget, QListWidgetItem, QMessageBox, QModelIndex,
                 QObject, QPlainTextEdit, QPushButton, QRect, QSize,
                 QSizeGrip, QSizePolicy, QSlider, QStackedWidget, Qt, QThread,
                 QTimer, QVBoxLayout, QWidget, Signal)

from . import APP_TITLE, api, installer as inst_mod, net, paths, theme
from .config import Config
from .net import ProgressSnapshot, Source
from .widgets import (BlockIcon, CheckBox, ElidedLabel, RingGauge, SmoothBar,
                      TitleBar, VersionDelegate)


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #

def hsize(n: float) -> str:
    if n <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    return f"{n:.1f} {units[i]}" if i else f"{int(n)} {units[i]}"


def htime(sec: float) -> str:
    if sec <= 0 or sec > 86400:
        return "--"
    sec = int(sec)
    if sec < 60:
        return f"{sec} 秒"
    if sec < 3600:
        return f"{sec // 60} 分 {sec % 60} 秒"
    return f"{sec // 3600} 时 {(sec % 3600) // 60} 分"


# --------------------------------------------------------------------------- #
# 后台线程
# --------------------------------------------------------------------------- #

class FnThread(QThread):
    """跑一个函数，结果通过信号回主线程。"""

    ok = Signal(object)
    err = Signal(str)

    def __init__(self, fn, parent: QObject | None = None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            self.ok.emit(self._fn())
        except Exception as exc:  # noqa: BLE001
            self.err.emit(str(exc))


class InstallThread(QThread):
    stage = Signal(str)
    prog = Signal(object)
    log = Signal(str)
    done = Signal(str)
    fail = Signal(str)

    def __init__(self, req: inst_mod.InstallRequest, parent=None):
        super().__init__(parent)
        self.req = req
        self._installer: inst_mod.Installer | None = None

    def run(self) -> None:
        self._installer = inst_mod.Installer(
            on_stage=self.stage.emit, on_progress=self.prog.emit,
            on_log=self.log.emit)
        try:
            vid = self._installer.install(self.req)
            self.done.emit(vid)
        except inst_mod.Cancelled:
            self.fail.emit("__cancelled__")
        except Exception as exc:  # noqa: BLE001
            self.fail.emit(str(exc))

    def cancel(self) -> None:
        if self._installer:
            self._installer.cancel()


# --------------------------------------------------------------------------- #
# 版本列表模型
# --------------------------------------------------------------------------- #

class VersionModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.rows: list[api.VersionInfo] = []

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        row = self.rows[index.row()]
        if role == Qt.UserRole:
            return row
        if role == Qt.DisplayRole:
            return row.id
        return None

    def set_rows(self, rows: list[api.VersionInfo]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()


# --------------------------------------------------------------------------- #
# 游戏目录选择对话框
# --------------------------------------------------------------------------- #

class DirDialog(QDialog):
    def __init__(self, candidates: list[paths.GameDir], current: str,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择游戏目录")
        self.setMinimumSize(620, 440)
        self.setStyleSheet(theme.qss() +
                           "QDialog{background:#151922;}"
                           "QListWidget{background:#12161F;border:1px solid #28303F;"
                           "border-radius:10px;padding:6px;}"
                           "QListWidget::item{border-radius:8px;padding:7px 9px;}"
                           "QListWidget::item:selected{background:rgba(110,139,255,0.22);}"
                           "QListWidget::item:hover{background:rgba(255,255,255,0.05);}")
        self.result_path: str = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        t = QLabel("自动识别到的 .minecraft 目录")
        t.setObjectName("H2")
        lay.addWidget(t)
        hint = QLabel("按「版本数量」排序，双击可直接选择；也可以手动浏览其他位置。")
        hint.setObjectName("Mute")
        lay.addWidget(hint)

        self.list = QListWidget()
        self.list.setMouseTracking(True)
        lay.addWidget(self.list, 1)

        for g in candidates:
            it = QListWidgetItem(f"{g.path}\n    {g.subtitle}")
            it.setData(Qt.UserRole, str(g.path))
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.doubleClicked.connect(lambda *_: self._accept_current())

        tip = QLabel(f"当前目录：{current}")
        tip.setObjectName("PathText")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        row = QHBoxLayout()
        b_browse = QPushButton("浏览…")
        b_browse.setObjectName("Ghost")
        b_browse.clicked.connect(self._browse)
        b_new = QPushButton("用当前目录新建")
        b_new.setObjectName("Ghost")
        b_new.clicked.connect(self._accept_typed)
        b_ok = QPushButton("确定")
        b_ok.setObjectName("Primary")
        b_ok.clicked.connect(self._accept_current)
        row.addWidget(b_browse)
        row.addWidget(b_new)
        row.addStretch(1)
        row.addWidget(b_ok)
        lay.addLayout(row)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择 .minecraft 目录")
        if d:
            self.result_path = d
            self.accept()

    def _accept_current(self) -> None:
        it = self.list.currentItem()
        if it is not None:
            self.result_path = it.data(Qt.UserRole) or ""
            self.accept()

    def _accept_typed(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择目录（不存在会自动创建结构）")
        if d:
            self.result_path = d
            self.accept()


# --------------------------------------------------------------------------- #
# 主窗口
# --------------------------------------------------------------------------- #

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = Config()
        self.manifest = api.Manifest(net.Client(mode=self.cfg["source"]))
        self.installed: set[str] = set()
        self.candidates: list[paths.GameDir] = []
        self._threads: list[QThread] = []
        self._install_thread: InstallThread | None = None
        self._filter = "all"
        self._selected: api.VersionInfo | None = None
        self._loader = "vanilla"
        self._loader_items: list[api.LoaderVersion] = []
        self._last_snap: ProgressSnapshot | None = None
        self._t_start = 0.0

        self.setWindowTitle(f"{APP_TITLE} · Minecraft 下载工具")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(920, 620)
        self._build_ui()
        self._apply_style()
        self._apply_adaptive_geometry()
        QTimer.singleShot(80, self._boot)

    # ------------------------------------------------------------------ #
    # 界面搭建
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.root = QWidget(self)
        self.root.setObjectName("Root")
        self.root.setAttribute(Qt.WA_StyledBackground, True)
        outer.addWidget(self.root)

        v = QVBoxLayout(self.root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        v.addWidget(TitleBar(self))

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        v.addLayout(body, 1)

        body.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.page_download = self._build_download_page()
        self.page_progress = self._build_progress_page()
        self.page_settings = self._build_settings_page()
        for p in (self.page_download, self.page_progress, self.page_settings):
            self.stack.addWidget(p)

        # 无边框窗口的右下角拖拽缩放
        self.grip = QSizeGrip(self.root)
        self.grip.setFixedSize(16, 16)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "grip"):
            self.grip.move(self.root.width() - 18, self.root.height() - 18)
            self.grip.setVisible(not self.isMaximized())

    def _apply_adaptive_geometry(self) -> None:
        """按屏幕可用区域决定初始尺寸，避免小屏上超出屏幕、大屏上过小。"""
        scr = QApplication.primaryScreen()
        avail = scr.availableGeometry() if scr else QRect(0, 0, 1280, 800)
        sw, sh = avail.width(), avail.height()

        # 最小尺寸跟着屏幕走，小屏（如 1024x600 上网本）也不会超出屏幕
        min_w = min(920, max(720, sw - 40))
        min_h = min(620, max(500, sh - 70))
        self.setMinimumSize(min_w, min_h)
        target_w = min(max(min_w, int(sw * 0.86)), 1280)
        target_h = min(max(min_h, int(sh * 0.88)), 860)

        w, h = (self.cfg["window"] or [0, 0])[:2]
        if not (min_w <= int(w) <= sw and min_h <= int(h) <= sh):
            w, h = target_w, target_h
        self.resize(int(w), int(h))

        # 居中到可用区域（多屏也以主屏为准）
        self.move(avail.x() + (sw - self.width()) // 2,
                  avail.y() + (sh - self.height()) // 2)

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(236)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 18, 12, 14)
        lay.setSpacing(6)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for key, text in (("download", "版本下载"), ("settings", "设置中心")):
            b = QPushButton(text)
            b.setObjectName("NavBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._nav(k))
            self.nav_group.addButton(b)
            self.nav_buttons[key] = b
            lay.addWidget(b)
        self.nav_buttons["download"].setChecked(True)

        lay.addSpacing(16)
        lbl = QLabel("游戏目录")
        lbl.setObjectName("NavLabel")
        lay.addWidget(lbl)

        card = QFrame()
        card.setObjectName("CardSoft")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(11, 9, 11, 9)
        cl.setSpacing(4)
        self.dir_source = QLabel("未选择")
        self.dir_source.setObjectName("Mute")
        self.dir_path = ElidedLabel("—")
        self.dir_path.setObjectName("PathText")
        btn = QPushButton("更换目录")
        btn.setObjectName("Ghost")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._choose_dir)
        cl.addWidget(self.dir_source)
        cl.addWidget(self.dir_path)
        cl.addSpacing(2)
        cl.addWidget(btn)
        lay.addWidget(card)

        lay.addStretch(1)

        foot = QLabel("数据源 BMCLAPI\n支持原版 / Fabric / Forge\nNeoForge / OptiFine")
        foot.setObjectName("Mute")
        foot.setStyleSheet(f"color:{theme.TEXT_MUTE}; font-size:11px;")
        lay.addWidget(foot)
        return side

    def _build_download_page(self) -> QWidget:
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(16)

        # ---- 左：版本列表 ----
        left = QFrame()
        left.setObjectName("Card")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(14, 14, 8, 12)
        lv.setSpacing(10)

        head = QHBoxLayout()
        head.setContentsMargins(2, 0, 6, 0)
        title = QLabel("版本列表")
        title.setObjectName("H1")
        self.count_label = QLabel("加载中…")
        self.count_label.setObjectName("Mute")
        head.addWidget(title)
        head.addSpacing(8)
        head.addWidget(self.count_label)
        head.addStretch(1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索版本号")
        self.search.setMinimumWidth(118)
        self.search.setMaximumWidth(240)
        self.search.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.search.textChanged.connect(self._on_search)
        head.addWidget(self.search, 1)

        refresh = QPushButton("刷新")
        refresh.setObjectName("Ghost")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(lambda: self._load_manifest(force=True))
        head.addWidget(refresh)
        lv.addLayout(head)

        chips = QHBoxLayout()
        chips.setContentsMargins(2, 0, 6, 0)
        chips.setSpacing(6)
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        for key, text in (("all", "全部"), ("release", "正式版"),
                          ("snapshot", "快照"), ("old", "远古版本")):
            b = QPushButton(text)
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(key == "all")
            b.clicked.connect(lambda _=False, k=key: self._on_filter(k))
            self.filter_group.addButton(b)
            chips.addWidget(b)
        chips.addStretch(1)
        lv.addLayout(chips)

        self.vlist = QListView()
        self.vlist.setObjectName("VersionList")
        self.vlist.setMouseTracking(True)
        self.vlist.setUniformItemSizes(True)
        self.vlist.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.vlist.setSelectionMode(QListView.SingleSelection)
        self.vlist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.vlist.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.vlist.setFrameShape(QFrame.NoFrame)
        self.vmodel = VersionModel()
        self.vlist.setModel(self.vmodel)
        self.vdelegate = VersionDelegate(self.vlist)
        self.vlist.setItemDelegate(self.vdelegate)
        self.vlist.selectionModel().currentChanged.connect(self._on_select)
        lv.addWidget(self.vlist, 1)

        lay.addWidget(left, 1)

        # ---- 右：安装面板 ----
        right = QFrame()
        right.setObjectName("Card")
        right.setMinimumWidth(300)
        right.setMaximumWidth(392)
        right.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(16, 16, 16, 16)
        rv.setSpacing(10)

        h = QLabel("安装配置")
        h.setObjectName("H1")
        rv.addWidget(h)

        self.sel_name = QLabel("未选择版本")
        f = QFont(theme.FONT_UI)
        f.setPointSizeF(15)
        f.setBold(True)
        self.sel_name.setFont(f)
        self.sel_name.setWordWrap(True)
        rv.addWidget(self.sel_name)

        self.sel_meta = QLabel("在左侧选择一个版本开始")
        self.sel_meta.setObjectName("Dim")
        self.sel_meta.setWordWrap(True)
        rv.addWidget(self.sel_meta)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{theme.BORDER};")
        rv.addWidget(line)

        lab = QLabel("装载器")
        lab.setObjectName("H2")
        rv.addWidget(lab)

        grid = QGridLayout()
        grid.setSpacing(5)
        grid.setContentsMargins(0, 0, 0, 0)
        self.loader_group = QButtonGroup(self)
        self.loader_group.setExclusive(True)
        for i, key in enumerate(inst_mod.LOADERS):
            b = QPushButton(inst_mod.LOADER_LABELS[key])
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setChecked(key == "vanilla")
            b.clicked.connect(lambda _=False, k=key: self._on_loader(k))
            self.loader_group.addButton(b)
            grid.addWidget(b, i // 3, i % 3)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        rv.addLayout(grid)

        self.loader_hint = QLabel("下载官方原版游戏本体")
        self.loader_hint.setObjectName("Mute")
        self.loader_hint.setWordWrap(True)
        rv.addWidget(self.loader_hint)

        self.loader_combo = QComboBox()
        self.loader_combo.setEnabled(False)
        self.loader_combo.addItem("无需选择")
        self.loader_combo.currentIndexChanged.connect(
            lambda _idx: self._update_name_hint())
        rv.addWidget(self.loader_combo)

        name_lab = QLabel("安装到版本目录")
        name_lab.setObjectName("H2")
        rv.addWidget(name_lab)

        self.name_combo = QComboBox()
        self.name_combo.setEditable(True)
        self.name_combo.setInsertPolicy(QComboBox.NoInsert)
        self.name_combo.setMaxVisibleItems(12)
        if self.name_combo.lineEdit() is not None:
            self.name_combo.lineEdit().setMaxLength(64)
            self.name_combo.lineEdit().setPlaceholderText("自动命名")
        self.name_combo.setToolTip(
            "versions 下的文件夹名。留空自动命名；\n"
            "也可以从下拉里选一个已有版本目录，直接覆盖更新它。")
        self.name_combo.currentTextChanged.connect(
            lambda _t: self._update_name_hint())
        rv.addWidget(self.name_combo)

        self.name_hint = QLabel("")
        self.name_hint.setObjectName("Mute")
        self.name_hint.setWordWrap(True)
        rv.addWidget(self.name_hint)

        self.chk_assets = CheckBox("下载资源文件（声音、语言等）")
        self.chk_assets.setChecked(bool(self.cfg["with_assets"]))
        rv.addWidget(self.chk_assets)

        rv.addStretch(1)

        self.space_label = QLabel("")
        self.space_label.setObjectName("Mute")
        self.space_label.setWordWrap(True)
        rv.addWidget(self.space_label)

        self.install_btn = QPushButton("开始下载并安装")
        self.install_btn.setObjectName("Primary")
        self.install_btn.setCursor(Qt.PointingHandCursor)
        self.install_btn.setMinimumHeight(44)
        self.install_btn.clicked.connect(self._start_install)
        rv.addWidget(self.install_btn)

        lay.addWidget(right)
        return page

    def _build_progress_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 16, 18, 18)

        card = QFrame()
        card.setObjectName("Card")
        lay.addWidget(card)

        v = QVBoxLayout(card)
        v.setContentsMargins(26, 22, 26, 20)
        v.setSpacing(14)

        head = QHBoxLayout()
        box = QVBoxLayout()
        box.setSpacing(2)
        self.p_title = QLabel("准备中…")
        self.p_title.setObjectName("H1")
        self.p_stage = QLabel("等待开始")
        self.p_stage.setObjectName("Dim")
        box.addWidget(self.p_title)
        box.addWidget(self.p_stage)
        head.addLayout(box)
        head.addStretch(1)
        self.ring = RingGauge(92)
        head.addWidget(self.ring)
        v.addLayout(head)

        self.bar = SmoothBar(12)
        v.addWidget(self.bar)

        stats = QHBoxLayout()
        stats.setSpacing(22)
        self.s_speed = self._stat(stats, "速度", "--")
        self.s_eta = self._stat(stats, "剩余时间", "--")
        self.s_files = self._stat(stats, "文件", "0 / 0")
        self.s_size = self._stat(stats, "数据量", "0 B / 0 B")
        stats.addStretch(1)
        v.addLayout(stats)

        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        self.log.setMinimumHeight(240)
        # 只读日志不需要光标，否则左上角会有个小方块
        self.log.setCursorWidth(0)
        self.log.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.log, 1)

        row = QHBoxLayout()
        self.p_back = QPushButton("返回")
        self.p_back.setObjectName("Ghost")
        self.p_back.setCursor(Qt.PointingHandCursor)
        self.p_back.clicked.connect(self._back_from_progress)
        row.addWidget(self.p_back)
        row.addStretch(1)
        self.p_open = QPushButton("打开目录")
        self.p_open.setObjectName("Ghost")
        self.p_open.setCursor(Qt.PointingHandCursor)
        self.p_open.clicked.connect(self._open_game_dir)
        row.addWidget(self.p_open)
        self.p_cancel = QPushButton("取消安装")
        self.p_cancel.setObjectName("Danger")
        self.p_cancel.setCursor(Qt.PointingHandCursor)
        self.p_cancel.clicked.connect(self._cancel_install)
        row.addWidget(self.p_cancel)
        v.addLayout(row)
        return page

    def _stat(self, layout: QHBoxLayout, title: str, value: str) -> QLabel:
        box = QVBoxLayout()
        box.setSpacing(1)
        t = QLabel(title)
        t.setObjectName("Mute")
        val = QLabel(value)
        val.setObjectName("H2")
        box.addWidget(t)
        box.addWidget(val)
        layout.addLayout(box)
        return val

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(14)

        card = QFrame()
        card.setObjectName("Card")
        lay.addWidget(card)
        v = QVBoxLayout(card)
        v.setContentsMargins(22, 20, 22, 20)
        v.setSpacing(12)

        h = QLabel("设置")
        h.setObjectName("H1")
        v.addWidget(h)

        # 游戏目录
        g1 = QLabel("游戏目录（.minecraft）")
        g1.setObjectName("H2")
        v.addWidget(g1)
        row = QHBoxLayout()
        self.set_dir = QLineEdit()
        self.set_dir.setReadOnly(True)
        row.addWidget(self.set_dir, 1)
        b1 = QPushButton("重新识别")
        b1.setObjectName("Ghost")
        b1.clicked.connect(lambda: self._scan_dirs(show=True))
        b2 = QPushButton("选择…")
        b2.setObjectName("Ghost")
        b2.clicked.connect(self._choose_dir)
        row.addWidget(b1)
        row.addWidget(b2)
        v.addLayout(row)

        # 线程数
        t1 = QLabel("并发下载线程")
        t1.setObjectName("H2")
        v.addWidget(t1)
        row2 = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(1, 64)
        self.slider.setValue(int(self.cfg["workers"]))
        self.slider.valueChanged.connect(self._on_workers)
        self.workers_label = QLabel(f"{self.cfg['workers']} 线程")
        self.workers_label.setObjectName("Dim")
        self.workers_label.setFixedWidth(80)
        row2.addWidget(self.slider, 1)
        row2.addWidget(self.workers_label)
        v.addLayout(row2)

        # 下载源
        t2 = QLabel("下载源")
        t2.setObjectName("H2")
        v.addWidget(t2)
        self.source_combo = QComboBox()
        self.source_combo.addItem("BMCLAPI 镜像（推荐，失败自动回退官方）", Source.AUTO)
        self.source_combo.addItem("仅 BMCLAPI 镜像", Source.MIRROR)
        self.source_combo.addItem("仅官方源（需要能直连 Mojang）", Source.OFFICIAL)
        idx = self.source_combo.findData(self.cfg["source"])
        self.source_combo.setCurrentIndex(max(0, idx))
        self.source_combo.currentIndexChanged.connect(self._on_source)
        v.addWidget(self.source_combo)

        self.chk_verify = CheckBox("下载完成后校验 SHA1（更稳，稍慢）")
        self.chk_verify.setChecked(bool(self.cfg["verify"]))
        self.chk_verify.stateChanged.connect(
            lambda: self._save_cfg("verify", self.chk_verify.isChecked()))
        v.addWidget(self.chk_verify)

        # Java
        t3 = QLabel("Java（Forge / NeoForge 安装器需要）")
        t3.setObjectName("H2")
        v.addWidget(t3)
        row3 = QHBoxLayout()
        self.java_label = QLabel("检测中…")
        self.java_label.setObjectName("PathText")
        self.java_label.setWordWrap(True)
        row3.addWidget(self.java_label, 1)
        bj = QPushButton("重新检测")
        bj.setObjectName("Ghost")
        bj.clicked.connect(self._detect_java)
        row3.addWidget(bj)
        bp = QPushButton("指定…")
        bp.setObjectName("Ghost")
        bp.clicked.connect(self._pick_java)
        row3.addWidget(bp)
        v.addLayout(row3)

        v.addStretch(1)
        about = QLabel("基于 BMCLAPI（https://bmclapidoc.bangbang93.com/）构建 · "
                       "仅用于下载，不包含任何 Mojang 文件")
        about.setObjectName("Mute")
        about.setWordWrap(True)
        v.addWidget(about)
        return page

    # ------------------------------------------------------------------ #
    # 样式 / 启动
    # ------------------------------------------------------------------ #
    def _apply_style(self) -> None:
        self.setStyleSheet(theme.qss())

    def _boot(self) -> None:
        gd = self.cfg["game_dir"]
        if not gd or not Path(gd).exists():
            best = paths.detect_best()
            gd = str(best.path) if best else str(
                Path.home() / ".minecraft")
        self._set_game_dir(gd, source="自动识别" if not self.cfg["game_dir"] else "")
        if not os.environ.get("MCDL_SKIP_SCAN"):
            self._scan_dirs(show=False)
        self._load_manifest()
        self._detect_java()

    # ------------------------------------------------------------------ #
    # 导航
    # ------------------------------------------------------------------ #
    def _nav(self, key: str) -> None:
        if key == "download":
            self.stack.setCurrentWidget(self.page_download)
        else:
            self.stack.setCurrentWidget(self.page_settings)
            self.nav_buttons["settings"].setChecked(True)

    # ------------------------------------------------------------------ #
    # 游戏目录
    # ------------------------------------------------------------------ #
    def _set_game_dir(self, path: str, source: str = "") -> None:
        p = Path(path)
        self.cfg["game_dir"] = str(p)
        self.cfg.save()
        self.dir_path.setText(str(p))
        src = source
        if not src:
            src = paths.make_gamedir(p).source if p.is_dir() else "自定义目录"
        self.dir_source.setText(src)
        self.set_dir.setText(str(p))
        self.installed = set(paths.installed_versions(p))
        self.vdelegate.installed = self.installed
        self.vlist.viewport().update()
        self._refresh_name_options()

    def _choose_dir(self) -> None:
        dlg = DirDialog(self.candidates, str(self.cfg["game_dir"]), self)
        if dlg.exec_() and dlg.result_path:
            g = paths.make_gamedir(Path(dlg.result_path))
            self._set_game_dir(dlg.result_path, g.source)
            self._log(f"切换游戏目录：{dlg.result_path}")

    def _scan_dirs(self, show: bool = True) -> None:
        def work():
            return paths.scan(depth=3)

        th = FnThread(work, self)
        self._threads.append(th)

        def on_ok(res):
            self.candidates = res
            self._log(f"目录扫描完成：找到 {len(res)} 个候选")
            # 若当前目录不在候选里但有更好选择，仅在未配置时自动切换
            if res and not Path(self.cfg["game_dir"]).exists():
                self._set_game_dir(str(res[0].path), res[0].source)
            if show:
                QMessageBox.information(
                    self, "识别完成",
                    f"共找到 {len(res)} 个可能的游戏目录。\n"
                    "点击侧边栏「更换目录」可以选择。")

        th.ok.connect(on_ok)
        th.err.connect(lambda e: self._log(f"扫描失败：{e}"))
        th.start()

    def _open_game_dir(self) -> None:
        p = Path(self.cfg["game_dir"])
        p.mkdir(parents=True, exist_ok=True)
        import os
        os.startfile(str(p))  # noqa: S606

    # ------------------------------------------------------------------ #
    # 版本清单
    # ------------------------------------------------------------------ #
    def _load_manifest(self, force: bool = False) -> None:
        self.count_label.setText("加载中…")

        def work():
            return self.manifest.load(force=force)

        th = FnThread(work, self)
        self._threads.append(th)

        def on_ok(versions):
            self._refresh_list()
            self._log(f"版本清单已加载，共 {len(versions)} 个版本")
            # 默认选中最新正式版
            if not self._selected:
                for i, row in enumerate(self.vmodel.rows):
                    if row.type == "release" and row.id == self.manifest.latest.get("release"):
                        self.vlist.setCurrentIndex(self.vmodel.index(i, 0))
                        break
                else:
                    if self.vmodel.rows:
                        self.vlist.setCurrentIndex(self.vmodel.index(0, 0))

        def on_err(msg):
            self.count_label.setText("加载失败")
            self._log(f"版本清单加载失败：{msg}")
            QMessageBox.warning(
                self, "网络异常",
                "无法获取版本清单，请检查网络或稍后重试。\n\n" + msg)

        th.ok.connect(on_ok)
        th.err.connect(on_err)
        th.start()

    def _on_search(self, text: str) -> None:
        if not hasattr(self, "_search_timer"):
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.timeout.connect(self._refresh_list)
        self._search_timer.start(180)

    def _on_filter(self, key: str) -> None:
        self._filter = key
        self._refresh_list()

    def _refresh_list(self) -> None:
        versions = self.manifest.versions
        q = self.search.text().strip().lower()
        out: list[api.VersionInfo] = []
        for v in versions:
            if self._filter == "release" and v.type != "release":
                continue
            if self._filter == "snapshot" and v.type != "snapshot":
                continue
            if self._filter == "old" and not v.type.startswith("old"):
                continue
            if q and q not in v.id.lower():
                continue
            out.append(v)
        self.vmodel.set_rows(out)
        self.count_label.setText(f"{len(out)} 个版本")

    def _on_select(self, current: QModelIndex, _prev) -> None:
        if not current.isValid():
            return
        info = self.vmodel.rows[current.row()]
        self._selected = info
        self.sel_name.setText(info.id)
        state = "已安装" if info.id in self.installed else "未安装"
        self.sel_meta.setText(f"{info.type_label} · {info.date} · {state}")
        self._on_loader(self._loader, reload_items=True)
        self._update_name_hint()

    # ------------------------------------------------------------------ #
    # 装载器
    # ------------------------------------------------------------------ #
    def _on_loader(self, key: str, reload_items: bool = False) -> None:
        self._loader = key
        for b in self.loader_group.buttons():
            b.setChecked(inst_mod.LOADER_LABELS[key] == b.text())
        hints = {
            "vanilla": "下载官方原版游戏本体",
            "fabric": "轻量模组加载器，安装最快",
            "forge": "经典模组加载器，需要本机有 Java",
            "neoforge": "Forge 的社区分支，适合新版本，需要 Java",
            "optifine": "光影与性能优化，下载后需手动运行安装器",
        }
        self.loader_hint.setText(hints.get(key, ""))

        if key == "vanilla":
            self.loader_combo.clear()
            self.loader_combo.addItem("无需选择")
            self.loader_combo.setEnabled(False)
            self._update_space()
            return

        if not self._selected:
            return
        self.loader_combo.setEnabled(False)
        self.loader_combo.clear()
        self.loader_combo.addItem("正在获取可用版本…")

        mc = self._selected.id
        loader_key = key

        def work():
            client = net.Client(mode=self.cfg["source"])
            if loader_key == "fabric":
                return api.fabric_loaders(client, mc)
            if loader_key == "forge":
                return api.forge_builds(client, mc)
            if loader_key == "neoforge":
                return api.neoforge_versions(client, mc)
            return api.optifine_builds(client, mc)

        th = FnThread(work, self)
        self._threads.append(th)

        def on_ok(items):
            if loader_key != self._loader or not self._selected or self._selected.id != mc:
                return
            self._loader_items = items
            self.loader_combo.clear()
            if not items:
                self.loader_combo.addItem("该版本无可用安装包")
                self.loader_combo.setEnabled(False)
                self._log(f"{inst_mod.LOADER_LABELS[loader_key]} 在 {mc} 上没有可用版本")
                return
            for it in items[:60]:
                self.loader_combo.addItem(it.label + ("" if it.stable else "  (测试版)"),
                                          it.value)
            self.loader_combo.setEnabled(True)
            self._log(f"{inst_mod.LOADER_LABELS[loader_key]}：{mc} 可用 {len(items)} 个版本")
            self._update_name_hint()

        def on_err(msg):
            self.loader_combo.clear()
            self.loader_combo.addItem("获取失败")
            self._log(f"获取装载器版本失败：{msg}")

        th.ok.connect(on_ok)
        th.err.connect(on_err)
        th.start()
        self._update_space()

    # ------------------------------------------------------------------ #
    # versions 目录名
    # ------------------------------------------------------------------ #
    def _version_dirs(self) -> list[str]:
        gd = Path(self.cfg["game_dir"] or ".")
        vdir = gd / "versions"
        if not vdir.is_dir():
            return []
        try:
            return sorted((p.name for p in vdir.iterdir() if p.is_dir()),
                          reverse=True)
        except OSError:
            return []

    def _refresh_name_options(self) -> None:
        """把已存在的 versions 目录填进下拉，同时保留用户当前输入。"""
        if not hasattr(self, "name_combo"):
            return
        keep = self.name_combo.currentText()
        self.name_combo.blockSignals(True)
        self.name_combo.clear()
        for n in self._version_dirs():
            self.name_combo.addItem(n, n)
        self.name_combo.setEditText(keep)
        self.name_combo.blockSignals(False)
        self._update_name_hint()

    def _suggest_version_name(self) -> str:
        if not self._selected:
            return ""
        mc = self._selected.id
        v = (self.loader_combo.currentData() or "") if self._loader != "vanilla" else ""
        k = self._loader
        if k == "fabric":
            return f"fabric-loader-{v}-{mc}" if v else f"fabric-{mc}"
        if k == "forge":
            return f"{mc}-forge-{v}" if v else f"{mc}-forge"
        if k == "neoforge":
            return f"{mc}-neoforge-{v}" if v else f"{mc}-neoforge"
        if k == "optifine":
            return f"{mc}-optifine"
        return mc

    def _update_name_hint(self) -> None:
        if not hasattr(self, "name_hint"):
            return
        if self._loader == "optifine":
            self.name_combo.setEnabled(False)
            self.name_hint.setText("OptiFine 只下载安装包，不生成独立版本目录")
            return
        self.name_combo.setEnabled(True)
        suggest = self._suggest_version_name()
        if self.name_combo.lineEdit() is not None:
            self.name_combo.lineEdit().setPlaceholderText(
                f"自动：{suggest}" if suggest else "自动命名")
        cur = self.name_combo.currentText().strip()
        if not cur:
            self.name_hint.setText("留空则自动使用上面提示的名字")
            return
        err = inst_mod.check_version_name(cur)
        if err:
            self.name_hint.setText(err)
            return
        exists = (Path(self.cfg["game_dir"]) / "versions" / cur).is_dir()
        self.name_hint.setText("目录已存在，安装会覆盖更新其中的文件" if exists
                               else "将新建这个版本目录")

    def _update_space(self) -> None:
        gd = Path(self.cfg["game_dir"])
        try:
            import shutil
            free = shutil.disk_usage(str(gd if gd.exists() else gd.parent)).free
            self.space_label.setText(f"目标磁盘剩余 {hsize(free)}")
        except Exception:
            self.space_label.setText("")

    # ------------------------------------------------------------------ #
    # 安装
    # ------------------------------------------------------------------ #
    def _start_install(self) -> None:
        if not self._selected:
            QMessageBox.information(self, "提示", "请先在左侧选择一个版本。")
            return
        gd = Path(self.cfg["game_dir"])

        loader_ver = ""
        if self._loader != "vanilla":
            if not self.loader_combo.isEnabled() or self.loader_combo.count() == 0:
                QMessageBox.warning(self, "提示",
                                    f"{inst_mod.LOADER_LABELS[self._loader]} "
                                    "还没有可用的版本，请稍等或换个装载器。")
                return
            loader_ver = self.loader_combo.currentData() or ""
            if not loader_ver:
                QMessageBox.warning(self, "提示", "请选择装载器版本。")
                return
            if self._loader in ("forge", "neoforge"):
                java = inst_mod.find_java(gd)
                if not java:
                    QMessageBox.warning(
                        self, "缺少 Java",
                        "Forge / NeoForge 安装器需要 Java 才能运行。\n"
                        "请安装 JDK 17+ 后点击设置页的「重新检测」。")
                    return

        try:
            paths.ensure_mc_dir(gd)
        except OSError as exc:
            QMessageBox.critical(self, "无法写入目录", str(exc))
            return

        # versions 目录名（OptiFine 不生成版本，忽略此项）
        version_name = ""
        if self._loader != "optifine":
            version_name = self.name_combo.currentText().strip()
            err = inst_mod.check_version_name(version_name)
            if err:
                QMessageBox.warning(self, "版本目录名不可用", err)
                self.name_combo.setFocus()
                return
            if version_name and (gd / "versions" / version_name).exists():
                r = QMessageBox.question(
                    self, "目录已存在",
                    f"versions/{version_name} 已经存在。\n"
                    "继续会用本次安装的文件覆盖更新它，确定吗？")
                if r != QMessageBox.Yes:
                    return

        req = inst_mod.InstallRequest(
            game_dir=gd,
            mc_version=self._selected.id,
            loader=self._loader,
            loader_version=loader_ver,
            with_assets=self.chk_assets.isChecked(),
            workers=int(self.cfg["workers"]),
            mode=self.cfg["source"],
            verify=bool(self.cfg["verify"]),
            java_path=str(self.cfg.get("java_path") or ""),
            version_name=version_name,
        )
        self.cfg["with_assets"] = req.with_assets
        self.cfg.save()

        self._t_start = time.time()
        self._last_snap = None
        self.log.clear()
        self.p_title.setText(f"正在安装 {req.mc_version}"
                             + ("" if req.loader == "vanilla"
                                else f" · {inst_mod.LOADER_LABELS[req.loader]}"))
        self.p_stage.setText("准备中…")
        self.bar.set_value(0, animated=False)
        self.bar.set_running(True)
        self.ring.set_value(0)
        self.s_speed.setText("--")
        self.s_eta.setText("--")
        self.s_files.setText("0 / 0")
        self.s_size.setText("0 B / 0 B")
        self.p_cancel.setEnabled(True)
        self.p_back.setEnabled(True)

        self.stack.setCurrentWidget(self.page_progress)
        self.nav_buttons["download"].setChecked(True)

        th = InstallThread(req, self)
        th.stage.connect(self._on_stage)
        th.prog.connect(self._on_progress)
        th.log.connect(self._log)
        th.done.connect(self._on_done)
        th.fail.connect(self._on_fail)
        self._install_thread = th
        th.start()

    def _on_stage(self, text: str) -> None:
        self.p_stage.setText(text)

    def _on_progress(self, snap: ProgressSnapshot) -> None:
        self._last_snap = snap
        self.bar.set_value(snap.ratio)
        self.ring.set_value(snap.ratio)
        self.s_speed.setText(hsize(snap.speed) + "/s")
        remain = snap.total_bytes - snap.done_bytes
        eta = remain / snap.speed if snap.speed > 0 else 0
        self.s_eta.setText(htime(eta))
        self.s_files.setText(f"{snap.done_files} / {snap.total_files}")
        self.s_size.setText(f"{hsize(snap.done_bytes)} / {hsize(snap.total_bytes)}")

    def _on_done(self, vid: str) -> None:
        self.bar.set_value(1.0)
        self.bar.set_running(False)
        self.ring.set_value(1.0)
        self.p_stage.setText("安装完成 ✓")
        self.p_cancel.setEnabled(False)
        self._log("—" * 30)
        self._log(f"全部完成，版本 id：{vid}")
        self._log(f"耗时 {htime(time.time() - self._t_start)}")
        self.installed = set(paths.installed_versions(Path(self.cfg["game_dir"])))
        self.vdelegate.installed = self.installed
        self.vlist.viewport().update()
        if self._selected:
            state = "已安装" if self._selected.id in self.installed else "未安装"
            self.sel_meta.setText(
                f"{self._selected.type_label} · {self._selected.date} · {state}")

    def _on_fail(self, msg: str) -> None:
        self.bar.set_running(False)
        self.p_cancel.setEnabled(False)
        if msg == "__cancelled__":
            self.p_stage.setText("已取消")
            self._log("安装已取消")
            return
        self.p_stage.setText("安装失败")
        self._log(f"[错误] {msg}")
        QMessageBox.critical(self, "安装失败", msg)

    def _cancel_install(self) -> None:
        if self._install_thread:
            self._install_thread.cancel()
            self.p_stage.setText("正在取消…")
            self.p_cancel.setEnabled(False)

    def _back_from_progress(self) -> None:
        if self._install_thread and self._install_thread.isRunning():
            r = QMessageBox.question(self, "取消安装？",
                                     "安装还在进行中，返回会中止当前任务。确定吗？")
            if r != QMessageBox.Yes:
                return
            self._install_thread.cancel()
        self.stack.setCurrentWidget(self.page_download)

    # ------------------------------------------------------------------ #
    # 设置项
    # ------------------------------------------------------------------ #
    def _save_cfg(self, key: str, value) -> None:
        self.cfg[key] = value
        self.cfg.save()

    def _on_workers(self, v: int) -> None:
        self.workers_label.setText(f"{v} 线程")
        self._save_cfg("workers", int(v))

    def _on_source(self, _idx: int) -> None:
        val = self.source_combo.currentData()
        self._save_cfg("source", val)
        self.manifest.client.mode = val
        self._load_manifest(force=True)

    def _detect_java(self) -> None:
        gd = Path(self.cfg["game_dir"])
        java = self.cfg.get("java_path") or inst_mod.find_java(gd)
        if java:
            ver = inst_mod.java_version(java)
            self.java_label.setText(f"{java}  ({ver})")
        else:
            self.java_label.setText("未检测到 Java —— 只影响 Forge/NeoForge 安装")

    def _pick_java(self) -> None:
        f, _ = QFileDialog.getOpenFileName(
            self, "选择 java.exe", "", "Java 可执行文件 (java.exe);;所有文件 (*)")
        if f:
            self.cfg["java_path"] = f
            self.cfg.save()
            self._detect_java()
            self._log(f"已指定 Java：{f}")

    # ------------------------------------------------------------------ #
    def _log(self, text: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{ts}] {text}")
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._install_thread and self._install_thread.isRunning():
            r = QMessageBox.question(self, "仍在安装",
                                     "安装尚未完成，退出会中止下载。确定退出吗？")
            if r != QMessageBox.Yes:
                event.ignore()
                return
            self._install_thread.cancel()
        size = self.normalGeometry().size() if self.isMaximized() else self.size()
        self.cfg["window"] = [size.width(), size.height()]
        self.cfg.save()
        super().closeEvent(event)
