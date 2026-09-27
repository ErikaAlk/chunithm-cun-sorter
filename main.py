# -*- coding: utf-8 -*-
"""界面入口。

    python main.py              # 正常打开
    python main.py --watch      # 随游戏启动：直接开监视并缩到托盘

单实例：start.bat 拉起来时如果程序已经在跑，这次启动静默退出，
不会出现两个监视器抢同一批截图。设 ``CUN_ALLOW_MULTIPLE=1`` 可以绕过这道闸
（打包时的启动冒烟要用它——开发机上多半正跑着一份正式版）。
"""

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    from core import winapi
    from core.version import APP_USER_MODEL_ID, SINGLE_INSTANCE_MUTEX

    # 必须赶在 QApplication 之前：不声明 DPI 感知的话，抓屏坐标会被系统缩放，
    # 自动截图截出来的是画面的一角
    winapi.set_dpi_awareness()

    if os.environ.get("CUN_ALLOW_MULTIPLE") != "1":
        if not winapi.acquire_single_instance(SINGLE_INSTANCE_MUTEX):
            return 0

    winapi.set_app_user_model_id(APP_USER_MODEL_ID)

    from core import autostart
    autostart.migrate_legacy()                      # 改名前设过的自启项，搬到新名字下

    from PySide6.QtWidgets import QApplication

    from core import config as config_mod
    from ui import theme
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("chunithm-cun-sorter")
    app.setQuitOnLastWindowClosed(False)            # 关窗口＝缩托盘，别退出进程

    # 深浅模式要在建窗口之前定下来，不然第一帧会闪一下另一套底色。
    # 跟随系统时读 Qt 的 colorScheme()，所以必须在 QApplication 之后。
    theme.set_appearance(config_mod.load_cached().appearance)
    theme.apply(app)

    window = MainWindow()
    window.show()
    if "--watch" in args:
        window.enter_watch_mode()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
