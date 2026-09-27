# -*- coding: utf-8 -*-
"""首次运行：问清楚 CHUNITHM 装在哪。

安装器里已经选过的话不会走到这儿（那份选择通过 ``install.ini`` 进了配置）。
便携解压、或者安装时跳过了这一步的用户才会看到。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QWidget

from core import game_locator
from core.config import derive_paths, normalize_game_root
from core.models import CunConfig

from .theme import metrics as m
from .widgets import Button, Card, Panel, SettingRow, label


class FirstRunPanel(Panel):
    """选完之后用 :attr:`game_root` 取结果；跳过则为 ``None``。"""

    def __init__(self, parent: QWidget, cfg: CunConfig) -> None:
        super().__init__(parent, "选择游戏目录", confirm="完成", cancel="跳过")
        self.game_root: Path | None = None

        card = Card()
        browse = Button("选择…")
        browse.clicked.connect(self._browse)
        self._path_row = card.add_row(SettingRow("游戏目录", "未选择", browse))
        self._derived_row = card.add_row(SettingRow("截图目录", "—"))
        self.body.addWidget(card)

        self._hint = label("", "secondary", wrap=True)
        self._hint.setContentsMargins(m.PAD_CONTAINER, 0, m.PAD_CONTAINER, 0)
        self.body.addWidget(self._hint)
        self.confirm_button.setEnabled(False)

        detected = game_locator.autodetect(cfg)
        if detected is not None:
            self._set_root(detected, "已自动找到，不对就重新选择")
        else:
            self._set_hint("没有自动找到。选中 CHUNITHM 根目录（里面有 bin 文件夹），"
                           "跳过的话之后也能在“配置”页里补")

    def _browse(self) -> None:
        start = str(self.game_root) if self.game_root else ""
        chosen = QFileDialog.getExistingDirectory(self, "选择 CHUNITHM 游戏目录", start)
        if not chosen:
            return
        root = normalize_game_root(chosen)
        if root is None:
            self._set_hint("这个目录里没有 bin 文件夹，不像 CHUNITHM 的安装位置。"
                           "选根目录或者它的 bin 目录")
            return
        self._set_root(root, "")

    def _set_root(self, root: Path, hint: str) -> None:
        self.game_root = root
        self._path_row.set_desc(str(root))
        shots, _bat = derive_paths(root)
        self._derived_row.set_desc(shots if Path(shots).is_dir() else f"{shots}（将自动创建）")
        self._set_hint(hint)
        self.confirm_button.setEnabled(True)

    def _set_hint(self, text: str) -> None:
        """文字和可见性一起改：选过一次有效目录之后提示被藏起来，再选错时得重新露出来。"""
        self._hint.setText(text)
        self._hint.setVisible(bool(text))


def ask_for_game_root(cfg: CunConfig, parent: QWidget) -> Path | None:
    """弹一次面板。跳过返回 ``None``。"""
    panel = FirstRunPanel(parent, cfg)
    if panel.run() and panel.game_root is not None:
        return panel.game_root
    return None
