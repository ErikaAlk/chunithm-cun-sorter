# -*- coding: utf-8 -*-
"""主窗口：左侧导航 + 三页 + 托盘，以及各页共用的那几个后台服务。

后台线程（监视、内存读取、联动、截图）的回调**一律通过信号**回到界面线程。
直接从工作线程碰部件在 Qt 里是未定义行为，偶发崩溃最难查。
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QStackedWidget,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from core import classifier, paths, winapi
from core import config as config_mod
from core.capture import CaptureService
from core.judge_memory import JudgeMemoryReader
from core.link_server import LinkServer
from core.models import Category, CunConfig, JudgeCounts, OcrRecord, ScanResult
from core.ocr import OcrEngine
from core.version import APP_NAME
from core.watcher import Watcher

from . import theme, widgets
from .first_run import ask_for_game_root
from .page_config import ConfigPage
from .page_run import RunPage
from .page_stats import StatsPage
from .widgets import Toast

#: 判定数冻结多久算「结算画面已经出来了」
_FREEZE_TRIGGER_SEC = 2.5
#: 少于这么多音符不当一次有效演奏
_MIN_NOTES = 10
#: 侧栏宽度与每一项的行高
_SIDEBAR_WIDTH = 152
_NAV_ROW_HEIGHT = 32


class MainWindow(QMainWindow):
    # 工作线程 → 界面线程
    sig_toast = Signal(str, str, str, int, object)
    sig_log = Signal(str)
    sig_watch_text = Signal(str)
    sig_link_text = Signal(str)
    sig_judge_text = Signal(str)
    sig_match = Signal(str, object, object)
    sig_scan_done = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.cfg: CunConfig = config_mod.load()
        self.ocr = OcrEngine()

        self._watcher: Watcher | None = None
        self._judge: JudgeMemoryReader | None = None
        self._link: LinkServer | None = None
        self._capture: CaptureService | None = None
        self._quitting = False

        # 判定数冻结的追踪状态，见 _track_freeze
        self._tick_last = JudgeCounts()
        self._tick_changed_at = 0.0

        self.setWindowTitle(APP_NAME)
        icon = _app_icon()
        if icon is not None:
            self.setWindowIcon(icon)

        # Mica 得在建窗口之前定：材质是 DWM 铺在窗口**后面**的，窗口自己那层
        # 像素不透明就等于把它整个盖住。而透明是建窗口时才能定下来的属性，
        # show 之后再设不生效。真正开材质在 _after_shown 里，那时才有 hwnd。
        self._mica = winapi.supports_mica()
        if self._mica:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._build_ui()
        self._wire_signals()
        self.setMinimumSize(860, 520)
        self._fit_to_screen()

        self._game_timer = QTimer(self)
        self._game_timer.timeout.connect(self._update_game_label)
        self._game_timer.start(4000)
        self._update_game_label()

        self._tray = self._build_tray(icon)
        QTimer.singleShot(0, self._after_shown)

    # ----------------------------- 组装 -------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        # 画布底色画在这里，不靠 QMainWindow——见 ui/theme/qss.py 里那条注释
        central.setObjectName("AppRoot")
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(_SIDEBAR_WIDTH)
        side_box = QVBoxLayout(sidebar)
        side_box.setContentsMargins(0, theme.GAP_GROUP, 0, theme.GAP_GROUP)
        side_box.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("NavList")
        self.nav.setFrameShape(QListWidget.Shape.NoFrame)
        for text in ("配置", "统计", "运行"):
            item = QListWidgetItem(text, self.nav)
            # 不给行高，Qt 会按图标那一档算，选中的色块高得像块砖
            item.setSizeHint(QSize(_SIDEBAR_WIDTH, _NAV_ROW_HEIGHT))
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._page_changed)
        side_box.addWidget(self.nav)
        side_box.addStretch(1)
        row.addWidget(sidebar)

        self.config_page = ConfigPage(self)
        self.stats_page = StatsPage(self)
        self.run_page = RunPage(self)

        self.stack = QStackedWidget()
        self.stack.setObjectName("ContentPane")
        self.stack.addWidget(self.config_page)
        self.stack.addWidget(self.stats_page)
        self.stack.addWidget(self.run_page)
        row.addWidget(self.stack, 1)

        self.setCentralWidget(central)
        self.toast = Toast(central)
        # 键盘焦点的可见指示。一个窗口一个，覆盖窗口里所有控件。
        self._focus_ring = widgets.FocusRing(self)

    def _fit_to_screen(self) -> None:
        """默认尺寸按可用屏幕收一收，然后居中。

        1040×720 是**逻辑**像素。高缩放比的小屏上可用区可能只有 1280×680
        （1920×1080 跑 150% 就是这个数），照搬会顶满整个高度、贴着任务栏。
        居中是因为 Qt 的默认落点不居中，开窗位置每次都有点随机。
        """
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.resize(1040, 720)
            return
        avail = screen.availableGeometry()
        self.resize(min(1040, int(avail.width() * 0.92)),
                    min(720, int(avail.height() * 0.92)))
        frame = self.frameGeometry()
        frame.moveCenter(avail.center())
        self.move(frame.topLeft())

    def _wire_signals(self) -> None:
        self.sig_toast.connect(self._show_toast_now)
        self.sig_log.connect(self.run_page.append_log)
        self.sig_watch_text.connect(self.run_page.set_watch_text)
        self.sig_link_text.connect(self.run_page.set_link_text)
        self.sig_judge_text.connect(self.run_page.set_judge_text)
        self.sig_match.connect(self._on_match_ui)
        self.sig_scan_done.connect(self._on_scan_done)

    def _build_tray(self, icon: QIcon | None) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(self)
        if icon is not None:
            tray.setIcon(icon)
        tray.setToolTip(APP_NAME)
        menu = QMenu()
        show_action = QAction("显示主界面", self)
        show_action.triggered.connect(self.show_normal)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.show()
        return tray

    def _after_shown(self) -> None:
        """窗口摆出来之后再做的事：标题栏、Mica、首次运行向导、联动开关。"""
        hwnd = int(self.winId())
        app = QApplication.instance()
        # 标题栏归 DWM 管，Qt 的样式表刷不到那一条，得单独跟着主题走
        winapi.set_titlebar_dark(hwnd, theme.is_dark())
        if self._mica and not winapi.enable_mica(hwnd):
            # 材质没铺上，而底色已经按「透得过去」配好了——再不换回来就是一片全黑
            self._mica = False
            if app is not None:
                app.setStyleSheet(theme.stylesheet(mica=False))
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._system_scheme_changed)
        self._ensure_game_root()
        self.apply_dghub_link()

    # ----------------------------- 主题 -------------------------------------
    def _system_scheme_changed(self, _scheme) -> None:
        """系统切了深浅。只有「跟随系统」时才跟着动。"""
        if theme.follows_system():
            self.apply_appearance()

    def apply_appearance(self) -> None:
        """按配置里的 appearance 重新定模式，并把整套外观刷一遍。"""
        theme.set_appearance(self.cfg.appearance)
        app = QApplication.instance()
        if app is not None:
            theme.apply(app, mica=self._mica)
        winapi.set_titlebar_dark(int(self.winId()), theme.is_dark())
        # 自绘的部件和用代码设过的字体不吃样式表，得自己再取一遍
        theme.apply_shadow(self.toast)
        self.stats_page.retheme()
        self.run_page.retheme()

    def _ensure_game_root(self) -> None:
        """还不知道截图目录在哪就弹一次向导。"""
        if self.cfg.screenshots_dir:
            return
        root = ask_for_game_root(self.cfg, self)
        if root is None:
            self.show_toast("还没设置游戏目录",
                            "去「配置 → 目录」里选一下，不然没有截图可以扫。",
                            Toast.WARNING)
            return
        config_mod.apply_game_root(self.cfg, root)
        config_mod.save(self.cfg)
        self.config_page.refresh_paths()
        self.run_page.refresh_start_bat()
        self.show_toast("已设置游戏目录", str(root), Toast.SUCCESS)

    def _page_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == 1:
            self.stats_page.refresh()

    # ----------------------------- 窗口行为 ---------------------------------
    def resizeEvent(self, event) -> None:            # noqa: N802
        super().resizeEvent(event)
        self.toast.parent_resized()

    def closeEvent(self, event) -> None:             # noqa: N802
        """监视还在跑就缩托盘，没在跑就真退出。"""
        if self._quitting or not self.watcher_running:
            self._shutdown()
            event.accept()
            return
        event.ignore()
        self.hide()
        self._tray.showMessage(APP_NAME, "已最小化到托盘，继续后台监视。",
                               QSystemTrayIcon.MessageIcon.Information, 3000)

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_normal()

    def show_normal(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._quitting = True
        self.close()
        QApplication.quit()

    def _shutdown(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        if self._judge is not None:
            self._judge.stop()
            self._judge = None
        if self._capture is not None:
            self._capture.shutdown()
            self._capture = None
        if self._link is not None:
            self._link.stop()
            self._link = None
        self.ocr.close()
        self._tray.hide()

    def enter_watch_mode(self) -> None:
        """``--watch`` 启动（start.bat 拉起来的）：直接开监视并缩到托盘。"""
        if not self.watcher_running:
            self.toggle_watch()
        self.hide()
        self._tray.showMessage(APP_NAME, "已随游戏启动，后台监视中。",
                               QSystemTrayIcon.MessageIcon.Information, 3000)

    # ----------------------------- 选择器 -----------------------------------
    def pick_folder(self, title: str = "选择文件夹", start: str = "") -> str:
        return QFileDialog.getExistingDirectory(self, title, start)

    def pick_file(self, title: str, filter_text: str) -> str:
        path, _ = QFileDialog.getOpenFileName(self, title, "", filter_text)
        return path

    # ----------------------------- 提示 -------------------------------------
    def show_toast(self, title: str, message: str, severity: str = Toast.INFO,
                   duration_ms: int = 0, action: tuple[str, object] | None = None) -> None:
        """线程安全：后台线程也能调，走信号回界面线程。

        ``duration_ms`` 留 0 就用 Toast 的默认时长；错误和带动作的提示不自动消失。
        """
        self.sig_toast.emit(title, message, severity, duration_ms, action)

    def _show_toast_now(self, title: str, message: str, severity: str,
                        duration_ms: int, action) -> None:
        self.toast.show_toast(title, message, severity, duration_ms or None, action)

    # ----------------------------- 配置 -------------------------------------
    def save_instant_settings(self) -> None:
        """开关、单选和选择器改完立刻落盘。

        **只收即时字段**：目录、端口、秒数和得分区间属于要明确提交的输入，
        不能被一次开关切换顺手写进去。
        """
        self.config_page.read_instant_into(self.cfg)
        config_mod.save(self.cfg)
        self.apply_dghub_link()

    def save_config_from_ui(self) -> None:
        self.config_page.read_into(self.cfg)
        config_mod.save(self.cfg)
        self.apply_dghub_link()
        self.run_page.refresh_start_bat()
        self.show_toast("已保存", f"配置已写入 {paths.config_path()}", Toast.SUCCESS)

    def apply_and_rescan(self) -> None:
        self.save_config_from_ui()
        # 全量扫描远超 2 秒，按钮要进 Loading 并给文字状态：
        # 不然连点会起好几个扫描线程去抢同一批文件。
        self.config_page.set_scanning(True)
        self.show_toast("正在重新扫描", "按当前规则重建输出文件夹，可以继续用其他页面",
                        Toast.INFO)

        def work() -> None:
            try:
                result = classifier.scan_all(config_mod.load(), self.ocr, rebuild=True)
            except OSError as e:
                result = ScanResult(error=str(e))
            self.sig_scan_done.emit(result)

        threading.Thread(target=work, name="cun-scan", daemon=True).start()

    def _on_scan_done(self, result: ScanResult) -> None:
        self.config_page.set_scanning(False)
        self.stats_page.refresh()
        if result.error:
            self.show_toast("扫描出错", result.error, Toast.ERROR)
        else:
            self.show_toast("扫描完成",
                            f"寸 {result.cun} 张 · AJ {result.aj} 张 · 共 {result.total} 张",
                            Toast.SUCCESS)

    def open_output(self) -> None:
        directory = self.cfg.output_root
        if not directory:
            self.show_toast("打开失败", "输出目录还没配置", Toast.ERROR)
            return
        try:
            Path(directory).mkdir(parents=True, exist_ok=True)
            os.startfile(directory)                 # noqa: S606 - 就是要交给资源管理器
        except OSError as e:
            self.show_toast("打开失败", str(e), Toast.ERROR)

    def on_mode_changed(self, mode: str) -> None:
        self.cfg.process_mode = mode
        config_mod.save(self.cfg)

    # ----------------------------- 监视 -------------------------------------
    @property
    def watcher_running(self) -> bool:
        return self._watcher is not None and self._watcher.running

    def toggle_watch(self) -> None:
        if self.watcher_running:
            assert self._watcher is not None
            self._watcher.stop()
            self._watcher = None
            self.run_page.set_watch_state(False, "已停止")
            return

        if not self.cfg.screenshots_dir:
            self.show_toast("还没设置截图目录", "去「配置 → 目录」里选一下。", Toast.WARNING)
            return

        self._watcher = Watcher(
            get_cfg=config_mod.load_cached,
            engine=self.ocr,
            on_match=lambda f, rec, m: self.sig_match.emit(f, rec, m),
            on_status=lambda s: self.sig_watch_text.emit(s),
        )
        self._watcher.start()
        self.run_page.set_watch_state(True, "运行中")

    def _on_match_ui(self, filename: str, rec: OcrRecord, matches: list[Category]) -> None:
        keys = "+".join(c.key for c in matches)
        self.run_page.append_log(
            f"✓ {filename}  得分={rec.score} A={rec.attack} M={rec.miss}  [{keys}]")
        self.stats_page.refresh()

    def _update_game_label(self) -> None:
        running = winapi.is_process_running(self.cfg.game_process)
        self.run_page.set_game_text("运行中" if running else "未运行")

    # ----------------------------- 联动与截图 -------------------------------
    def apply_dghub_link(self) -> None:
        """按配置起停内存读取和它的两个消费者（联动数据服务、自动截图）。

        启动时和每次保存配置后都会调，所以开关是立即生效的。
        """
        want_link = self.cfg.dghub.enabled
        want_capture = self.cfg.capture.enabled

        if want_link and (self._link is None or not self._link.running):
            self._link = LinkServer(on_status=lambda s: self.sig_link_text.emit(s))
            self._link.start(self.cfg.dghub.port)
        elif not want_link and self._link is not None:
            self._link.stop()
            self._link = None
            self.run_page.set_link_text("未启用")

        if want_capture and self._capture is None:
            self._capture = CaptureService(
                get_cfg=config_mod.load_cached,
                on_captured=self._on_captured,
                on_status=self._on_capture_status)
        elif not want_capture and self._capture is not None:
            self._capture.shutdown()
            self._capture = None

        want_judge = want_link or want_capture
        if want_judge and (self._judge is None or not self._judge.running):
            self._judge = JudgeMemoryReader(
                get_process_name=lambda: config_mod.load_cached().game_process,
                on_status=lambda s: self.sig_judge_text.emit(s),
                on_delta=lambda _prev, _cur: None,   # 实时增量由插件自己算
                on_song_end=self._on_song_end,
                on_tick=self._on_tick)
            self._judge.start()
        elif not want_judge and self._judge is not None:
            self._judge.stop()
            self._judge = None
            self.run_page.set_judge_text("未启用")

    def _on_capture_status(self, message: str) -> None:
        classifier.log("[CAPTURE] " + message)       # 落盘，方便事后核对时序
        self.sig_log.emit("📸 " + message)

    def _on_tick(self, counts: JudgeCounts) -> None:
        if self._link is not None:
            self._link.update_counts(counts)
        self._track_freeze(counts)

    def _track_freeze(self, counts: JudgeCounts) -> None:
        """判定数冻结＝结算画面已经出来了，这才是截图的时机。

        实测的时序：结算画面显示期间计数块**仍然活着**、冻结在最终值，
        要等玩家离开结算画面内存才释放——所以结算信号本身来得太晚，
        截不到。冻结两秒半就开始尝试，误触发（曲中长空档）由 CaptureService
        里的画面检查挡掉，结算信号那次请求留作兜底。
        """
        now = time.monotonic()
        if counts != self._tick_last:
            self._tick_last = counts
            self._tick_changed_at = now
            return
        # 冻结期间**持续**请求，而不是只请求一次：曲中空档的误触发会跑完自己那
        # 30 秒超时，真正的结算画面可能在那之后才出来，靠重试才接得住。
        # request_capture 本身很便宜：正在跑会被 busy 挡掉，成功之后被同曲去重挡掉。
        if counts.total >= _MIN_NOTES and now - self._tick_changed_at >= _FREEZE_TRIGGER_SEC:
            if self._capture is not None and config_mod.load_cached().capture.enabled:
                self._capture.request_capture(counts)

    def _on_captured(self, path: str, final: JudgeCounts) -> None:
        """截到并存下一张结算图：把内存里的判定数据写进 OCR 缓存。

        这样监视器（或下一次扫描）分类它时完全不用跑 OCR。
        """
        name = Path(path).name
        try:
            size: int | None = Path(path).stat().st_size
        except OSError:
            size = None
        rec = OcrRecord(score=final.score, attack=final.attack, miss=final.miss, size=size)
        if self._watcher is not None and self._watcher.running:
            self._watcher.seed_cache(name, rec)
        else:
            cache = classifier.load_cache()
            cache[name] = rec
            classifier.save_cache(cache)
        classifier.log(f"[CAPTURE] {name} score={rec.score} A={rec.attack} M={rec.miss} (memory)")

    def _on_song_end(self, final: JudgeCounts) -> None:
        """一首歌结束：由判定数换算得分，跑一遍寸规则，把结果发给插件。"""
        cfg = config_mod.load_cached()
        score = final.score
        rank = config_mod.rank_of(score, cfg) or "?"
        matches = [c for c in classifier.classify(score, final.attack, final.miss, cfg)
                   if c.kind in classifier.CUN_KINDS]
        keys = "+".join(c.key for c in matches)

        if self._link is not None:
            self._link.publish_settle({
                "event": "settle",
                "cun": bool(matches),
                "rules": keys,
                "score": score,
                "rank": rank,
                "critical": final.critical,
                "justice": final.justice,
                "attack": final.attack,
                "miss": final.miss,
            })

        summary = f"得分≈{score} {rank} A{final.attack}M{final.miss}"
        verdict = keys if matches else "未寸"
        classifier.log(f"[SETTLE] {summary} [{verdict}]")
        self.sig_log.emit(f"🏁 结算 {summary}  [{verdict}]")

        if cfg.capture.enabled and self._capture is not None:
            self._capture.request_capture(final)


def _app_icon() -> QIcon | None:
    for candidate in (paths.resource_path("assets", "icon.ico"),
                      paths.exe_dir() / "assets" / "icon.ico"):
        if candidate.is_file():
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon
    return None
