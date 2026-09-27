# -*- coding: utf-8 -*-
"""主题的验收：颜色和设计库一致、对比度底线、键鼠密度的尺寸、QSS 里的雷区、弹簧。

这些断言钉的是**规范里的底线**，不是当前长相。改配色时它们会红，那正是要的。

对比度按合成后的实际颜色算：暗色卡片是 10% 白，叠在页面底上才是看到的颜色。
Mica 的真实亮度跟着壁纸走，这里拿它的实色回退 bgGrouped 当底。
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from ui.theme import metrics, qss, spring, tokens

ROOT = Path(__file__).resolve().parent.parent
KIT = Path.home() / "Workspace" / "code" / "coloros-ui-kit" / "tokens" / "coloros17.json"
MODES = {"light": tokens.LIGHT, "dark": tokens.DARK}


# ----------------------------- 色彩计算 -------------------------------------
def _argb(h: str) -> tuple[float, int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16) / 255, int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)


def over(top: str, bottom: str) -> str:
    """半透明叠到不透明底上，返回不透明结果。"""
    a, r, g, b = _argb(top)
    _, r2, g2, b2 = _argb(bottom)
    mix = [round(c * a + d * (1 - a)) for c, d in ((r, r2), (g, g2), (b, b2))]
    return "#FF" + "".join(f"{c:02X}" for c in mix)


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def contrast(fg: str, bg: str) -> float:
    def lum(h: str) -> float:
        _, r, g, b = _argb(h)
        return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)
    la, lb = lum(fg), lum(bg)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def faces(t: dict[str, str]) -> dict[str, str]:
    """文字实际落在的几种面（合成后）。"""
    page = over(t["bgGrouped"], "#FFFFFFFF")
    panel = over(t["surfaceGrouped"], page)
    return {"页面底": page, "卡片": over(t["card"], page), "内容面": over(t["contentSurface"], page),
            "浮层": over(t["surfaceTop"], page), "面板": panel, "面板里的卡片": over(t["card"], panel)}


# ----------------------------- 与设计库一致 ---------------------------------
def test_light_and_dark_define_exactly_the_same_tokens():
    """少一个键，那个模式下就是 KeyError。"""
    assert set(tokens.LIGHT) == set(tokens.DARK)
    assert set(tokens.KIT_SOURCE) == set(tokens.LIGHT), "每个颜色都要登记来源"


def test_every_colour_is_a_concrete_argb_value():
    for mode, table in MODES.items():
        for key, value in table.items():
            assert re.fullmatch(r"#[0-9A-F]{8}", value), f"{mode}.{key} 不是 #AARRGGBB：{value}"


def test_the_project_records_which_design_system_revision_it_follows():
    """跨项目视觉对比只在 Revision 一致时才成立，所以必须写下来。"""
    assert tokens.DESIGN_SYSTEM_REVISION == "2026.09.26-coloros17"


def test_every_deviation_from_the_design_library_carries_a_reason():
    assert tokens.OVERRIDES
    for item, value, reason in tokens.OVERRIDES:
        assert item and value, item
        assert len(reason) > 20, f"{item} 的原因写得太糊：{reason}"


def _kit() -> dict:
    if not KIT.is_file():
        pytest.skip(f"本机没有设计库 {KIT}（CI 上正常）")
    return json.loads(KIT.read_text(encoding="utf-8"))


def _kit_value(kit: dict, path: str):
    cur = kit
    for part in path.split("."):
        cur = cur[part]
    return cur


def test_colours_are_the_design_library_values():
    """颜色一律取设计库原值，不在项目里另调一套（DESIGN.md 第 1 章）。"""
    kit = _kit()
    for key, path in tokens.KIT_SOURCE.items():
        if path is None:
            continue
        want = _kit_value(kit, path)
        if isinstance(want, str):
            want = {"light": want, "dark": want}
        assert tokens.LIGHT[key] == want["light"], f"light.{key} 和设计库 {path} 不一致"
        assert tokens.DARK[key] == want["dark"], f"dark.{key} 和设计库 {path} 不一致"


def test_springs_and_durations_are_the_design_library_values():
    kit = _kit()
    for name, path in metrics.SPRING_KIT.items():
        want = _kit_value(kit, path)
        assert metrics.SPRINGS[name] == (want["bounce"], want["response"]), name
    assert f"{metrics.DIALOG_IN_MS}ms" == kit["dialog"]["enterDuration"]
    assert f"{metrics.DIALOG_OUT_MS}ms" == kit["dialog"]["exitDurationCenter"]
    assert metrics.DIALOG_SCALE_FROM == kit["dialog"]["enterScale"]
    assert f"{metrics.TOAST_MS}ms" == kit["snackBar"]["duration"]
    assert f"{metrics.SWITCH_WIDTH}dp" == kit["switch"]["width"]
    assert f"{metrics.SWITCH_HEIGHT}dp" == kit["switch"]["height"]
    assert f"{metrics.SWITCH_THUMB}dp" == kit["switch"]["thumbSize"]


# ----------------------------- 对比度 ---------------------------------------
def test_body_text_is_readable_on_every_surface_it_lands_on():
    for mode, t in MODES.items():
        for name, bg in faces(t).items():
            got = contrast(over(t["label1"], bg), bg)
            assert got >= 4.5, f"{mode} label1 在{name}上只有 {got:.2f}:1"


def test_secondary_text_is_readable_except_the_registered_library_deviation():
    """label2 叠在亮色 #F0F1F2 上是 4.46:1（页面底、面板底都是这个色），设计库原值，
    登记在 OVERRIDES 里；别处都要 4.5。"""
    for mode, t in MODES.items():
        for name, bg in faces(t).items():
            got = contrast(over(t["label2"], bg), bg)
            floor = 4.4 if mode == "light" and name in ("页面底", "面板") else 4.5
            assert got >= floor, f"{mode} label2 在{name}上只有 {got:.2f}:1"


def test_error_text_is_readable_where_errors_are_written():
    """红字只写在页面的卡片和内容面上（行内错误）。面板里的区间填错不出红字：
    上下限互相夹住，填不出错的值。"""
    for mode, t in MODES.items():
        for name in ("卡片", "内容面"):
            bg = faces(t)[name]
            got = contrast(t["error"], bg)
            assert got >= 4.5, f"{mode} error 在{name}上只有 {got:.2f}:1"


def test_the_focus_ring_reaches_three_to_one_everywhere():
    """16.4：主题色对相邻底色不到 3:1 时焦点环改用 label1（COUI 橙在白底上只有 2.7:1）。"""
    for mode, t in MODES.items():
        for name, bg in faces(t).items():
            got = contrast(over(t["focusRing"], bg), bg)
            assert got >= 3.0, f"{mode} 焦点环在{name}上只有 {got:.2f}:1"


def test_primary_button_text_does_not_get_worse_than_the_coui_orange_original():
    """白字配 COUI 橙是 2.66:1（登记在 OVERRIDES）。换主题色不许比这更差。"""
    for mode, t in MODES.items():
        got = contrast(t["onPrimary"], over(t["primary"], faces(t)["页面底"]))
        assert got >= 2.6, f"{mode} 主色按钮文字只有 {got:.2f}:1"


# ----------------------------- 字阶与尺寸 -----------------------------------
def test_typography_is_the_desktop_density_of_chapter_16():
    """16.1：页面标题 24 / 600，设置项标题 14 / 500，正文 14，摘要 12，分组标题 12 / 500。"""
    assert metrics.PAGE_TITLE[::2] == (24, 600)
    assert metrics.TITLE[::2] == (14, 500)
    assert metrics.BODY.size == 14
    assert metrics.SECONDARY.size == 12
    assert metrics.GROUP_TITLE[::2] == (12, 500)
    assert metrics.BUTTON[::2] == (14, 500)
    for role, spec in metrics.FONT_ROLES.items():
        assert isinstance(spec.size, int) and spec.line_height > spec.size, role
        assert spec.weight in (400, 500, 600), f"{role}：字重只有 400 / 500 / 600 三档"


def test_sizes_are_the_desktop_density_of_chapter_16():
    assert (metrics.BUTTON_HEIGHT, metrics.BUTTON_SMALL) == (32, 28)
    assert metrics.INPUT_HEIGHT == 32
    assert (metrics.SETTING_ROW, metrics.SETTING_ROW_WITH_DESC) == (40, 58)
    assert (metrics.NAV_EXPANDED, metrics.NAV_RAIL, metrics.NAV_ITEM) == (224, 72, 40)
    assert metrics.CONTENT_MAX_WIDTH == 720
    assert (metrics.BREAK_MEDIUM, metrics.BREAK_EXPANDED) == (600, 840)
    assert (metrics.RADIUS_CARD, metrics.RADIUS_MENU, metrics.RADIUS_DIALOG) == (16, 12, 24)
    # 16.9 的最小验收尺寸：窗口至少要能缩到 640×480
    assert (metrics.WINDOW_MIN_WIDTH, metrics.WINDOW_MIN_HEIGHT) == (640, 480)


def test_a_setting_row_is_exactly_its_floor_height():
    """行高由文字列的上下内边距撑出来：单行 10 + 20 + 10 = 40，带摘要 10 + 20 + 2 + 16 + 10 = 58。"""
    pad = metrics.PAD_CONTROL_Y
    assert 2 * pad + metrics.TITLE.line_height == metrics.SETTING_ROW
    assert (2 * pad + metrics.TITLE.line_height + 2 + metrics.SECONDARY.line_height
            == metrics.SETTING_ROW_WITH_DESC)


# ----------------------------- QSS ------------------------------------------
def _selectors(sheet: str) -> list[str]:
    out: list[str] = []
    for block in sheet.split("{"):
        head = block.rsplit("}", 1)[-1]
        head = re.sub(r"/\*.*?\*/", " ", head, flags=re.S)
        out += [s.strip() for s in head.split(",") if s.strip()]
    return out


def test_the_stylesheet_never_uses_an_unqualified_qwidget_selector():
    """Qt 的类型选择器连子类一起命中：``QWidget { background }`` 会把每个 QLabel 都刷上底色。"""
    for mode, t in MODES.items():
        for sel in _selectors(qss.build(t)):
            first = sel.split()[0]
            assert not re.fullmatch(r"QWidget(:[\w-]+)?", first), f"{mode}：{sel}"


def test_the_stylesheet_resolves_every_token_it_mentions():
    for t in MODES.values():
        sheet = qss.build(t, 1.5)
        assert "None" not in sheet and "#" not in sheet.replace("QWidget#", "") \
            .replace("QListWidget#", "").replace("QStackedWidget#", "") \
            .replace("QPlainTextEdit#", "").replace("QScrollArea#", ""), "颜色要转成 rgba()"
        for line in sheet.splitlines():
            if ":" in line and "{" not in line and not line.strip().startswith("/*"):
                assert line.split(":", 1)[1].strip().rstrip(";"), f"空值：{line!r}"


def test_focus_is_not_left_to_qss():
    """QSS 不支持 outline / outline-offset（实测被静默忽略）；焦点环归 FocusTracker。"""
    sheet = qss.build(tokens.DARK)
    assert "outline-offset" not in sheet
    assert ":focus" not in sheet


def test_text_scale_multiplies_font_sizes_once():
    sheet = qss.build(tokens.LIGHT, 1.5)
    assert f"font-size: {round(metrics.PAGE_TITLE.size * 1.5)}px" in sheet
    assert f"font-size: {round(metrics.BODY.size * 1.5)}px" in sheet


# ----------------------------- 弹簧 -----------------------------------------
def test_a_critically_damped_spring_never_overshoots():
    s = spring.Spring(0.0, 0.3)
    xs = [spring.state(s, -1.0, 0.0, i / 200)[0] for i in range(200)]
    assert all(b >= a - 1e-9 for a, b in zip(xs, xs[1:]))
    assert max(xs) <= 1e-9


def test_a_bouncy_spring_overshoots_by_the_textbook_amount():
    s = spring.Spring(0.3, 0.4)
    z = s.zeta
    want = math.exp(-z * math.pi / math.sqrt(1 - z * z))
    peak = max(spring.state(s, -1.0, 0.0, i / 10000)[0] for i in range(10000))
    assert abs(peak - want) < 1e-3


def test_retargeting_keeps_position_and_velocity_continuous():
    m = spring.Motion(0.0)
    m.to(1.0, spring.Spring(0.3, 0.4))
    for _ in range(6):
        m.step(1 / 60)
    before = (m.value, m.velocity)
    m.to(0.0, spring.Spring(0.0, 0.3))
    assert (m.value, m.velocity) == before, "换目标的那一刻位置和速度不能跳"
    for _ in range(600):
        if not m.step(1 / 60):
            break
    assert not m.moving and m.value == 0.0
