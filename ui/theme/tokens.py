# -*- coding: utf-8 -*-
"""颜色。**纯数据，不 import PySide6。**

值是 ColorOS 17 设计库 ``~\\Workspace\\code\\coloros-ui-kit\\tokens\\coloros17.json`` 的
**原值**（``#AARRGGBB``，很多带透明度），抄过来是因为装到用户机器上的程序读不到那个
私有仓库。``KIT_SOURCE`` 记着每个键在设计库里的路径，设计库在本机时
``tests/test_theme.py`` 逐项比对，漂了就红。

主题色用 COUI 自带的橙（``Theme.COUI.Orange``，笔记、计算器、指南针用的那一套），
接着寸录一直以来的橙色身份。主题色只点一处（主操作），别拿来铺底、给正文上色。

⚠️ **Light 与 Dark 的键集合必须完全一致。** 少一个键就是那个模式下 KeyError。
"""

from __future__ import annotations

#: 本项目遵循的全局规范版本。跨项目视觉对比只在这个值一致时才成立。
DESIGN_SYSTEM_REVISION = "2026.09.26-coloros17"

#: 每个键来自设计库的哪里。``None`` 是 DESIGN.md 第 16 章自定、设计库里没有的角色。
KIT_SOURCE: dict[str, str | None] = {
    # 主题色一族：COUI 橙
    "primary": "themeColor.orange.primary",
    "primaryText": "themeColor.orange.primaryText",
    "primaryContainer": "themeColor.orange.primaryContainer",
    "primaryDisabled": "themeColor.orange.primaryDisabled",
    "focus": "themeColor.orange.focus",
    "onPrimary": "color.onPrimary",
    # 文字四级里用到的三级
    "label1": "color.label1",
    "label2": "color.label2",
    "label3": "color.label3",
    # 面
    "bgGrouped": "color.bgGrouped",
    "surface": "color.surface",
    "surfaceTop": "color.surfaceTop",
    "surfaceGrouped": "color.surfaceGrouped",
    "card": "color.card",
    # 填充、分割、蒙层
    "fill8": "color.fill8",
    "controlTrack": "color.controlTrack",
    "divider": "color.divider",
    "hover": "color.hover",
    "press": "color.press",
    "scrim": "color.scrim",
    "error": "color.error",
    # 组件
    "button.secondaryBg": "button.secondaryBg",
    "button.secondaryDisabledBg": "button.secondaryDisabledBg",
    "button.onPrimaryDisabled": "button.onPrimaryDisabled",
    "switch.thumb": "switch.thumb",
    "switch.thumbShadowColor": "switch.thumbShadowColor",
    "snackBar.bg": "snackBar.bg",
    # DESIGN.md 16.3 / 16.4 自定
    "focusRing": None,
    "contentSurface": None,
}

LIGHT: dict[str, str] = {
    "primary": "#FFFF7700",
    "primaryText": "#FFEB6E00",
    "primaryContainer": "#26FF7700",
    "primaryDisabled": "#4DFF7700",
    "focus": "#1FFF7700",
    "onPrimary": "#FFFFFFFF",
    "label1": "#E6000000",
    "label2": "#8A000000",
    "label3": "#42000000",
    "bgGrouped": "#FFF0F1F2",
    "surface": "#FFFFFFFF",
    "surfaceTop": "#FFFFFFFF",
    "surfaceGrouped": "#FFF0F1F2",
    "card": "#FFFFFFFF",
    "fill8": "#14000000",
    "controlTrack": "#29000000",
    "divider": "#1F000000",
    "hover": "#14000000",
    "press": "#1F000000",
    "scrim": "#33000000",
    "error": "#FFDB382C",
    "button.secondaryBg": "#FFEBEBEB",
    "button.secondaryDisabledBg": "#14000000",
    "button.onPrimaryDisabled": "#8AFFFFFF",
    "switch.thumb": "#FFFFFFFF",
    "switch.thumbShadowColor": "#19000000",
    "snackBar.bg": "#FFFFFFFF",
    # 焦点环：COUI 橙在白底上只有 2.7:1，不到 3:1，按 16.4 换成 label1
    "focusRing": "#E6000000",
    # 平铺内容（曲线、日志）的实色底：亮色白
    "contentSurface": "#FFFFFFFF",
}

DARK: dict[str, str] = {
    "primary": "#FFF08222",
    "primaryText": "#FFF08222",
    "primaryContainer": "#40F08222",
    "primaryDisabled": "#66F08222",
    "focus": "#33F08222",
    "onPrimary": "#FFFFFFFF",
    "label1": "#E6FFFFFF",
    "label2": "#8AFFFFFF",
    "label3": "#4DFFFFFF",
    "bgGrouped": "#FF000000",
    "surface": "#FF1E1E1E",
    "surfaceTop": "#FF333333",
    "surfaceGrouped": "#FF1E1E1E",
    "card": "#1AFFFFFF",
    "fill8": "#1AFFFFFF",
    "controlTrack": "#40FFFFFF",
    "divider": "#33FFFFFF",
    "hover": "#26FFFFFF",
    "press": "#33FFFFFF",
    "scrim": "#99000000",
    "error": "#FFFF6C61",
    "button.secondaryBg": "#FF343434",
    "button.secondaryDisabledBg": "#1AFFFFFF",
    "button.onPrimaryDisabled": "#28FFFFFF",
    "switch.thumb": "#FFFFFFFF",
    "switch.thumbShadowColor": "#19000000",
    "snackBar.bg": "#FF333333",
    # 暗底上橙色够 3:1，焦点环直接用主题色
    "focusRing": "#FFF08222",
    # 暗色的内容面是 Surface #1E1E1E，不用纯黑：纯黑放在 Mica 上像个黑洞（16.3）
    "contentSurface": "#FF1E1E1E",
}

#: 覆盖与偏差登记：和设计库、DESIGN.md 默认不一样的地方，写出确定值与原因。
OVERRIDES: tuple[tuple[str, str, str], ...] = (
    ("focusRing（亮色）", "label1 #E6000000",
     "DESIGN.md 16.4：主题色和相邻底色对比不到 3:1 时焦点环改用 Label Primary。"
     "COUI 橙 #FF7700 在白底上只有 2.7:1，暗色下 #F08222 够 3:1，照用主题色。"),
    ("onPrimary 叠在 primary 上", "2.66:1（亮暗都是）",
     "COUI 橙主题的原值：白字配 #FF7700 / #F08222。2026-09-24 定下组件照 COUI 原样、"
     "不自行改色，主色按钮只在每屏一个主操作上用，文字 14 / 500。不再往下掉由测试守着。"),
    ("label2 叠在亮色页面底和面板底", "4.46:1",
     "设计库原值（label2 #8A000000 叠在 #F0F1F2 上）。只影响直接写在页面底、面板底上的分组标题"
     "和页脚，卡片上是 4.9:1。设计库照 COUI 原样，这里不改。"),
    ("mono 字阶", "12 / 18 / 400，等宽字体",
     "COUI 没有等宽字阶。「记录」页的日志要按列对齐时间和数字，按 bodyXS 的字号给一档等宽。"),
    ("统计页的大数字", "36 / 50 / 600（displayM）",
     "DESIGN.md 第 5 章「大数字」一档：闹钟列表时间 36dp。四块汇总各占 170 宽左右，放得下五位数。"),
)
