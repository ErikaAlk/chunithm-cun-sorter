# -*- coding: utf-8 -*-
"""添加 / 编辑判定规则的面板。

三种类型：评级判定（按得分区间）、AJ寸、ATTACK+MISS。评级判定再选一个档位：
选中预设则上限锁死、下限仍可调；选「自定义区间」上下限都能填。
多字段表单，所以是面板 + 顶栏「取消 / 完成」的明确提交（DESIGN.md 11.2）。
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from core.config import SCORE_PRESETS, ranks
from core.models import MAX_SCORE, Category, CunConfig

from .widgets import Button, Card, ComboBox, LineEdit, Panel, SettingRow, SpinBox, value_label

_KINDS: tuple[tuple[str, str], ...] = (
    ("score", "评级判定"),
    ("ajcun", "AJ寸"),
    ("am", "ATTACK+MISS"),
)
_LEGACY_KINDS = {"aj": "AJ", "fc": "FC"}
_CUSTOM_RANGE = "自定义区间"


def unique_key(label_text: str, taken: set[str]) -> str:
    """规则的 key 是它的持久身份（分类结果、DGHub 的 rules 字段都认它），不能重。"""
    base = label_text.strip() or "custom"
    key = base
    i = 2
    while key in taken:
        key = f"{base}_{i}"
        i += 1
    return key


def summary(cat: Category, cfg: CunConfig) -> str:
    """设置行第二行放的数据：这条规则到底卡在哪。"""
    if cat.kind == "score":
        return f"{cat.lo or 0:,} – {cat.hi or 0:,}"
    if cat.kind == "ajcun":
        return f"ATTACK 0 ｜ MISS 1 – {cat.m_hi if cat.m_hi is not None else 4}"
    if cat.kind == "am":
        rank = cat.min_rank or "SSS"
        return (f"ATTACK ≤ {cat.a_hi if cat.a_hi is not None else 4} ｜ "
                f"MISS ≤ {cat.m_hi if cat.m_hi is not None else 4} ｜ {rank} 及以上")
    return _LEGACY_KINDS.get(cat.kind, cat.kind)


class RulePanel(Panel):
    """``existing`` 为 ``None`` 是添加，否则是编辑那一条。

    关掉之后看 :attr:`deleted` 和 :meth:`result_category`。
    """

    def __init__(self, parent: QWidget, cfg: CunConfig, taken_keys: set[str],
                 existing: Category | None = None) -> None:
        editing = existing is not None
        super().__init__(parent, "编辑判定规则" if editing else "添加判定规则",
                         confirm="完成" if editing else "添加")
        self._cfg = cfg
        self._taken = taken_keys - ({existing.key} if existing else set())
        self._existing = existing
        self.deleted = False
        legacy = existing is not None and existing.kind in _LEGACY_KINDS

        card = Card()
        self._card = card
        self.name_box = LineEdit()
        self.name_box.setFixedWidth(200)
        self.name_box.setPlaceholderText("SSS寸")
        self.name_box.textChanged.connect(self._refresh_confirm)
        card.add_row(SettingRow("名称", "", self.name_box))

        self.kind_box = ComboBox([name for _, name in _KINDS])
        self._kind_row = card.add_row(SettingRow("类型", "", self.kind_box))
        self._legacy_row = card.add_row(SettingRow(
            "类型", "", value_label(_LEGACY_KINDS.get(existing.kind, "") if legacy else "")))

        self.preset_box = ComboBox([name for name, _, _ in SCORE_PRESETS] + [_CUSTOM_RANGE])
        self._preset_row = card.add_row(SettingRow("档位", "", self.preset_box))
        self.lo_box = SpinBox(0, MAX_SCORE, 0, width=128)
        self._lo_row = card.add_row(SettingRow("得分下限", "", self.lo_box))
        self.hi_box = SpinBox(0, MAX_SCORE, 0, width=128)
        self.hi_fixed = value_label()
        self._hi_row = card.add_row(SettingRow("得分上限", "", self.hi_box, self.hi_fixed))

        self.m_hi_box = SpinBox(0, 100, 4, width=72)
        self._m_row = card.add_row(SettingRow("MISS 上限", "", self.m_hi_box))
        self.a_hi_box = SpinBox(0, 100, 4, width=72)
        self._a_row = card.add_row(SettingRow("ATTACK 上限", "", self.a_hi_box))
        self.rank_box = ComboBox(ranks(cfg))
        self._rank_row = card.add_row(SettingRow("最低评级", "", self.rank_box))

        self.folder_box = LineEdit()
        self.folder_box.setFixedWidth(200)
        card.add_row(SettingRow("输出文件夹", "", self.folder_box))
        self.body.addWidget(card)

        if editing:
            delete = Button("删除规则", "danger")
            delete.clicked.connect(self._delete)
            self.body.addWidget(delete)

        self._last_suggest = ""
        self._fill(existing)
        self.kind_box.currentIndexChanged.connect(self._refresh)
        self.preset_box.currentIndexChanged.connect(self._refresh)
        # 自定义区间的上下限互相夹住：填不出下限高于上限的区间，也就不用事后报错
        self.lo_box.valueChanged.connect(self._clamp_range)
        self.hi_box.valueChanged.connect(self._clamp_range)
        self.name_box.textChanged.connect(self._suggest_folder)
        self._refresh()
        card.set_row_visible(self._kind_row, not legacy)
        card.set_row_visible(self._legacy_row, legacy)

    # ----------------------------- 初值 -------------------------------------
    def _fill(self, cat: Category | None) -> None:
        index = self.rank_box.findText("SSS")
        self.rank_box.setCurrentIndex(max(0, index))
        if cat is None:
            return
        self.name_box.setText(cat.label or cat.key)
        self._last_suggest = ""
        self.folder_box.setText(cat.folder)
        kinds = [k for k, _ in _KINDS]
        if cat.kind in kinds:
            self.kind_box.setCurrentIndex(kinds.index(cat.kind))
        if cat.kind == "score":
            preset = next((i for i, (_, lo, hi) in enumerate(SCORE_PRESETS)
                           if hi == cat.hi), None)
            self.preset_box.setCurrentIndex(len(SCORE_PRESETS) if preset is None else preset)
            self.lo_box.setValue(cat.lo or 0)
            self.hi_box.setValue(cat.hi or 0)
        if cat.m_hi is not None:
            self.m_hi_box.setValue(cat.m_hi)
        if cat.a_hi is not None:
            self.a_hi_box.setValue(cat.a_hi)
        if cat.min_rank:
            index = self.rank_box.findText(cat.min_rank)
            if index >= 0:
                self.rank_box.setCurrentIndex(index)

    # ----------------------------- 联动 -------------------------------------
    def _kind(self) -> str:
        if self._existing is not None and self._existing.kind in _LEGACY_KINDS:
            return self._existing.kind
        return _KINDS[self.kind_box.currentIndex()][0]

    def _is_custom_range(self) -> bool:
        return self.preset_box.currentText() == _CUSTOM_RANGE

    def _refresh(self) -> None:
        kind = self._kind()
        is_score = kind == "score"
        custom = self._is_custom_range()
        card = self._card
        card.set_row_visible(self._preset_row, is_score)
        card.set_row_visible(self._lo_row, is_score)
        card.set_row_visible(self._hi_row, is_score)
        self.hi_box.setVisible(custom)
        self.hi_fixed.setVisible(not custom)
        card.set_row_visible(self._m_row, kind in ("ajcun", "am"))
        card.set_row_visible(self._a_row, kind == "am")
        card.set_row_visible(self._rank_row, kind == "am")

        if is_score and not custom:
            _, lo, hi = SCORE_PRESETS[self.preset_box.currentIndex()]
            self.lo_box.setMaximum(hi)
            if self._existing is None or self._existing.hi != hi:
                self.lo_box.setValue(lo)
            self.hi_fixed.setText(f"{hi:,}")
        elif is_score:
            self._clamp_range()
        self._suggest_name()
        self._refresh_confirm()

    def _clamp_range(self) -> None:
        if not self._is_custom_range():
            self.hi_box.setMinimum(0)
            return
        if self.hi_box.value() < self.lo_box.value():   # 刚从预设切过来，上限还是空的
            self.hi_box.setValue(self.lo_box.value())
        self.lo_box.setMaximum(self.hi_box.value())
        self.hi_box.setMinimum(self.lo_box.value())

    def _suggest_name(self) -> None:
        """名字跟着当前选择自动填，用户自己打过就不再覆盖。"""
        kind = self._kind()
        if kind == "score":
            suggestion = None if self._is_custom_range() else self.preset_box.currentText()
        elif kind == "ajcun":
            suggestion = "AJ寸"
        elif kind == "am":
            suggestion = "AM寸"
        else:
            suggestion = None
        if suggestion is None:
            return
        current = self.name_box.text().strip()
        if not current or current == self._last_suggest:
            self.name_box.setText(suggestion)
            self._last_suggest = suggestion

    def _suggest_folder(self, _text: str = "") -> None:
        self.folder_box.setPlaceholderText(f"寸/{self.name_box.text().strip() or '名称'}")

    def _refresh_confirm(self) -> None:
        self.confirm_button.setEnabled(bool(self.name_box.text().strip()))
        self._suggest_folder()

    def _delete(self) -> None:
        self.deleted = True
        self.reject()

    # ----------------------------- 结果 -------------------------------------
    def result_category(self) -> Category:
        name = self.name_box.text().strip()
        kind = self._kind()
        folder = self.folder_box.text().strip() or f"寸/{name}"
        old = self._existing
        cat = Category(key=old.key if old else unique_key(name, self._taken), label=name, kind=kind,
                       enabled=old.enabled if old else True, custom=True, folder=folder)
        if kind == "score":
            cat.lo = self.lo_box.value()
            cat.hi = (self.hi_box.value() if self._is_custom_range()
                      else SCORE_PRESETS[self.preset_box.currentIndex()][2])
        elif kind == "ajcun":
            cat.m_hi = self.m_hi_box.value()
        elif kind == "am":
            cat.a_hi = self.a_hi_box.value()
            cat.m_hi = self.m_hi_box.value()
            cat.min_rank = self.rank_box.currentText()
        return cat

