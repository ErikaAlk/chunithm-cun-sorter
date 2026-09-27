# -*- coding: utf-8 -*-
"""结算画面自动截图，取代外部截图工具。

内存读取那边发现判定数冻结（＝结算画面已经出来了）之后，这里开始每 0.5 秒
抓一帧游戏画面，确认是成绩画面就等分数滚完再存进截图目录。判定数据直接来自
内存，所以这样存下来的新截图**完全不需要 OCR**。

「是不是成绩画面」靠三道叠加的检查，每一道都只看**跨版本不变**的界面元素：

1. **顶栏**——「JUSTICE CRITICAL」那段黄字黑底。打歌、CLEAR 过场、成绩画面都有，
   TOTAL RESULT、选曲、地图没有。
2. **判定明细面板**——成绩画面中部那几行紫色底条。CLEAR 过场和成绩画面共享**全部**
   顶部 chrome，只有这块面板能把两者分开（生产环境就是这么截错过的）。
3. **没有被动画盖住**——刷新纪录、Rating 上涨时，成绩画面上会先铺一块深色横幅再闪一下。
   面板已经出来了，但这时候截下来的图中间是一块黑。

⚠️ 别拿背景、顶栏底色、头像、称号、曲绘做特征：它们会随游戏版本或玩家设置变。
2.1 及之前的 17 点指纹有 11 个点取在背景和顶栏底色上（另有 2 个在头像和称号上），
游戏升到 2.50、主题换成黄色之后，成绩画面只剩 6~7/17，自动截图一张都截不到。

阈值在 305 张旧版本成绩图和 2.50 版的实机帧上量过，数字写在各常量旁边。
坐标按 1920×1080 标定，其它分辨率（比如 24 寸映射补丁的 3413×1920）按比例缩放。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PIL import Image

from . import paths, winapi
from .models import CaptureConfig, CunConfig, JudgeCounts

REF_W, REF_H = 1920, 1080
POLL_SEC = 0.5

#: 顶栏「JUSTICE CRITICAL」标签那一段。黄字占比实测 0.225~0.239、黑底 0.618~0.624，
#: 两个版本、打歌 / CLEAR / 成绩三种画面都在这个范围；TOTAL RESULT 黑底是 0。
CHROME_RECT = (600, 10, 760, 28)
CHROME_YELLOW_MIN = 0.15
CHROME_DARK_MIN = 0.45

#: 判定明细面板里标签和数字之间那一列，四行紫色底条都从这里经过，没有字。
#: 紫色占比：成绩画面 0.955~0.961（新版多出的 LATE / FAST 行在这一列下面），
#: 打歌、CLEAR、TOTAL RESULT ≤0.02，动画闪白那一下 0.49~0.64。
JUDGE_COLUMN_RECT = (770, 655, 815, 810)
JUDGE_PURPLE_MIN = 0.85

#: 画面正中那条带，干净的成绩画面上全是浅色面板（305 张里深色占比都是 0）；
#: 庆祝动画的深色横幅盖上来时是 0.44~0.77。
OVERLAY_BAND_RECT = (640, 460, 1300, 620)
OVERLAY_DARK_MAX = 0.05

#: 诊断用的进度：一帧最多走到哪一道检查
STAGE_NONE, STAGE_CHROME, STAGE_PANEL, STAGE_CLEAN = 0, 1, 2, 3

CapturedFn = Callable[[str, JudgeCounts], None]
StatusFn = Callable[[str], None]
GetConfigFn = Callable[[], CunConfig]


class Frame:
    """一帧原始像素：BGRX 四字节、行优先、自上而下。"""

    __slots__ = ("buf", "width", "height")

    def __init__(self, buf: bytes, width: int, height: int) -> None:
        self.buf = buf
        self.width = width
        self.height = height

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        i = (y * self.width + x) * 4
        b, g, r = self.buf[i], self.buf[i + 1], self.buf[i + 2]
        return r, g, b

    def to_image(self) -> Image.Image:
        return Image.frombuffer(
            "RGB", (self.width, self.height), self.buf, "raw", "BGRX", 0, 1)


def grab(process_name: str) -> Frame | None:
    """抓一帧游戏客户区。游戏没跑、窗口没了或者被锁屏挡着就返回 ``None``。"""
    pid = winapi.pid_of(process_name or "chusanApp.exe")
    if pid == 0:
        return None
    hwnd = winapi.main_window_of_pid(pid)
    if not hwnd:
        return None
    rect = winapi.client_rect_on_screen(hwnd)
    if rect is None:
        return None
    x, y, w, h = rect
    if w < 640 or h < 360:
        return None                                 # 最小化了，或者是个假窗口
    buf = winapi.grab_screen(x, y, w, h)
    if buf is None:
        return None
    return Frame(buf, w, h)


def _fraction(frame: Frame, rect: tuple[int, int, int, int],
              test: Callable[[int, int, int], bool], step: int) -> float:
    """矩形（1920×1080 坐标）里满足 ``test`` 的像素占比，隔 ``step`` 取一个点。"""
    sx, sy = frame.width / REF_W, frame.height / REF_H
    x1, y1, x2, y2 = rect
    hit = n = 0
    for y in range(y1, y2, step):
        py = min(int(y * sy), frame.height - 1)
        for x in range(x1, x2, step):
            hit += test(*frame.pixel(min(int(x * sx), frame.width - 1), py))
            n += 1
    return hit / n if n else 0.0


def _yellow(r: int, g: int, b: int) -> bool:
    return r >= 170 and g >= 140 and b <= 90


def _black(r: int, g: int, b: int) -> bool:
    return max(r, g, b) <= 40


def _purple(r: int, g: int, b: int) -> bool:
    return b - g >= 70 and b >= r + 20


def _dark_grey(r: int, g: int, b: int) -> bool:
    """庆祝动画那块横幅：暗、而且不怎么饱和。面板上的紫色、彩色大字都不算。"""
    return (299 * r + 587 * g + 114 * b) < 80_000 and max(r, g, b) - min(r, g, b) < 70


def chrome_present(frame: Frame) -> bool:
    """顶栏在不在：打歌、CLEAR 过场、成绩画面都有它。"""
    return (_fraction(frame, CHROME_RECT, _yellow, 2) >= CHROME_YELLOW_MIN
            and _fraction(frame, CHROME_RECT, _black, 2) >= CHROME_DARK_MIN)


def judge_panel_looks_right(frame: Frame) -> bool:
    """判定明细面板出来了没有（用来把 CLEAR 过场挡在外面）。"""
    return _fraction(frame, JUDGE_COLUMN_RECT, _purple, 3) >= JUDGE_PURPLE_MIN


def overlay_covers_panels(frame: Frame) -> bool:
    """成绩画面正被庆祝动画的深色横幅盖着。"""
    return _fraction(frame, OVERLAY_BAND_RECT, _dark_grey, 4) > OVERLAY_DARK_MAX


def stage(frame: Frame) -> int:
    """这一帧走到了第几道检查，``STAGE_CLEAN`` 就是可以存的成绩画面。"""
    if not chrome_present(frame):
        return STAGE_NONE
    if not judge_panel_looks_right(frame):
        return STAGE_CHROME
    if overlay_covers_panels(frame):
        return STAGE_PANEL
    return STAGE_CLEAN


def is_result_screen(frame: Frame) -> bool:
    return stage(frame) == STAGE_CLEAN


def save_png(frame: Frame, directory: str) -> str:
    """按截图工具的命名习惯存进截图目录，返回落盘路径。"""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = d / f"{stamp}.png"
    i = 2
    while path.exists():
        path = d / f"{stamp}_{i}.png"
        i += 1
    img = frame.to_image()
    try:
        img.save(path)
    finally:
        img.close()
    return str(path)


class CaptureService:
    """一次只跑一个截图尝试，同一首歌不重复截。"""

    def __init__(self, get_cfg: GetConfigFn, on_captured: CapturedFn, on_status: StatusFn) -> None:
        self._get_cfg = get_cfg
        self._on_captured = on_captured
        self._on_status = on_status
        self._lock = threading.Lock()
        self._busy = False
        self._last_captured: JudgeCounts | None = None
        self._stop = threading.Event()

    def shutdown(self) -> None:
        self._stop.set()

    def _status(self, msg: str) -> None:
        try:
            self._on_status(msg)
        except Exception:                           # noqa: BLE001
            pass

    def request_capture(self, final: JudgeCounts) -> None:
        """判定数冻结（结算画面出来了）时调，结算信号到达时再兜一次底。

        重复调很便宜：正在跑就直接返回，同一首歌已经截过也直接返回。
        """
        with self._lock:
            if self._stop.is_set() or self._busy or final == self._last_captured:
                return
            self._busy = True
        threading.Thread(target=self._run, args=(final,),
                         name="cun-capture", daemon=True).start()

    def _run(self, final: JudgeCounts) -> None:
        try:
            self._capture_loop(final)
        except Exception as e:                      # noqa: BLE001 - 截图失败不能带崩后台线程
            self._status(f"截图失败：{e}")
        finally:
            with self._lock:
                self._busy = False

    def _capture_loop(self, final: JudgeCounts) -> None:
        cfg = self._get_cfg()
        cap: CaptureConfig = cfg.capture
        start = time.monotonic()
        deadline = start + max(5.0, cap.timeout_s)
        best = -1
        best_frame: Frame | None = None

        while time.monotonic() < deadline and not self._stop.is_set():
            frame = grab(cfg.game_process)
            if frame is not None:
                reached = stage(frame)
                if reached > best:
                    best = reached
                    best_frame = frame
                if reached == STAGE_CLEAN:
                    # chrome 出来了，但分数可能还在滚——等动画走完，复验一次，
                    # 留下**那一帧**而不是现在这帧。
                    self._stop.wait(min(max(cap.delay_s, 0.0), 15.0))
                    settled = grab(cfg.game_process)
                    if settled is not None and is_result_screen(settled):
                        path = save_png(settled, cfg.screenshots_dir)
                        with self._lock:
                            self._last_captured = final
                        elapsed = time.monotonic() - start
                        self._status(
                            f"已截取结算画面 {Path(path).name}（触发后 {elapsed:.1f}s）")
                        try:
                            self._on_captured(path, final)
                        except Exception:           # noqa: BLE001
                            pass
                        return
            self._stop.wait(POLL_SEC)

        if best < 0:
            self._status("未捕获：拿不到游戏画面（窗口不在？）")
            return

        # 把走得最远的那一帧存下来，方便离线看卡在哪一道检查
        note = ""
        if best_frame is not None:
            try:
                d = paths.diag_dir()
                d.mkdir(parents=True, exist_ok=True)
                dump = d / f"capture_{datetime.now():%Y%m%d_%H%M%S}_stage{best}.png"
                img = best_frame.to_image()
                try:
                    img.save(dump)
                finally:
                    img.close()
                note = f"，最佳帧已存 diag\\{dump.name}"
            except OSError:
                pass                                # 诊断而已，存不下就算了
        self._status(f"未捕获到结算画面：{_STAGE_HINTS[best]}{note}")


#: 超时的时候最远走到哪一步，对应的原因
_STAGE_HINTS = {
    STAGE_NONE: "一直没看到游戏顶栏（不在打歌或结算画面）",
    STAGE_CHROME: "没等到判定明细面板（停在 CLEAR 过场，或结算画面被跳过、切换了视图）",
    STAGE_PANEL: "判定明细面板一直被动画挡着",
    STAGE_CLEAN: "",
}
