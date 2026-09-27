# -*- coding: utf-8 -*-
"""「运行」页：启停监视、处理方式、各路状态、自启动、记录。

开关和选择改完立即生效（自启动和 start.bat 本来就是即时动作）。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from core import autostart, start_bat
from core import config as config_mod

from . import theme
from .theme import metrics as m
from .widgets import (Button, ComboBox, Page, Section, SettingRow, Surface, Switch, label,
                      value_label)

if TYPE_CHECKING:
    from .main_window import MainWindow

_MODES = (("realtime", "实时处理"), ("on_close", "关闭游戏后处理"))
#: 记录最多留这么多行，跑一整天也不会把内存吃光
_LOG_LIMIT = 500


class RunPage(Page):
    def __init__(self, main: "MainWindow") -> None:
        super().__init__("运行")
        self._main = main
        self._initializing = True

        # 这一页的主操作只有一个：开始 / 停止监视
        self.start_button = Button("开始监视", "primary")
        self.start_button.clicked.connect(main.toggle_watch)
        self.add_action(self.start_button)

        watch = Section()
        self.watch_row = watch.add_row(SettingRow("监视", "已停止"))
        self.mode_box = ComboBox([name for _, name in _MODES])
        self.mode_box.setCurrentIndex(0 if main.cfg.process_mode == "realtime" else 1)
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        watch.add_row(SettingRow("处理方式", "", self.mode_box))
        self.game_value = value_label("检测中…")
        watch.add_row(SettingRow("游戏", "", self.game_value))
        self.body.addWidget(watch)

        link = Section("联动状态")
        self.link_row = link.add_row(SettingRow("数据服务", "未启用"))
        self.judge_row = link.add_row(SettingRow("判定读取", "未启用"))
        self.body.addWidget(link)

        self.auto = Section("自启动")
        self.autostart_switch = Switch()
        self.autostart_switch.setChecked(autostart.is_enabled())
        self.autostart_switch.toggled.connect(autostart.set_enabled)
        self.auto.add_row(SettingRow("开机时启动", "", self.autostart_switch))
        self.bat_switch = Switch()
        self.bat_switch.toggled.connect(self._toggle_start_bat)
        self.auto.add_row(SettingRow("随游戏启动", "改写游戏的 start.bat，关闭即还原",
                                     self.bat_switch))
        self.body.addWidget(self.auto)

        # 记录是平铺内容，放在实色内容面上（16.3），不包设置卡片
        log_group = QWidget()
        log_lay = QVBoxLayout(log_group)
        log_lay.setContentsMargins(0, 0, 0, 0)
        log_lay.setSpacing(m.GAP_INLINE)
        head = label("记录", "groupTitle")
        head.setContentsMargins(m.PAD_CONTAINER, 0, m.PAD_CONTAINER, 0)
        log_lay.addWidget(head)
        panel = Surface("contentSurface")
        box = QVBoxLayout(panel)
        box.setContentsMargins(m.PAD_CONTAINER, m.PAD_CONTROL_Y, m.GAP_INLINE, m.PAD_CONTROL_Y)
        self.log_box = QPlainTextEdit()
        self.log_box.setObjectName("LogBox")
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(_LOG_LIMIT)
        self.log_box.setFont(theme.font(theme.MONO, mono=True))
        self.log_box.setPlaceholderText("暂无记录")
        self.log_box.setMinimumHeight(m.SETTING_ROW * 5)
        box.addWidget(self.log_box)
        log_lay.addWidget(panel, 1)
        self.body.addWidget(log_group, 1)

        self.refresh_start_bat()
        self._initializing = False

    def restyle(self) -> None:
        """换主题后日志的等宽字体要重新取（跟着文本大小走）。"""
        self.log_box.setFont(theme.font(theme.MONO, mono=True))

    # ----------------------------- 交互 -------------------------------------
    def _mode_changed(self, index: int) -> None:
        if not self._initializing:
            self._main.on_mode_changed(_MODES[index][0])

    def _toggle_start_bat(self, checked: bool) -> None:
        if self._initializing:
            return
        cfg = self._main.cfg
        if checked:
            bat = cfg.start_bat
            if not bat or not Path(bat).is_file():
                bat = self._main.pick_file("选择游戏的 start.bat", "批处理 (*.bat *.cmd)")
                if not bat:
                    self.refresh_start_bat()
                    return
            try:
                start_bat.hook(bat)
                cfg.start_bat = bat
                config_mod.save(cfg)
            except OSError as e:
                self._main.show_toast(f"接入 start.bat 失败：{e}", error=True)
        else:
            try:
                if cfg.start_bat:
                    start_bat.unhook(cfg.start_bat)
            except OSError as e:
                self._main.show_toast(f"还原 start.bat 失败：{e}", error=True)
        self.refresh_start_bat()

    def refresh_start_bat(self) -> None:
        bat = self._main.cfg.start_bat
        hooked = bool(bat) and start_bat.is_hooked(bat)
        was = self._initializing
        self._initializing = True                   # 别让程序化的置位触发 toggled
        self.bat_switch.setChecked(hooked)
        self._initializing = was
        self.auto.set_note(f"已接入 {bat}，原文件备份为 .cun-backup" if hooked else "")

    # ----------------------------- 主窗口回调 -------------------------------
    def set_watch_state(self, running: bool, text: str) -> None:
        self.start_button.setText("停止监视" if running else "开始监视")
        self.start_button.set_kind("secondary" if running else "primary")
        self.start_button.updateGeometry()
        self.watch_row.set_desc(text)

    def set_watch_text(self, text: str) -> None:
        self.watch_row.set_desc(text)

    def set_game_text(self, text: str) -> None:
        self.game_value.setText(text)

    def set_link_text(self, text: str) -> None:
        self.link_row.set_desc(text)

    def set_judge_text(self, text: str) -> None:
        self.judge_row.set_desc(text)

    def append_log(self, line: str) -> None:
        self.log_box.appendPlainText(line)
