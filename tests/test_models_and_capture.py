# -*- coding: utf-8 -*-
"""判定数换算得分、配置序列化、结算画面识别。"""

from __future__ import annotations

from core import capture
from core.models import CunConfig, JudgeCounts, OcrRecord


# ----------------------------- 得分换算 -------------------------------------
def test_all_justice_is_a_perfect_score():
    assert JudgeCounts(critical=1000, justice=0, attack=0, miss=0).score == 1_010_000


def test_the_weights_are_101_100_50_0():
    """1000 物量下，各判定各占一份的权重。"""
    assert JudgeCounts(critical=0, justice=1000).score == 1_000_000
    assert JudgeCounts(attack=1000).score == 500_000
    assert JudgeCounts(miss=1000).score == 0


def test_an_empty_chart_scores_zero_instead_of_dividing_by_zero():
    assert JudgeCounts().score == 0
    assert JudgeCounts().total == 0


def test_one_justice_out_of_a_thousand_costs_ten_points():
    full = JudgeCounts(critical=1000).score
    one_off = JudgeCounts(critical=999, justice=1).score
    assert full - one_off == 10


def test_the_score_truncates_instead_of_rounding():
    """游戏显示的是截断值。

    在 150 张真实结算截图上，用顶栏的判定数按公式反算，截断值 149 次与画面上
    的得分完全一致；四舍五入会高 1 分。v1.x 用的是四舍五入，所以联动那条路
    换算的分数系统性偏高，在评级边界上会改判。
    """
    # 2 JC + 1 JUSTICE：精确值 1,006,666.67，四舍五入会给 1,006,667
    assert JudgeCounts(critical=2, justice=1).score == 1_006_666


def test_an_all_justice_run_is_exactly_full_marks_even_at_awkward_note_counts():
    """截断必须走整数运算，否则全 JC 会被算成差 1 分。

    实测有 48 组判定数会踩到：``int(1e6 * (1.01*jc + ...) / total)`` 在
    129 物量全 JC 时给出 1,009,999 而不是 1,010,000。
    """
    assert JudgeCounts(critical=129).score == 1_010_000
    for notes in (2, 4, 16, 32, 65, 129, 1000):
        assert JudgeCounts(critical=notes).score == 1_010_000, notes


# ----------------------------- 配置序列化 -----------------------------------
def test_optional_rule_fields_are_omitted_when_unset():
    """None 的字段不写进 JSON，配置文件才不会长满 null。"""
    from core.models import Category
    d = Category(key="AJ寸", kind="ajcun", m_hi=4).to_dict()
    assert "m_hi" in d
    assert "lo" not in d and "min_rank" not in d
    assert "custom" not in d                      # False 也不写


def test_a_config_survives_a_dict_round_trip():
    cfg = CunConfig()
    cfg.capture.delay_s = 3.0
    cfg.boxes["top_line1"] = [1, 2, 3, 4]
    back = CunConfig.from_dict(cfg.to_dict())
    assert back.capture.delay_s == 3.0
    assert back.boxes["top_line1"] == [1, 2, 3, 4]
    assert back.rank_thresholds == cfg.rank_thresholds


def test_garbage_values_fall_back_to_defaults():
    cfg = CunConfig.from_dict({"game_poll_sec": "不是数字", "dghub": {"port": None},
                               "expected_size": "坏的", "organize": 42})
    assert cfg.game_poll_sec == 4.0
    assert cfg.dghub.port == 8890
    assert cfg.expected_size == [1920, 1080]
    assert len(cfg.organize.steps) == 3


def test_an_ocr_record_without_a_size_omits_the_key():
    assert "size" not in OcrRecord(score=1, attack=0, miss=0).to_dict()
    assert OcrRecord(score=1, size=7).to_dict()["size"] == 7


# ----------------------------- 结算画面识别 ---------------------------------
#: 两个版本的背景主题色：2.50 之前是浅蓝，2.50 换成了黄色
_OLD_THEME = (226, 238, 252)
_NEW_THEME = (255, 250, 225)


def _frame(width: int = 1920, height: int = 1080,
           fill: tuple[int, int, int] = (0, 0, 0)) -> capture.Frame:
    r, g, b = fill
    return capture.Frame(bytes([b, g, r, 255]) * (width * height), width, height)


