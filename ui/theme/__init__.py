# -*- coding: utf-8 -*-
"""主题入口。业务代码只跟这个模块打交道：``from . import theme``。

- :mod:`~ui.theme.tokens`  颜色，设计库原值，纯数据
- :mod:`~ui.theme.metrics` 字阶、间距、圆角、尺寸、动效、阴影，纯数据
- :mod:`~ui.theme.qss`     颜色与字阶 → QSS，唯一拼样式表的地方
- :mod:`~ui.theme.spring`  COUI 弹簧的解析解
- 本文件                    当前模式、取色、取字体、蒙层合成、系统设置的接入

业务组件只消费这里的语义角色，不散写颜色、字号、间距、圆角、阴影与动画时长。

深浅两套是两份独立映射。模式来自配置里的 ``appearance``（``system`` / ``light`` /
``dark``），跟随系统时读 Qt 的 ``colorScheme()``。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette

from core import winapi

from . import metrics as m
from . import qss as _qss
from . import tokens as _tokens
from .metrics import (BODY, BUTTON, CAPTION, DIALOG_TITLE, EMPTY_TITLE,  # noqa: F401
                      GROUP_TITLE, METRIC, MONO, PAGE_TITLE, SECONDARY, TITLE, FontSpec)
from .tokens import DESIGN_SYSTEM_REVISION  # noqa: F401

#: 配置里 ``appearance`` 的三个取值
APPEARANCE_SYSTEM, APPEARANCE_LIGHT, APPEARANCE_DARK = "system", "light", "dark"
APPEARANCES = (APPEARANCE_SYSTEM, APPEARANCE_LIGHT, APPEARANCE_DARK)
APPEARANCE_LABELS = {APPEARANCE_SYSTEM: "跟随系统",
                     APPEARANCE_LIGHT: "浅色",
                     APPEARANCE_DARK: "深色"}

_appearance = APPEARANCE_SYSTEM
_dark = True
_scale = 1.0
_reduce_motion = False
_families: list[str] | None = None
_mono_families: list[str] | None = None

_CJK_FALLBACK = ("Microsoft YaHei UI", "微软雅黑", "PingFang SC", "Noto Sans CJK SC")
_MONO_FALLBACK = ("Cascadia Mono", "Consolas", "Microsoft YaHei UI", "微软雅黑")


# ----------------------------- 模式 -----------------------------------------
def system_prefers_dark() -> bool:
    """系统当前是不是深色。Qt 6.5 起 ``colorScheme()`` 直接给答案，拿不到就读注册表。"""
    app = QGuiApplication.instance()
    if app is not None:
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Light:
            return False
        if scheme == Qt.ColorScheme.Dark:
            return True
    light = winapi.apps_use_light_theme()
    return True if light is None else not light


def set_appearance(value: str) -> bool:
    """按配置值定下当前模式。返回模式是否发生了变化。"""
    global _appearance, _dark
    _appearance = value if value in APPEARANCES else APPEARANCE_SYSTEM
    dark = {APPEARANCE_LIGHT: False, APPEARANCE_DARK: True}.get(_appearance)
    if dark is None:
        dark = system_prefers_dark()
    changed = dark != _dark
    _dark = dark
    return changed


def appearance() -> str:
    return _appearance


def is_dark() -> bool:
    return _dark


def follows_system() -> bool:
    return _appearance == APPEARANCE_SYSTEM


def palette() -> dict[str, str]:
    return _tokens.DARK if _dark else _tokens.LIGHT


# ----------------------------- 取色 -----------------------------------------
def color(role: str) -> QColor:
    """颜色角色 → :class:`QColor`（``#AARRGGBB``，可能半透明）。

    拼错角色名要当场炸，不能静默返回空色——那会变成「界面塌了但什么都不报」。
    """
    return QColor(palette()[role])


def qss_color(role: str) -> str:
    return _qss.rgba(palette()[role])


def over(top: QColor, bottom: QColor) -> QColor:
    """把半透明颜色叠到底色上。底色也可以是半透明的。"""
    ta, ba = top.alphaF(), bottom.alphaF()
    a = ta + ba * (1 - ta)
    if a <= 0:
        return QColor(0, 0, 0, 0)

    def ch(t: float, b: float) -> float:
        return (t * ta + b * ba * (1 - ta)) / a

    return QColor.fromRgbF(ch(top.redF(), bottom.redF()), ch(top.greenF(), bottom.greenF()),
                           ch(top.blueF(), bottom.blueF()), a)


def state_color(base: str | QColor, *, hover: float = 0.0, pressed: float = 0.0) -> QColor:
    """底色叠上悬停、按压蒙层（亮 8% / 12% 黑，暗 15% / 20% 白）。

    ``hover`` / ``pressed`` 是 0～1 的进度，用来做淡入淡出。
    """
    c = base if isinstance(base, QColor) else color(base)
    for role, k in (("hover", hover), ("press", pressed)):
        if k > 0:
            mask = color(role)
            mask.setAlphaF(mask.alphaF() * min(1.0, k))
            c = over(mask, c)
    return c


# ----------------------------- 字体 -----------------------------------------
def _resolve_families() -> None:
    """系统界面字体打头，后面挂中文兜底。

    DESIGN.md 16.1：用系统默认界面字体，不替换成品牌字体。后面那几个只是兜底：
    Segoe UI 没有汉字字形，不挂兜底的话中文走系统默认回退，行高和西文对不齐。
    ``setFamilies`` 让 Qt **逐字符**回退，别写成「挑第一个装了的家族」。
    """
    global _families, _mono_families
    try:
        ui_family = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()
        mono_family = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
    except (RuntimeError, AttributeError):          # 没有 QGuiApplication
        ui_family = mono_family = ""
    _families = [f for f in (ui_family, *_CJK_FALLBACK) if f]
    _mono_families = [f for f in (mono_family, *_MONO_FALLBACK) if f]


def refresh_system_metrics() -> None:
    """重新读一次系统的文本缩放和减少动态。切换主题或系统设置变化时调。"""
    global _scale, _reduce_motion
    _scale = winapi.text_scale_factor()
    _reduce_motion = not winapi.animations_enabled()
    _resolve_families()


def _qt_weight(css_weight: int) -> QFont.Weight:
    return {400: QFont.Weight.Normal,
            500: QFont.Weight.Medium,
            600: QFont.Weight.DemiBold}.get(css_weight, QFont.Weight.Normal)


def font(spec: FontSpec = BODY, mono: bool = False) -> QFont:
    """按排版角色取字体。

    ``spec.size`` 是**逻辑**像素，Qt 6 的高 DPI 缩放会自己处理显示缩放。
    Windows「文本大小」是另一个设置，Qt 不管，所以在这里乘一次——只此一处。
    """
    if _families is None:
        _resolve_families()
    f = QFont()
    f.setFamilies(list(_mono_families if mono else _families))
    f.setPixelSize(max(1, round(spec.size * _scale)))
    f.setWeight(_qt_weight(spec.weight))
    return f


def line_height(spec: FontSpec) -> int:
    return max(1, round(spec.line_height * _scale))


def scaled(px: int) -> int:
    """行高、命中区这类必须装下文字的尺寸随文本大小一起长。纯间距不用这个。"""
    return max(px, round(px * _scale))


def text_scale() -> float:
    return _scale


def reduce_motion() -> bool:
    """系统关了「动画效果」：跟手、弹跳、位移全部直接到位（DESIGN.md 第 12 章）。"""
    return _reduce_motion


# ----------------------------- 阴影 -----------------------------------------
def shadow(spec: m.Shadow) -> tuple[QColor, int, int]:
    """浮层阴影 → (颜色, 模糊半径, 纵向偏移)。"""
    return QColor(spec.dark if _dark else spec.light), spec.blur, spec.y


# ----------------------------- 装上 -----------------------------------------
def qt_palette() -> QPalette:
    """原生控件的底色（滚动区视口、下拉列表、菜单这些 QSS 覆盖不全的地方）。"""
    p = QPalette()
    g, r = QPalette.ColorGroup, QPalette.ColorRole
    solid = color("contentSurface")
    for group in (g.Active, g.Inactive):
        p.setColor(group, r.Window, color("bgGrouped"))
        p.setColor(group, r.WindowText, color("label1"))
        p.setColor(group, r.Base, solid)
        p.setColor(group, r.AlternateBase, solid)
        p.setColor(group, r.Text, color("label1"))
        p.setColor(group, r.Button, color("button.secondaryBg"))
        p.setColor(group, r.ButtonText, color("label1"))
        p.setColor(group, r.Highlight, color("primary"))
        p.setColor(group, r.HighlightedText, color("onPrimary"))
        p.setColor(group, r.ToolTipBase, color("surfaceTop"))
        p.setColor(group, r.ToolTipText, color("label1"))
        p.setColor(group, r.PlaceholderText, color("label3"))
        p.setColor(group, r.Link, color("primaryText"))
    for role in (r.WindowText, r.Text, r.ButtonText):
        p.setColor(g.Disabled, role, color("label3"))
    p.setColor(g.Disabled, r.Base, solid)
    p.setColor(g.Disabled, r.Window, color("bgGrouped"))
    return p


def stylesheet() -> str:
    return _qss.build(palette(), _scale)


def apply(app) -> None:
    """把字体、调色板和样式表一起装上。切换深浅、系统设置变化都走这里。"""
    refresh_system_metrics()
    app.setFont(font(BODY))
    app.setPalette(qt_palette())
    app.setStyleSheet(stylesheet())
