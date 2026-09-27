# -*- coding: utf-8 -*-
"""字阶、间距、圆角、尺寸、动效、阴影。**纯数据，不 import PySide6。**

数值是全局 DESIGN.md 第 16 章的键鼠密度（电脑端比手机的 COUI 原尺寸收一档：按钮 32、
设置行 40 / 58、字号 14 / 12），字阶取自 COUI。带 ``KIT`` 注释的动效参数和设计库
``coloros17.json`` 逐项比对（``tests/test_theme.py``）。

⚠️ **字号一律按像素给**（``setPixelSize`` / QSS 的 ``px``）。这里的数字是**逻辑**
像素：Qt 6 的高 DPI 缩放会把它们按显示缩放放大。写 ``pt`` 会让 Qt 在 Windows 上
按 96 DPI 换算，14 变成 18，整屏字大一圈（v2.0 就是这样）。

Windows 的辅助功能「文本大小」是**另一个**设置，Qt 不会自动应用。
:func:`ui.theme.font` 读一次系统的 TextScaleFactor 自己乘上去，只此一处。
"""

from __future__ import annotations

from typing import NamedTuple


class FontSpec(NamedTuple):
    """一个排版角色。``weight`` 用 CSS 数值，映射到 Qt 在门面里做。"""

    size: int
    line_height: int
    weight: int


REGULAR, MEDIUM, SEMIBOLD = 400, 500, 600

# ----------------------------- 字阶（16.1）----------------------------------
PAGE_TITLE = FontSpec(24, 34, SEMIBOLD)       # DisplayXS，固定不折叠
DIALOG_TITLE = FontSpec(18, 24, SEMIBOLD)
EMPTY_TITLE = FontSpec(16, 22, MEDIUM)
TITLE = FontSpec(14, 20, MEDIUM)              # 设置项、列表项标题
BODY = FontSpec(14, 20, REGULAR)              # BodyM
BUTTON = FontSpec(14, 20, MEDIUM)
SECONDARY = FontSpec(12, 16, REGULAR)         # 摘要、元信息、页脚
GROUP_TITLE = FontSpec(12, 16, MEDIUM)        # 分组标题，次要色
CAPTION = FontSpec(10, 14, REGULAR)
METRIC = FontSpec(36, 50, SEMIBOLD)           # DisplayM，大数字
MONO = FontSpec(12, 18, REGULAR)              # 日志，项目自定（见 tokens.OVERRIDES）

FONT_ROLES: dict[str, FontSpec] = {
    "pageTitle": PAGE_TITLE, "dialogTitle": DIALOG_TITLE, "emptyTitle": EMPTY_TITLE,
    "title": TITLE, "body": BODY, "button": BUTTON, "secondary": SECONDARY,
    "groupTitle": GROUP_TITLE, "caption": CAPTION, "metric": METRIC, "mono": MONO,
}

# ----------------------------- 间距 -----------------------------------------
GAP_RELATED = 4         # 标题与摘要、值与单位
GAP_INLINE = 8          # 图标与文字、分组标题与卡片
GAP_CONTROL = 8         # 同组相邻控件
GAP_CARD = 12           # 卡片之间
GAP_GROUP = 16          # 行内标题与控件
GAP_SECTION = 32        # 分组之间（含分组标题）

PAD_CONTROL_X = 16      # 按钮、输入框、设置行左右
PAD_CONTROL_Y = 10      # 设置行上下
PAD_CONTAINER = 16      # 卡片内边距

#: 页边距跟着窗口类走（16.2）：≥840 为 40，600～840 为 24，更窄 16
PAGE_MARGIN_EXPANDED = 40
PAGE_MARGIN_MEDIUM = 24
PAGE_MARGIN_COMPACT = 16
PAGE_TOP = 20           # 页面标题上方
PAGE_BOTTOM = 32        # 列表末尾留白

# ----------------------------- 圆角（16.1）----------------------------------
RADIUS_SMALL = 8        # 卡内小卡、菜单项
RADIUS_MENU = 12        # 菜单、侧栏选中底
RADIUS_CARD = 16        # 卡片
RADIUS_DIALOG = 24      # 对话框、居中面板
# 控件是胶囊：半径 = 高 / 2，由控件自己算

