# -*- coding: utf-8 -*-
"""「配置」页：目录、判定规则、整理、DGHub 联动、自动截图、外观。

改完**立即生效并保存**（DESIGN.md 11.2）：开关、选择器、目录选择当场写盘，数字框敲完
（回车或离开）写盘。判定规则是多字段表单，放进面板里用「取消 / 完成」明确提交。
页面上没有「保存」按钮，也就不存在两种保存方式混用的问题。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from core.config import derive_paths, normalize_game_root
from core.models import Category, CunConfig, OrganizeStep

from . import theme
from .rule_dialog import RulePanel, summary, unique_key
from .widgets import (Button, ComboBox, DoubleSpinBox, IconButton, Page, Section,
                      SettingRow, SpinBox, Switch)

if TYPE_CHECKING:                                   # 只为类型标注，运行时不导入主窗口
    from .main_window import MainWindow

_SPAN_KEYS = ("year", "month", "day")
_SPAN_NAMES = ("按年", "按月", "按日")
_ORGANIZE_LABELS = {"date": "日期", "rank": "评级", "achievement": "达成"}


class ConfigPage(Page):
    def __init__(self, main: "MainWindow") -> None:
        super().__init__("配置")
        self._main = main
        self._loading = True
        self._org: list[tuple[str, Switch, ComboBox | None]] = []

        open_out = IconButton("folder", "打开输出文件夹")
        open_out.clicked.connect(main.open_output)
        self.add_action(open_out)
        self.rescan_btn = Button("重新扫描", "primary")
        self.rescan_btn.clicked.connect(main.rescan)
        self.add_action(self.rescan_btn)

        self._build_dirs()
        self._build_rules()
        self._build_organize()
        self._build_link()
        self._build_capture()
        self._build_appearance()
        self.body.addStretch(1)
        self._loading = False

    @property
    def _cfg(self) -> CunConfig:
        return self._main.cfg

    def _save(self) -> None:
        """改完立即写盘。构建界面时的程序化置位不算。"""
        if not self._loading:
            self._main.save_settings()

    # ----------------------------- 目录 -------------------------------------
    def _build_dirs(self) -> None:
        section = Section()
        self.game_row = self._dir_row(section, "游戏目录", self._pick_game)
        self.shots_row = self._dir_row(section, "截图目录", self._pick_shots)
        self.out_row = self._dir_row(section, "输出目录", self._pick_out)
        self.body.addWidget(section)
        self.refresh_paths()

    @staticmethod
    def _dir_row(section: Section, title: str, on_pick) -> SettingRow:
        change = Button("更改")
        change.setAccessibleName(f"更改{title}")
        change.clicked.connect(on_pick)
        return section.add_row(SettingRow(title, "", change))

    def refresh_paths(self) -> None:
        """配置在别处被改过（比如首次运行）之后，把三行目录刷新一遍。"""
        for row, value in ((self.game_row, self._cfg.game_root),
                           (self.shots_row, self._cfg.screenshots_dir),
                           (self.out_row, self._cfg.output_root)):
            row.set_desc(value or "未设置")

    def _pick_game(self) -> None:
        path = self._main.pick_folder("选择 CHUNITHM 游戏目录", self._cfg.game_root)
        if not path:
            return
        root = normalize_game_root(path)
        if root is None:
            self._main.show_toast("这个目录里没有 bin 文件夹，选 CHUNITHM 根目录或它的 bin 目录",
                                  error=True)
            return
        cfg = self._cfg
        cfg.game_root = str(root)
        shots, bat = derive_paths(root)
        cfg.screenshots_dir = shots
        if not cfg.output_root:
            cfg.output_root = shots
        if bat:
            cfg.start_bat = bat
        self._after_dirs_changed()

    def _pick_shots(self) -> None:
        path = self._main.pick_folder("选择截图目录", self._cfg.screenshots_dir)
        if not path:
            return
        self._cfg.screenshots_dir = path
        # 第一次选截图目录时把输出也指过去，分类结果落在原图旁边（一直以来的默认）
        if not self._cfg.output_root:
            self._cfg.output_root = path
        self._after_dirs_changed()

    def _pick_out(self) -> None:
        path = self._main.pick_folder("选择输出目录", self._cfg.output_root)
        if path:
            self._cfg.output_root = path
            self._after_dirs_changed()

    def _after_dirs_changed(self) -> None:
        self.refresh_paths()
        self._main.save_settings()
        self._main.run_page.refresh_start_bat()

    # ----------------------------- 判定规则 ---------------------------------
    def _build_rules(self) -> None:
        self.rules = Section("判定规则", "命中的截图会复制到规则的文件夹并计入“寸”统计，原图不动")
        self._rebuild_rules()
        self.body.addWidget(self.rules)

    def _rebuild_rules(self) -> None:
        was, self._loading = self._loading, True
        self.rules.card.clear()
        for cat in self._cfg.categories:
            switch = Switch()
            switch.setChecked(cat.enabled)
            switch.toggled.connect(lambda on, c=cat: self._toggle_rule(c, on))
            row = SettingRow(cat.label or cat.key, summary(cat, self._cfg), switch,
                             on_click=lambda c=cat: self._edit_rule(c))
            switch.setAccessibleName(f"启用“{cat.label or cat.key}”")
            self.rules.add_row(row)
        add = self.rules.add_row(SettingRow("添加判定规则", on_click=self._add_rule))
        add.title.setProperty("role", "action")
        self._loading = was

    def _toggle_rule(self, cat: Category, on: bool) -> None:
        cat.enabled = on
        self._save()

    def _taken_keys(self) -> set[str]:
        return {c.key for c in self._cfg.categories}

    def _add_rule(self) -> None:
        panel = RulePanel(self, self._cfg, self._taken_keys())
        if not panel.run():
            return
        self._cfg.categories.append(panel.result_category())
        self._rebuild_rules()
        self._main.save_settings()

    def _edit_rule(self, cat: Category) -> None:
        panel = RulePanel(self, self._cfg, self._taken_keys(), existing=cat)
        accepted = panel.run()
        try:
            index = self._cfg.categories.index(cat)
        except ValueError:
            return
        if panel.deleted:
            self._remove_rule(index)
        elif accepted:
            self._cfg.categories[index] = panel.result_category()
            self._rebuild_rules()
            self._main.save_settings()

    def _remove_rule(self, index: int) -> None:
        """规则随手能重建，直接删、不确认（11.4）；原图不受影响，给一个撤销。"""
        cat = self._cfg.categories.pop(index)
        self._rebuild_rules()
        self._main.save_settings()

        def undo() -> None:
            # 删掉之后又新建了同名规则的话，旧 key 已经被占了，撤销回来的换一个
            taken = self._taken_keys()
            if cat.key in taken:
                cat.key = unique_key(cat.key, taken)
            self._cfg.categories.insert(min(index, len(self._cfg.categories)), cat)
            self._rebuild_rules()
            self._main.save_settings()

        self._main.show_toast(f"已删除“{cat.label or cat.key}”", action=("撤销", undo))

    # ----------------------------- 整理 -------------------------------------
    def _build_organize(self) -> None:
        self.organize = Section("整理", "开启后，扫描会把识别出成绩的原图移到归档文件夹，"
                                        "靠上的一项是外层；无关图片不动")
        self._rebuild_organize(self._cfg.organize.steps)
        self.body.addWidget(self.organize)

    def _rebuild_organize(self, steps: list[OrganizeStep]) -> None:
        was, self._loading = self._loading, True
        self._org.clear()
        self.organize.card.clear()
        last = len(steps) - 1
        for i, step in enumerate(steps):
            name = _ORGANIZE_LABELS.get(step.kind, step.kind)
            controls: list[QWidget] = []
            span = None
            if step.kind == "date":
                span = ComboBox(_SPAN_NAMES)
                span.setCurrentIndex(_SPAN_KEYS.index(step.date_span)
                                     if step.date_span in _SPAN_KEYS else 1)
                span.setAccessibleName("日期的归档粒度")
                span.currentIndexChanged.connect(self._organize_changed)
                controls.append(span)
            up = IconButton("chevron-up", "上移")
            up.setAccessibleName(f"上移“{name}”")
            up.setEnabled(i > 0)
            up.clicked.connect(lambda _=False, k=step.kind: self._move(k, -1))
            down = IconButton("chevron-down", "下移")
            down.setAccessibleName(f"下移“{name}”")
            down.setEnabled(i < last)
            down.clicked.connect(lambda _=False, k=step.kind: self._move(k, +1))
            switch = Switch()
            switch.setChecked(step.enabled)
            switch.setAccessibleName(f"按{name}整理")
            switch.toggled.connect(self._organize_changed)
            self.organize.add_row(SettingRow(name, "", *controls, up, down, switch))
            self._org.append((step.kind, switch, span))
        self._loading = was

    def current_organize_steps(self) -> list[OrganizeStep]:
        steps = []
        for kind, switch, span in self._org:
            step = OrganizeStep(kind=kind, enabled=switch.isChecked())
            if span is not None:
                step.date_span = _SPAN_KEYS[max(0, span.currentIndex())]
            steps.append(step)
        return steps

    def _organize_changed(self, *_args) -> None:
        if self._loading:
            return
        self._cfg.organize.steps = self.current_organize_steps()
        self._save()

    def _move(self, kind: str, delta: int) -> None:
        steps = self.current_organize_steps()
        i = next((n for n, s in enumerate(steps) if s.kind == kind), -1)
        j = i + delta
        if i < 0 or not 0 <= j < len(steps):
            return
        steps[i], steps[j] = steps[j], steps[i]
        self._cfg.organize.steps = steps
        self._rebuild_organize(steps)
        self._save()

    # ----------------------------- 联动 -------------------------------------
    def _build_link(self) -> None:
        section = Section("DGHub 联动", "只读取游戏内存里的判定计数，不修改游戏；"
                                         "数据只在本机 127.0.0.1 上提供")
        self.dg_switch = Switch()
        self.dg_switch.setChecked(self._cfg.dghub.enabled)
        section.add_row(SettingRow("DGHub 联动", "打歌中实时触发 DGHub 波形", self.dg_switch))
        self.dg_port = SpinBox(1, 65535, self._cfg.dghub.port or 8890, width=96)
        self.dg_port.setGroupSeparatorShown(False)
        self.dg_port.setAccessibleName("数据端口")
        self.dg_port_row = section.add_row(SettingRow("数据端口", "", self.dg_port))
        self.dg_port_row.setEnabled(self._cfg.dghub.enabled)
        self.dg_switch.toggled.connect(self._link_toggled)
        self.dg_port.valueChanged.connect(self._port_changed)
        self.body.addWidget(section)

    def _link_toggled(self, on: bool) -> None:
        self._cfg.dghub.enabled = on
        self.dg_port_row.setEnabled(on)
        self._save()

    def _port_changed(self, value: int) -> None:
        self._cfg.dghub.port = value
        self._save()

    # ----------------------------- 自动截图 ---------------------------------
    def _build_capture(self) -> None:
        section = Section()
        self.cap_switch = Switch()
        self.cap_switch.setChecked(self._cfg.capture.enabled)
        section.add_row(SettingRow("自动截图", "结算时截取成绩画面，新截图不用 OCR",
                                   self.cap_switch))
        self.cap_delay = DoubleSpinBox(0.0, 15.0, self._cfg.capture.delay_s, 0.5, " 秒")
        self.cap_delay.setAccessibleName("截图前等待")
        self.cap_delay_row = section.add_row(SettingRow("截图前等待", "", self.cap_delay))
        self.cap_delay_row.setEnabled(self._cfg.capture.enabled)
        self.cap_switch.toggled.connect(self._capture_toggled)
        self.cap_delay.valueChanged.connect(self._delay_changed)
        self.body.addWidget(section)

    def _capture_toggled(self, on: bool) -> None:
        self._cfg.capture.enabled = on
        self.cap_delay_row.setEnabled(on)
        self._save()

    def _delay_changed(self, value: float) -> None:
        self._cfg.capture.delay_s = value
        self._save()

    # ----------------------------- 外观 -------------------------------------
    def _build_appearance(self) -> None:
        section = Section()
        self.appearance = ComboBox([theme.APPEARANCE_LABELS[a] for a in theme.APPEARANCES])
        current = self._cfg.appearance
        self.appearance.setCurrentIndex(theme.APPEARANCES.index(current)
                                        if current in theme.APPEARANCES else 0)
        self.appearance.currentIndexChanged.connect(self._appearance_changed)
        section.add_row(SettingRow("外观", "", self.appearance))
        self.body.addWidget(section)

    def _appearance_changed(self, index: int) -> None:
        self._cfg.appearance = theme.APPEARANCES[index]
        self._save()
        self._main.apply_appearance()

    # ----------------------------- 状态 -------------------------------------
    def set_scanning(self, scanning: bool) -> None:
        """扫描是异步的，按钮进 Loading，否则连点会起好几个扫描线程。"""
        self.rescan_btn.setEnabled(not scanning)
        self.rescan_btn.setText("正在扫描…" if scanning else "重新扫描")
        self.rescan_btn.updateGeometry()
