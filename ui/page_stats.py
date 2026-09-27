# -*- coding: utf-8 -*-
"""「统计」页：四块汇总数字 + 每日 寸 / AJ / FC 曲线。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QGridLayout, QVBoxLayout

from core import classifier
from core import config as config_mod

from .theme import metrics as m
from .widgets import DailyChart, EmptyState, IconButton, Page, StatTile, Surface, label

if TYPE_CHECKING:
    from .main_window import MainWindow

#: 内容列窄于这个宽度时，四块汇总排成两行两列
_TWO_BY_TWO_BELOW = 560


def _day(iso: str) -> str:
    """``2026-07-10`` → ``7月10日``（DESIGN.md 14 章：日期不加空格）。"""
    return f"{int(iso[5:7])}月{int(iso[8:10])}日"


class StatsPage(Page):
    def __init__(self, main: "MainWindow") -> None:
        super().__init__("统计")
        self._main = main
        refresh = IconButton("refresh", "刷新")
        refresh.clicked.connect(self.refresh)
        self.add_action(refresh)

        self.status = label("", "value")
        self.body.addWidget(self.status)

        self.today = StatTile("今天")
        self.week = StatTile("近 7 天")
        self.total = StatTile("累计")
        self.best = StatTile("最高一天")
        self._tiles = (self.today, self.week, self.total, self.best)
        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(m.GAP_CARD)
        self._columns = 0
        self._arrange(4)
        self.body.addLayout(self._grid)

        # 曲线是平铺内容，放在实色内容面上，不直接铺在 Mica 上（16.3）
        panel = Surface("contentSurface")
        box = QVBoxLayout(panel)
        box.setContentsMargins(m.PAD_CONTAINER, m.PAD_CONTAINER,
                               m.PAD_CONTAINER, m.PAD_CONTAINER)
        self.chart = DailyChart()
        self.empty = EmptyState("暂无记录", "开始监视或重新扫描之后，这里会按天画出寸、AJ 和 FC")
        box.addWidget(self.chart)
        box.addWidget(self.empty)
        self.body.addWidget(panel, 1)

    def _arrange(self, columns: int) -> None:
        if columns == self._columns:
            return
        self._columns = columns
        for tile in self._tiles:
            self._grid.removeWidget(tile)
        for i, tile in enumerate(self._tiles):
            self._grid.addWidget(tile, i // columns, i % columns)
        for c in range(4):
            self._grid.setColumnStretch(c, 1 if c < columns else 0)

    def resizeEvent(self, event) -> None:           # noqa: N802
        super().resizeEvent(event)
        # 列宽按页宽减页边距算：这一刻列本身还没排版，量到的是上一轮的宽度
        width = min(self.width() - 2 * self.margin, m.CONTENT_MAX_WIDTH)
        self._arrange(2 if width < _TWO_BY_TWO_BELOW else 4)

    def refresh(self) -> None:
        cfg = config_mod.load_cached()
        data = classifier.daily_counts(cfg)
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        by_date = {d: (cun, aj, fc) for d, cun, aj, fc in data}
        week_days = {(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}

        self.today.set_value(by_date.get(today, (0, 0, 0))[0])
        self.week.set_value(sum(v[0] for d, v in by_date.items() if d in week_days))
        self.total.set_value(sum(v[0] for v in by_date.values()))
        best = max(data, key=lambda d: d[1], default=None)
        if best is not None and best[1] > 0:
            self.best.set_value(best[1])
            self.best.set_caption(f"最高一天 ｜ {_day(best[0])}")
        else:
            self.best.set_value(0)
            self.best.set_caption("最高一天")

        stamp = f"更新于 {now:%H:%M}"
        self.status.setText(f"{_day(data[0][0])} – {_day(data[-1][0])} ｜ {stamp}"
                            if data else stamp)
        self.chart.set_data(data)
        self.chart.setVisible(bool(data))
        self.empty.setVisible(not data)