def _paint(frame: capture.Frame, rect: tuple[int, int, int, int],
           rgb: tuple[int, int, int], every: int = 1) -> capture.Frame:
    """在 1920×1080 坐标的矩形里涂色（按帧的实际分辨率缩放）；``every`` 隔列涂，用来做条纹。"""
    sx, sy = frame.width / 1920, frame.height / 1080
    x1, y1, x2, y2 = (int(rect[0] * sx), int(rect[1] * sy),
                      int(rect[2] * sx), int(rect[3] * sy))
    buf = bytearray(frame.buf)
    px = bytes([rgb[2], rgb[1], rgb[0], 255])
    for y in range(y1, y2):
        row = y * frame.width
        for x in range(x1, x2, every):
            i = (row + x) * 4
            buf[i:i + 4] = px
    return capture.Frame(bytes(buf), frame.width, frame.height)


def _in_song(background: tuple[int, int, int], width: int = 1920,
             height: int = 1080) -> capture.Frame:
    """打歌、CLEAR 过场、成绩画面共有的样子：背景 + 顶栏那段黄字黑底。"""
    frame = _frame(width, height, background)
    frame = _paint(frame, capture.CHROME_RECT, (0, 0, 0))
    return _paint(frame, capture.CHROME_RECT, (239, 203, 33), every=3)


def _result(background: tuple[int, int, int], width: int = 1920,
            height: int = 1080) -> capture.Frame:
    frame = _in_song(background, width, height)
    frame = _paint(frame, capture.OVERLAY_BAND_RECT, (250, 250, 252))    # 浅色面板
    return _paint(frame, (640, 655, 910, 845), (106, 46, 177))            # 判定明细面板


def test_a_black_frame_matches_nothing():
    frame = _frame()
    assert capture.stage(frame) == capture.STAGE_NONE
    assert not capture.is_result_screen(frame)


def test_the_chrome_alone_is_not_enough_to_be_a_result_screen():
    """CLEAR 过场和成绩画面共享全部顶部 chrome，只有判定面板能分开它们。

    这一条对着的是实机上真发生过的误截：指纹全中，截到的却是 CLEAR。
    """
    frame = _in_song(_OLD_THEME)
    assert capture.chrome_present(frame)
    assert capture.stage(frame) == capture.STAGE_CHROME
    assert not capture.is_result_screen(frame)


def test_a_result_screen_is_recognised_whatever_the_version_theme():
    """游戏 2.50 把背景从浅蓝换成了黄色，旧指纹从 17/17 掉到 6/17，一张都截不到。

    识别只能看跨版本不变的元素，背景换什么颜色都不该影响结果。
    """
    for background in (_OLD_THEME, _NEW_THEME, (40, 40, 60)):
        assert capture.is_result_screen(_result(background)), background


def test_a_result_screen_under_the_celebration_banner_is_not_saved_yet():
    """刷新纪录时那块深色横幅会盖住画面中间，那一帧存下来是坏图，要等它过去。"""
    frame = _paint(_result(_NEW_THEME), (570, 444, 1350, 636), (35, 45, 65))
    assert capture.judge_panel_looks_right(frame)
    assert capture.overlay_covers_panels(frame)
    assert capture.stage(frame) == capture.STAGE_PANEL
    assert not capture.is_result_screen(frame)


def test_a_purple_play_field_without_the_top_bar_is_not_a_result():
    """判定面板那块碰巧是紫色的别的画面（选曲、地图）没有顶栏，也不能当成绩画面。"""
    frame = _paint(_frame(fill=_NEW_THEME), (640, 655, 910, 845), (106, 46, 177))
    assert capture.judge_panel_looks_right(frame)
    assert not capture.is_result_screen(frame)


def test_detection_scales_with_the_resolution():
    """24 寸映射补丁把游戏窗口拉到 3413×1920，坐标要按比例换算。"""
    assert capture.is_result_screen(_result(_NEW_THEME, 3413, 1920))
    assert not capture.is_result_screen(_in_song(_NEW_THEME, 3413, 1920))