# ----------------------------- 尺寸（16.1 / 16.2）---------------------------
BREAK_MEDIUM = 600
BREAK_EXPANDED = 840
NAV_EXPANDED = 224      # COUISidePaneLayout
NAV_RAIL = 72           # COUINavigationRailView
NAV_ITEM = 40
CONTENT_MAX_WIDTH = 720

BUTTON_HEIGHT = 32
BUTTON_SMALL = 28
BUTTON_MIN_WIDTH = 72
ICON_BUTTON = 32        # 纯图标按钮的命中区
ICON_ACTION = 20
ICON_INLINE = 16
INPUT_HEIGHT = 32
SETTING_ROW = 40
SETTING_ROW_WITH_DESC = 58
MENU_ITEM = 32
MENU_MIN_WIDTH = 160
SWITCH_WIDTH = 44       # KIT switch.width
SWITCH_HEIGHT = 24      # KIT switch.height
SWITCH_THUMB = 18       # KIT switch.thumbSize
DIALOG_WIDTH = 360      # KIT dialog.maxWidth
PANEL_MAX_WIDTH = 540   # 手机的底部面板在电脑上居中浮起（16.5）
DIALOG_PADDING = 24
TOAST_BOTTOM = 24

FOCUS_RING_WIDTH = 2
FOCUS_RING_OFFSET = 2

WINDOW_WIDTH = 1120
WINDOW_HEIGHT = 760
#: 16.9 的验收尺寸下限。再窄就要做临时抽屉，这个程序用不上，窗口不让缩到那么窄。
WINDOW_MIN_WIDTH = 640
WINDOW_MIN_HEIGHT = 480

# ----------------------------- 动效 -----------------------------------------
#: COUI 弹簧 (bounce, response)。换算 ζ = 1 − bounce、k = (2π / response)²（设计库 spec 07）。
SPRINGS: dict[str, tuple[float, float]] = {
    "state": (0.0, 0.3),        # KIT button.pressMask：悬停、按压蒙层
    "press": (0.0, 0.3),        # KIT touchMotion.candyPress：按下缩小
    "release": (0.5, 0.5),      # KIT touchMotion.candyRelease：松手弹回
    "switch": (0.3, 0.4),       # KIT switch.toggle
    "menu": (0.2, 0.4),         # KIT popupMenu.enterScale：菜单、下拉弹出，侧栏选中底滑动
    "toastIn": (0.0, 0.3),      # KIT snackBar.enter
    "toastOut": (0.0, 0.25),    # KIT snackBar.exit
    "page": (0.0, 0.3),         # 换页淡入，自定
}
#: 设计库里对应的路径，测试逐项比对
SPRING_KIT: dict[str, str] = {
    "state": "button.pressMask", "press": "touchMotion.candyPress",
    "release": "touchMotion.candyRelease", "switch": "switch.toggle",
    "menu": "popupMenu.enterScale", "toastIn": "snackBar.enter", "toastOut": "snackBar.exit",
}

DIALOG_IN_MS = 250              # KIT dialog.enterDuration
DIALOG_OUT_MS = 150             # KIT dialog.exitDurationCenter
DIALOG_IN_BEZIER = (0.3, 0.0, 0.1, 1.0)
DIALOG_OUT_BEZIER = (0.3, 0.0, 1.0, 1.0)
DIALOG_SCALE_FROM = 0.8         # KIT dialog.enterScale
TOAST_MS = 2500                 # KIT snackBar.duration
PRESS_SCALE = 0.96              # 桌面按钮按下缩小的幅度，自定
MENU_OFFSET = 6                 # 下拉弹出时从控件一侧滑出的距离，自定
TOOLTIP_DELAY_MS = 500


# ----------------------------- 阴影 -----------------------------------------
class Shadow(NamedTuple):
    """浮层阴影。COUI 的焦散阴影桌面上画不出来，这两档是自定的。"""

    y: int
    blur: int
    light: str
    dark: str


SHADOW_FLOAT = Shadow(4, 16, "#1F000000", "#80000000")     # Toast、菜单
SHADOW_DIALOG = Shadow(12, 40, "#2E000000", "#99000000")   # 对话框、面板
