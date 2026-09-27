# -*- coding: utf-8 -*-
"""颜色与字阶 → QSS。全应用**唯一**拼样式表的地方。

QSS 只管 Qt 原生控件的字和底：胶囊按钮、输入框、下拉框、开关、卡片都由
:mod:`ui.widgets` 自己画——QSS 的 ``border-radius`` 不做抗锯齿，32 高的胶囊画出来
边缘全是台阶。

⚠️ 绝不要写 ``QWidget { background: ... }`` 这类**无祖先限定**的类型选择器。
Qt 的类型选择器连子类一起命中，每个 QLabel 都会被刷上底色，在卡片上显示成一条条横杠。
``tests/test_theme.py`` 钉着这条。

⚠️ QSS **不支持** ``outline`` / ``outline-offset``（实测被静默忽略）。焦点环由
:class:`ui.widgets.FocusTracker` 统一画，这里没有 ``:focus`` 规则。
"""

from __future__ import annotations

from . import metrics as m


def rgba(argb: str) -> str:
    """``#AARRGGBB`` → ``rgba(r, g, b, a)``（a 取 0～255，QSS 两种写法都认）。"""
    h = argb.lstrip("#")
    if len(h) == 6:
        h = "FF" + h
    a, r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4, 6))
    return f"rgba({r}, {g}, {b}, {a})"


def build(t: dict[str, str], scale: float = 1.0) -> str:
    """按一套颜色生成整份样式表。``scale`` 是系统「文本大小」，字号在这里乘一次。"""
    q = {k: rgba(v) for k, v in t.items()}

    def px(spec: m.FontSpec) -> int:
        return max(1, round(spec.size * scale))

    return f"""
/* ===== 窗口底 =====
   Mica 由窗口壳层持有，中间容器全都不画底。材质铺不上（Windows 10、关了透明效果、高对比度）
   时壳层给 AppRoot 设 opaque，退回 BackgroundWithCard 实色（16.3）。
   ⚠️ 底色画在 AppRoot 上，不画在 QMainWindow 上：窗口设过 WA_TranslucentBackground 之后
   QMainWindow 自己的 QSS 背景就不画了，而那个属性 show() 之后撤不掉。 */
QWidget#AppRoot, QWidget#NavPane, QWidget#PageHeader, QWidget#PageBody,
QStackedWidget#ContentPane {{
    background: transparent;
}}
QWidget#AppRoot[opaque="true"] {{
    background: {q["bgGrouped"]};
}}
QListWidget#NavList {{
    background: transparent;
    border: none;
    outline: none;
}}

/* ===== 文字 ===== 角色由 role 属性选，默认是正文 */
QLabel {{
    color: {q["label1"]};
    background: transparent;
    font-size: {px(m.BODY)}px;
}}
QLabel[role="pageTitle"] {{
    font-size: {px(m.PAGE_TITLE)}px;
    font-weight: {m.PAGE_TITLE.weight};
}}
QLabel[role="dialogTitle"] {{
    font-size: {px(m.DIALOG_TITLE)}px;
    font-weight: {m.DIALOG_TITLE.weight};
}}
QLabel[role="emptyTitle"] {{
    font-size: {px(m.EMPTY_TITLE)}px;
    font-weight: {m.EMPTY_TITLE.weight};
}}
QLabel[role="title"] {{
    font-weight: {m.TITLE.weight};
}}
QLabel[role="value"] {{
    color: {q["label2"]};
}}
QLabel[role="action"] {{
    color: {q["primaryText"]};
    font-weight: {m.TITLE.weight};
}}
QLabel[role="secondary"] {{
    color: {q["label2"]};
    font-size: {px(m.SECONDARY)}px;
}}
QLabel[role="groupTitle"] {{
    color: {q["label2"]};
    font-size: {px(m.GROUP_TITLE)}px;
    font-weight: {m.GROUP_TITLE.weight};
}}
QLabel[role="caption"] {{
    color: {q["label2"]};
    font-size: {px(m.CAPTION)}px;
}}
QLabel[role="metric"] {{
    font-size: {px(m.METRIC)}px;
    font-weight: {m.METRIC.weight};
}}
QLabel[role="error"] {{
    color: {q["error"]};
    font-size: {px(m.SECONDARY)}px;
}}
QLabel:disabled {{
    color: {q["label3"]};
}}

/* ===== 输入 ===== 胶囊底由 widgets 自己画，这里只管字 */
QLineEdit, QAbstractSpinBox {{
    background: transparent;
    border: none;
    padding: 0px;
    color: {q["label1"]};
    font-size: {px(m.BODY)}px;
    selection-background-color: {q["primary"]};
    selection-color: {q["onPrimary"]};
}}
QLineEdit:disabled, QAbstractSpinBox:disabled {{
    color: {q["label3"]};
}}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    width: 0px;
    border: none;
}}
QPlainTextEdit#LogBox {{
    background: transparent;
    border: none;
    color: {q["label1"]};
    selection-background-color: {q["primary"]};
    selection-color: {q["onPrimary"]};
}}
QComboBox {{
    background: transparent;
    border: none;
    color: {q["label1"]};
    font-size: {px(m.BODY)}px;
}}
/* 下拉列表：浮层底色，行由 widgets._PopupDelegate 画。外层容器也得清掉边框，不然多一圈方框。 */
QComboBoxPrivateContainer {{
    background: {q["surfaceTop"]};
    border: none;
}}
QComboBox QAbstractItemView {{
    background: {q["surfaceTop"]};
    color: {q["label1"]};
    border: none;
    outline: none;
    padding: {m.GAP_RELATED}px;
}}

/* ===== 滚动 ===== 细、贴边、悬停变宽，不完全隐藏（16.4） */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea#PageScroll > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {q["controlTrack"]};
    border-radius: 2px;
    min-height: 32px;
    margin: 6px 4px 6px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {q["controlTrack"]};
    border-radius: 2px;
    min-width: 32px;
    margin: 4px 6px 4px 6px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {q["label3"]};
    border-radius: 3px;
    margin: 4px 3px 4px 3px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ===== 浮层 ===== 菜单窗口的圆角交给系统（winapi.round_corners） */
QMenu {{
    background: {q["surfaceTop"]};
    color: {q["label1"]};
    border: none;
    padding: {m.GAP_RELATED}px;
    font-size: {px(m.BODY)}px;
}}
QMenu::item {{
    padding: 6px {m.PAD_CONTROL_X + m.GAP_INLINE}px 6px {m.PAD_CONTROL_X}px;
    border-radius: {m.RADIUS_SMALL}px;
    min-width: {m.MENU_MIN_WIDTH - 2 * m.PAD_CONTROL_X}px;
}}
QMenu::item:selected {{
    background: {q["hover"]};
}}
QMenu::item:disabled {{
    color: {q["label3"]};
}}
QMenu::separator {{
    height: 1px;
    background: {q["divider"]};
    margin: {m.GAP_RELATED}px {m.PAD_CONTROL_X}px;
}}
QToolTip {{
    background: {q["surfaceTop"]};
    color: {q["label1"]};
    border: 1px solid {q["divider"]};
    border-radius: {m.RADIUS_SMALL}px;
    padding: {m.GAP_RELATED}px {m.GAP_INLINE}px;
    font-size: {px(m.SECONDARY)}px;
}}
"""
