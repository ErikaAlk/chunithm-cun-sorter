# -*- coding: utf-8 -*-
"""主窗口：侧栏 + 三页 + 托盘，以及各页共用的那几个后台服务。

窗口结构照 DESIGN.md 16.2：左侧栏 224（窗口窄于 840 收成 72 宽的图标竖栏），
右边是页面；系统标题栏保留，Mica 铺满标题栏、侧栏和页面底（16.3）。

后台线程（监视、内存读取、联动、截图）的回调**一律通过信号**回到界面线程。
直接从工作线程碰部件在 Qt 里是未定义行为，偶发崩溃最难查。
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QStackedWidget, QStyle,
                               QStyledItemDelegate, QSystemTrayIcon, QVBoxLayout, QWidget)

from core import classifier, paths, winapi
from core import config as config_mod
from core.capture import CaptureService
from core.judge_memory import JudgeMemoryReader
from core.link_server import LinkServer
from core.models import Category, CunConfig, JudgeCounts, OcrRecord, ScanResult
from core.ocr import OcrEngine
from core.version import APP_NAME
from core.watcher import Watcher

from . import icons, theme, widgets
from .first_run import ask_for_game_root
from .page_config import ConfigPage
from .page_run import RunPage
from .page_stats import StatsPage
from .theme import metrics as m
from .widgets import Anim, Toast

#: 判定数冻结多久算「结算画面已经出来了」
_FREEZE_TRIGGER_SEC = 2.5
#: 少于这么多音符不当一次有效演奏
_MIN_NOTES = 10
#: 侧栏三项：(标题, 图标)
_NAV = (("配置", "settings"), ("统计", "stats"), ("运行", "run"))
#: WM_SETTINGCHANGE / WM_THEMECHANGED：系统改了透明效果、对比度、文本大小或动画
_WM_SETTINGCHANGE, _WM_THEMECHANGED = 0x001A, 0x031A


# ----------------------------- 侧栏 -----------------------------------------
class _NavDelegate(QStyledItemDelegate):
    """侧栏项：选中换实心图标，图标和文字用主题色；底是 fill8、圆角 12，由 NavList 画。"""

    def __init__(self, nav: "NavList") -> None:
        super().__init__(nav)
        self.nav = nav

    def sizeHint(self, option, _index) -> QSize:    # noqa: N802
        return QSize(option.rect.width(), theme.scaled(m.NAV_ITEM) + 2)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect).adjusted(0, 1, 0, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rad = float(m.RADIUS_MENU)
        if option.state & QStyle.StateFlag.State_MouseOver and not selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.color("hover"))
            painter.drawRoundedRect(r, rad, rad)
        if (self.nav.hasFocus() and widgets.keyboard_focus()
                and index.row() == self.nav.currentRow()):
            w = m.FOCUS_RING_WIDTH
            painter.setPen(QPen(theme.color("focusRing"), w))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(r.adjusted(w / 2, w / 2, -w / 2, -w / 2), rad, rad)

        size = m.ICON_ACTION
        x = (r.left() + m.PAD_CONTROL_X - m.GAP_RELATED if self.nav.expanded
             else r.center().x() - size / 2)
        box = QRectF(round(x), round(r.center().y() - size / 2), size, size)
        tint = theme.color("primaryText" if selected else "label1")
        icons.paint(painter, index.data(Qt.ItemDataRole.UserRole), box, tint, solid=selected)
        if self.nav.expanded:
            painter.setFont(theme.font(theme.TITLE if selected else theme.BODY))
            painter.setPen(tint)
            text = QRectF(box.right() + m.PAD_CONTROL_Y, r.top(),
                          r.right() - box.right() - m.PAD_CONTROL_X, r.height())
            painter.drawText(text, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             index.data(Qt.ItemDataRole.DisplayRole))
        painter.restore()


class NavList(QListWidget):
    """一级导航。选中项的底是一块会滑动的圆角块：换页时从旧项滑到新项。"""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("NavList")
        self.setProperty("ownFocusRing", True)
        self.setAccessibleName("一级导航")
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.expanded = True
        self.setItemDelegate(_NavDelegate(self))
        for title, icon in _NAV:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, icon)
            self.addItem(item)
        self._y = Anim(self, on_change=self.viewport().update)
        self.currentRowChanged.connect(lambda _: self.glide())

    def _row_rect(self) -> QRectF:
        item = self.currentItem()
        return QRectF(self.visualItemRect(item)).adjusted(0, 1, 0, -1) if item else QRectF()

    def glide(self, instant: bool = False) -> None:
        rect = self._row_rect()
        if not rect.isEmpty():
            self._y.to(rect.top(), "menu", instant=instant or not self.isVisible())

    def set_expanded(self, expanded: bool) -> None:
        self.expanded = expanded
        # 收成竖栏时名字挪到 Tooltip 里（16.2：悬停显示名称）
        for i in range(self.count()):
            self.item(i).setToolTip("" if expanded else self.item(i).text())
        self.doItemsLayout()
        self.glide(instant=True)
        self.viewport().update()

    def resizeEvent(self, e) -> None:               # noqa: N802
        super().resizeEvent(e)
        self.glide(instant=True)

    def showEvent(self, e) -> None:                 # noqa: N802
        super().showEvent(e)
        self.glide(instant=True)

    def paintEvent(self, e) -> None:                # noqa: N802
        rect = self._row_rect()
        if not rect.isEmpty():
            p = QPainter(self.viewport())
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("fill8"))
            rad = float(m.RADIUS_MENU)
            p.drawRoundedRect(QRectF(rect.left(), self._y.value, rect.width(), rect.height()),
                              rad, rad)
            p.end()
        super().paintEvent(e)


# ----------------------------- 主窗口 ---------------------------------------
class MainWindow(QMainWindow):
    # 工作线程 → 界面线程
    sig_toast = Signal(str, bool)
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
        self._expanded: bool | None = None

        # 判定数冻结的追踪状态，见 _track_freeze
        self._tick_last = JudgeCounts()
        self._tick_changed_at = 0.0

        self.setWindowTitle(APP_NAME)
        icon = _app_icon()
        if icon is not None:
            self.setWindowIcon(icon)

        # 透明属性**只能在建窗前设一次**，show() 之后改会重建原生窗口。
        # 所以只要系统画得出 Mica 就一直设着；材质铺不上时由 AppRoot 的 opaque 属性铺实色。
        self._mica_capable = winapi.supports_mica()
        if self._mica_capable:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Qt 自带的下拉、菜单「卷下来」效果会先在它自己的位置播一遍，再被挪走，看着是跳一下
        for effect in (Qt.UIEffect.UI_AnimateCombo, Qt.UIEffect.UI_AnimateMenu,
                       Qt.UIEffect.UI_FadeMenu):
            QApplication.setEffectEnabled(effect, False)

        self._build_ui()
        self._wire_signals()
        self.setMinimumSize(m.WINDOW_MIN_WIDTH, m.WINDOW_MIN_HEIGHT)
        self._fit_to_screen()

        self._game_timer = QTimer(self)
        self._game_timer.timeout.connect(self._update_game_label)
        self._game_timer.start(4000)
        self._update_game_label()

        self._tray = self._build_tray(icon)
        # 系统设置变化的消息一次会来好几条（WM_SETTINGCHANGE 常常成串），停下来再刷一次
        self._settings_timer = QTimer(self)
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(150)
        self._settings_timer.timeout.connect(self.apply_appearance)
        QTimer.singleShot(0, self._after_shown)

    # ----------------------------- 组装 -------------------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        root.setProperty("opaque", "false" if self._mica_capable else "true")
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # 侧栏不单独铺底：桌面上直接露出 Mica，靠间距和页面分开，不画分割线（16.2）
        self.nav_pane = QWidget()
        self.nav_pane.setObjectName("NavPane")
        side = QVBoxLayout(self.nav_pane)
        side.setContentsMargins(m.GAP_INLINE, m.GAP_INLINE, m.GAP_INLINE, m.GAP_INLINE)
        self.nav = NavList()
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._page_changed)
        side.addWidget(self.nav)
        row.addWidget(self.nav_pane)

        self.config_page = ConfigPage(self)
        self.stats_page = StatsPage(self)
        self.run_page = RunPage(self)
        self.pages = (self.config_page, self.stats_page, self.run_page)

        self.stack = QStackedWidget()
        self.stack.setObjectName("ContentPane")
        for page in self.pages:
            self.stack.addWidget(page)
        row.addWidget(self.stack, 1)

        self.setCentralWidget(root)
        self.toast = Toast(root)
        widgets.install_focus_tracker(QApplication.instance())

    def _fit_to_screen(self) -> None:
        """默认 1120×760（逻辑像素），按可用屏幕收一收，然后居中。

        高缩放比的小屏上可用区可能只有 1280×680（1920×1080 跑 150%），照搬会顶满整个高度。
        """
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.resize(m.WINDOW_WIDTH, m.WINDOW_HEIGHT)
            return
        avail = screen.availableGeometry()
        self.resize(min(m.WINDOW_WIDTH, int(avail.width() * 0.92)),
                    min(m.WINDOW_HEIGHT, int(avail.height() * 0.92)))
        frame = self.frameGeometry()
        frame.moveCenter(avail.center())
        self.move(frame.topLeft())

    def _wire_signals(self) -> None:
        self.sig_toast.connect(lambda text, error: self.toast.show_message(text, error=error))
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
        menu.aboutToShow.connect(lambda: winapi.round_corners(int(menu.winId())))
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.show()
        self._tray_menu = menu
        return tray

    def _after_shown(self) -> None:
        """窗口摆出来之后再做的事：标题栏、材质、首次运行、联动开关。"""
        self._apply_material()
        app = QApplication.instance()
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._system_scheme_changed)
        self._ensure_game_root()
        self.apply_dghub_link()

    # ----------------------------- 主题与材质 -------------------------------
    def _apply_material(self) -> None:
        """Mica 能铺就铺，铺不上（Windows 10、关了透明效果、高对比度）退回实色底（16.3）。

        ⚠️ Mica 是两步：声明材质 + 把玻璃摊进客户区，``winapi.enable_mica`` 里两步都做了。
        DWM 返回成功只说明请求被接受，验收要看真实桌面截图。
        """
        hwnd = int(self.winId())
        winapi.set_titlebar_dark(hwnd, theme.is_dark())
        want = (self._mica_capable and winapi.transparency_enabled()
                and not winapi.high_contrast())
        on = want and winapi.enable_mica(hwnd)
        if self._mica_capable and not on:
            winapi.disable_mica(hwnd)
        root = self.centralWidget()
        root.setProperty("opaque", "false" if on else "true")
        root.style().unpolish(root)
        root.style().polish(root)
        root.update()

    def _system_scheme_changed(self, _scheme) -> None:
        if theme.follows_system():
            self.apply_appearance()

    def nativeEvent(self, event_type, message):     # noqa: N802
        if event_type == b"windows_generic_MSG":
            import ctypes
            from ctypes import wintypes
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            timer = getattr(self, "_settings_timer", None)   # 构造到一半时还没有
            if timer is not None and msg.message in (_WM_SETTINGCHANGE, _WM_THEMECHANGED):
                timer.start()
        return super().nativeEvent(event_type, message)

    def apply_appearance(self) -> None:
        """按配置重定深浅，重读系统的文本大小和动画设置，就地重新上色（不重建页面）。"""
        theme.set_appearance(self.cfg.appearance)
        app = QApplication.instance()
        if app is not None:
            theme.apply(app)
        widgets.restyle_tree(self)
        self._apply_material()

    # ----------------------------- 导航 -------------------------------------
    def _page_changed(self, index: int) -> None:
        if index < 0:
            return
        target = self.pages[index]
        if self.stack.currentWidget() is not target and self.isVisible():
            widgets.fade_in(target)
        self.stack.setCurrentWidget(target)
        if target is self.stats_page:
            self.stats_page.refresh()

    def resizeEvent(self, event) -> None:            # noqa: N802
        super().resizeEvent(event)
        self.toast.parent_resized()
        width = self.centralWidget().width() or self.width()
        expanded = width >= m.BREAK_EXPANDED
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self.nav_pane.setFixedWidth(m.NAV_EXPANDED if expanded else m.NAV_RAIL)
        self.nav.set_expanded(expanded)
        margin = m.PAGE_MARGIN_EXPANDED if expanded else m.PAGE_MARGIN_MEDIUM
        for page in self.pages:
            page.set_margin(margin)

    # ----------------------------- 窗口行为 ---------------------------------
    def _ensure_game_root(self) -> None:
        """还不知道截图目录在哪就问一次。"""
        if self.cfg.screenshots_dir:
            return
        root = ask_for_game_root(self.cfg, self)
        if root is None:
            self.show_toast("未设置游戏目录，可以在“配置”页补上")
            return
        config_mod.apply_game_root(self.cfg, root)
        config_mod.save(self.cfg)
        self.config_page.refresh_paths()
        self.run_page.refresh_start_bat()

    def closeEvent(self, event) -> None:             # noqa: N802
        """监视还在跑就缩托盘，没在跑就真退出。"""
        if self._quitting or not self.watcher_running:
            self._shutdown()
            event.accept()
            return
        event.ignore()
        self.hide()
        self._tray.showMessage(APP_NAME, "已最小化到托盘，继续在后台监视",
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
        self._tray.showMessage(APP_NAME, "已随游戏启动，正在后台监视",
                               QSystemTrayIcon.MessageIcon.Information, 3000)

    # ----------------------------- 选择器 -----------------------------------
    def pick_folder(self, title: str = "选择文件夹", start: str = "") -> str:
        return QFileDialog.getExistingDirectory(self, title, start)

    def pick_file(self, title: str, filter_text: str) -> str:
        path, _ = QFileDialog.getOpenFileName(self, title, "", filter_text)
        return path

    # ----------------------------- 提示 -------------------------------------
    def show_toast(self, text: str, *, error: bool = False,
                   action: tuple[str, object] | None = None) -> None:
        """底部提示。带动作的（撤销）只能在界面线程里调；后台线程走 ``sig_toast``。"""
        if action is not None:
            self.toast.show_message(text, error=error, action=action)
        else:
            self.sig_toast.emit(text, error)

    # ----------------------------- 配置 -------------------------------------
    def save_settings(self) -> None:
        """设置改完立即写盘，并让依赖它的后台服务跟上（DESIGN.md 11.2）。"""
        config_mod.save(self.cfg)
        self.apply_dghub_link()

    def rescan(self) -> None:
        # 全量扫描远超 2 秒，按钮要进 Loading：不然连点会起好几个扫描线程去抢同一批文件
        self.config_page.set_scanning(True)

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
            self.show_toast(f"扫描失败：{result.error}", error=True)
        else:
            self.show_toast(f"已扫描 {result.total:,} 张 ｜ 寸 {result.cun} ｜ AJ {result.aj}")

    def open_output(self) -> None:
        directory = self.cfg.output_root
        if not directory:
            self.show_toast("未设置输出目录，先在上面选一个", error=True)
            return
        try:
            Path(directory).mkdir(parents=True, exist_ok=True)
            os.startfile(directory)                 # noqa: S606 - 就是要交给资源管理器
        except OSError as e:
            self.show_toast(f"无法打开输出目录：{e}", error=True)

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
            self.show_toast("未设置截图目录，先在“配置”页选择", error=True)
            return

        self._watcher = Watcher(
            get_cfg=config_mod.load_cached,
            engine=self.ocr,
            on_match=lambda f, rec, hits: self.sig_match.emit(f, rec, hits),
            on_status=lambda s: self.sig_watch_text.emit(s),
        )
        self._watcher.start()
        self.run_page.set_watch_state(True, "运行中")

    def _on_match_ui(self, filename: str, rec: OcrRecord, matches: list[Category]) -> None:
        keys = "+".join(c.key for c in matches)
        score = f"{rec.score:,}" if rec.score is not None else "?"
        self._log(f"命中  {filename}  {score}  A{rec.attack} M{rec.miss}  {keys}")
        self.stats_page.refresh()

    def _log(self, text: str) -> None:
        self.sig_log.emit(f"{datetime.now():%H:%M:%S}  {text}")

    def _update_game_label(self) -> None:
        running = winapi.is_process_running(self.cfg.game_process)
        self.run_page.set_game_text("运行中" if running else "未运行")

    # ----------------------------- 联动与截图 -------------------------------
    def apply_dghub_link(self) -> None:
        """按配置起停内存读取和它的两个消费者（联动数据服务、自动截图）。

        启动时和每次改完设置都会调，所以开关是立即生效的。
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
        self._log("截图  " + message)

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
        self._log(f"结算  {score:,}  {rank}  A{final.attack} M{final.miss}  {verdict}")

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
