# -*- coding: utf-8 -*-
"""界面逻辑：改完即存、规则面板、卡片里藏行。离屏跑，不开真窗口。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from core import config as config_mod  # noqa: E402
from core.models import Category, CunConfig  # noqa: E402

QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def app():
    from ui import theme
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    theme.apply(application)
    return application


class _FakeRunPage:
    def refresh_start_bat(self) -> None:
        pass


class _FakeMain:
    """ConfigPage 只用到主窗口的这几样。"""

    def __init__(self, cfg: CunConfig) -> None:
        self.cfg = cfg
        self.saves = 0
        self.toasts: list[tuple[str, object]] = []
        self.run_page = _FakeRunPage()

    def save_settings(self) -> None:
        self.saves += 1
        config_mod.save(self.cfg)

    def show_toast(self, text, *, error=False, action=None) -> None:
        self.toasts.append((text, action))

    def pick_folder(self, *_a) -> str:
        return ""

    def open_output(self) -> None:
        pass

    def rescan(self) -> None:
        pass

    def apply_appearance(self) -> None:
        pass


def _saved() -> CunConfig:
    config_mod.invalidate_cache()
    return config_mod.load()


def test_a_rule_switch_is_saved_the_moment_it_is_flipped(app, cfg, sss_rule):
    """DESIGN.md 11.2：开关改完立即生效并保存，页面上没有「保存」按钮。"""
    from ui.page_config import ConfigPage
    cfg.categories = [sss_rule]
    main = _FakeMain(cfg)
    page = ConfigPage(main)
    assert main.saves == 0, "搭界面时的程序化置位不该写盘"
    row = page.rules.card.rows[0]
    row.controls[0].click()
    assert main.saves == 1
    assert _saved().categories[0].enabled is False


def test_deleting_a_rule_saves_at_once_and_undo_puts_it_back_in_place(app, cfg):
    from ui.page_config import ConfigPage
    cfg.categories = [Category(key=k, label=k, kind="ajcun", enabled=True, folder=f"寸/{k}",
                               m_hi=4) for k in ("甲", "乙", "丙")]
    main = _FakeMain(cfg)
    page = ConfigPage(main)
    page._remove_rule(1)
    assert [c.key for c in _saved().categories] == ["甲", "丙"]
    text, (label, undo) = main.toasts[-1]
    assert "乙" in text and label == "撤销"
    undo()
    assert [c.key for c in _saved().categories] == ["甲", "乙", "丙"]


def test_moving_an_organize_step_saves_the_new_nesting(app, cfg):
    from ui.page_config import ConfigPage
    main = _FakeMain(cfg)
    page = ConfigPage(main)
    before = [s.kind for s in cfg.organize.steps]
    page._move(before[1], -1)
    after = [s.kind for s in _saved().organize.steps]
    assert after == [before[1], before[0], *before[2:]]


def test_the_port_is_saved_when_editing_finishes(app, cfg):
    from ui.page_config import ConfigPage
    main = _FakeMain(cfg)
    page = ConfigPage(main)
    page.dg_port.setValue(9000)
    assert _saved().dghub.port == 9000


def test_a_custom_score_range_cannot_be_turned_inside_out(app, cfg):
    """上下限互相夹住，填不出下限高于上限的区间。"""
    from ui.rule_dialog import RulePanel
    host = QtWidgets.QMainWindow()
    host.setCentralWidget(QtWidgets.QWidget())
    panel = RulePanel(host, cfg, set())
    panel.preset_box.setCurrentIndex(panel.preset_box.count() - 1)   # 自定义区间
    panel.lo_box.setValue(1_009_500)
    assert panel.lo_box.value() <= panel.hi_box.value()
    panel.hi_box.setValue(1_000_000)
    assert panel.hi_box.value() >= panel.lo_box.value()


def test_editing_a_rule_keeps_its_identity(app, cfg, sss_rule):
    from ui.rule_dialog import RulePanel
    host = QtWidgets.QMainWindow()
    host.setCentralWidget(QtWidgets.QWidget())
    sss_rule.enabled = False
    panel = RulePanel(host, cfg, {sss_rule.key, "AJ寸"}, existing=sss_rule)
    panel.lo_box.setValue(1_007_200)
    edited = panel.result_category()
    assert (edited.key, edited.enabled, edited.lo, edited.hi) == ("SSS寸", False, 1_007_200,
                                                                   sss_rule.hi)


def test_a_new_rule_with_a_taken_name_gets_a_fresh_key(app, cfg):
    from ui.rule_dialog import RulePanel
    host = QtWidgets.QMainWindow()
    host.setCentralWidget(QtWidgets.QWidget())
    panel = RulePanel(host, cfg, {"AJ寸"})
    panel.kind_box.setCurrentIndex(1)                                  # AJ寸
    assert panel.result_category().key == "AJ寸_2"


def test_hiding_a_row_takes_its_divider_with_it(app):
    """藏起来的行上面那条分割线也得一起藏，不然卡片里会多出一道线。"""
    from ui.widgets import Card, Divider, SettingRow
    card = Card()
    rows = [card.add_row(SettingRow(name)) for name in ("一", "二", "三")]
    card.set_row_visible(rows[0], False)
    dividers = [w for w in card.findChildren(Divider)]
    shown = [d for d in dividers if not d.isHidden()]
    assert len(shown) == 1, "只剩两行，中间只该有一条线"
