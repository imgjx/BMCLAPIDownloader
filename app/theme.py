"""配色与全局样式表。深色 + 圆角 + 渐变强调色。"""

from __future__ import annotations

# 基础色板
BG = "#0D0F14"
SURFACE = "#151922"
SURFACE_HI = "#1C2130"
SURFACE_TOP = "#232A3B"
BORDER = "#28303F"
BORDER_HI = "#3A4560"
TEXT = "#E9EDF6"
TEXT_DIM = "#9AA4B8"
TEXT_MUTE = "#6C768C"
ACCENT = "#6E8BFF"
ACCENT_HI = "#8AA2FF"
ACCENT_DEEP = "#4A63D8"
PURPLE = "#A56CFF"
OK = "#3DDC97"
WARN = "#FFC24B"
ERR = "#FF6B78"

FONT_UI = "Microsoft YaHei UI"
FONT_MONO = "Consolas"

TYPE_COLORS = {
    "release": (OK, 0.16),
    "snapshot": (WARN, 0.16),
    "old_beta": ("#8B94A8", 0.14),
    "old_alpha": ("#8B94A8", 0.14),
}


def qss() -> str:
    return f"""
* {{
    font-family: "{FONT_UI}", "Segoe UI", sans-serif;
    outline: none;
}}
QWidget {{
    color: {TEXT};
    font-size: 13px;
}}
#Root {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}

/* ---------------- 标题栏 ---------------- */
#TitleBar {{
    background: transparent;
    border-bottom: 1px solid {BORDER};
}}
#AppName {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT};
}}
#AppSub {{
    font-size: 11px;
    color: {TEXT_MUTE};
}}
#WinBtn, #WinBtnClose {{
    background: transparent;
    border: none;
    border-radius: 7px;
    color: {TEXT_DIM};
    font-size: 14px;
    padding: 0px;
}}
#WinBtn:hover {{
    background: rgba(255,255,255,0.08);
    color: {TEXT};
}}
#WinBtnClose:hover {{
    background: #E0485A;
    color: #FFFFFF;
}}

/* ---------------- 侧边栏 ---------------- */
#Sidebar {{
    background: {SURFACE};
    border-right: 1px solid {BORDER};
    border-top-left-radius: 15px;
    border-bottom-left-radius: 15px;
}}
#NavBtn {{
    background: transparent;
    border: none;
    border-radius: 10px;
    color: {TEXT_DIM};
    text-align: left;
    padding: 10px 14px;
    font-size: 13.5px;
}}
#NavBtn:hover {{
    background: rgba(255,255,255,0.05);
    color: {TEXT};
}}
#NavBtn:checked {{
    background: rgba(110,139,255,0.16);
    color: {ACCENT_HI};
    font-weight: 600;
}}
#NavLabel {{
    color: {TEXT_MUTE};
    font-size: 11px;
    padding: 0 6px;
}}

/* ---------------- 卡片 ---------------- */
#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
#CardSoft {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
#H1 {{
    font-size: 20px;
    font-weight: 700;
    color: {TEXT};
}}
#H2 {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT};
}}
#Dim {{
    color: {TEXT_DIM};
    font-size: 12px;
}}
#Mute {{
    color: {TEXT_MUTE};
    font-size: 11.5px;
}}
#PathText {{
    color: {TEXT_DIM};
    font-size: 11.5px;
    font-family: "{FONT_MONO}";
}}

/* ---------------- 输入 ---------------- */
QLineEdit {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 8px 12px;
    color: {TEXT};
    selection-background-color: {ACCENT_DEEP};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
    background: #1F2534;
}}
QLineEdit::placeholder {{
    color: {TEXT_MUTE};
}}

/* ---------------- 按钮 ---------------- */
QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {ACCENT}, stop:1 {PURPLE});
    border: none;
    border-radius: 10px;
    color: #FFFFFF;
    font-size: 13.5px;
    font-weight: 600;
    padding: 11px 18px;
}}
QPushButton#Primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {ACCENT_HI}, stop:1 #B682FF);
}}
QPushButton#Primary:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {ACCENT_DEEP}, stop:1 #8B55E0);
}}
QPushButton#Primary:disabled {{
    background: {SURFACE_TOP};
    color: {TEXT_MUTE};
}}
QPushButton#Ghost {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 9px;
    color: {TEXT_DIM};
    padding: 8px 13px;
}}
QPushButton#Ghost:hover {{
    background: {SURFACE_TOP};
    border: 1px solid {BORDER_HI};
    color: {TEXT};
}}
QPushButton#Danger {{
    background: rgba(255,107,120,0.14);
    border: 1px solid rgba(255,107,120,0.4);
    border-radius: 9px;
    color: {ERR};
    padding: 9px 16px;
    font-weight: 600;
}}
QPushButton#Danger:hover {{
    background: rgba(255,107,120,0.24);
}}

/* 分段选择（装载器） */
QPushButton#Chip {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: {TEXT_DIM};
    padding: 7px 10px;
    font-size: 12.5px;
}}
QPushButton#Chip:hover {{
    color: {TEXT};
    background: rgba(255,255,255,0.05);
}}
QPushButton#Chip:checked {{
    background: rgba(110,139,255,0.2);
    border: 1px solid rgba(110,139,255,0.55);
    color: {ACCENT_HI};
    font-weight: 600;
}}

/* ---------------- 下拉框 ---------------- */
QComboBox {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 8px 12px;
    color: {TEXT};
    min-height: 18px;
}}
QComboBox:hover {{
    border: 1px solid {BORDER_HI};
}}
QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_DIM};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER_HI};
    border-radius: 10px;
    padding: 5px;
    color: {TEXT};
    selection-background-color: rgba(110,139,255,0.28);
    outline: none;
}}

/* ---------------- 列表 ---------------- */
QListView#VersionList {{
    background: transparent;
    border: none;
    padding: 2px;
}}
QListView#VersionList::item {{
    border: none;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 4px 2px 4px 0;
}}
QScrollBar::handle:vertical {{
    background: #333D52;
    border-radius: 4px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: #465373;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QScrollBar:horizontal {{
    height: 9px;
    background: transparent;
}}
QScrollBar::handle:horizontal {{
    background: #333D52;
    border-radius: 4px;
}}

/* ---------------- 日志 ---------------- */
QPlainTextEdit#Log {{
    background: #0B0D12;
    border: 1px solid {BORDER};
    border-radius: 12px;
    color: #A9B6CE;
    font-family: "{FONT_MONO}";
    font-size: 11.5px;
    padding: 10px;
    selection-background-color: {ACCENT_DEEP};
}}

/* 复选框由 widgets.CheckBox 自绘，QSS 不参与 indicator 绘制 */
QCheckBox {{
    spacing: 8px;
    color: {TEXT_DIM};
}}

QSlider::groove:horizontal {{
    height: 5px;
    background: {SURFACE_TOP};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT}, stop:1 {PURPLE});
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #FFFFFF;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}

QToolTip {{
    background: {SURFACE_TOP};
    color: {TEXT};
    border: 1px solid {BORDER_HI};
    border-radius: 8px;
    padding: 6px 9px;
}}

QMessageBox {{
    background: {SURFACE};
}}
"""
