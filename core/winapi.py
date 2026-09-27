# -*- coding: utf-8 -*-
"""用到的那点 Win32：进程、优先级、窗口、抓帧、单实例、标题栏、Mica、系统外观。

全走 ctypes，不引 pywin32 / psutil / mss——这个程序要打成安装包分发，
少一个二进制依赖就少一类「装上跑不起来」。

⚠️ 每个函数的 ``argtypes`` / ``restype`` 都必须写全。ctypes 默认把参数当
``c_int``，64 位下句柄（``HANDLE`` / ``HWND`` / ``HDC``）会被截成低 32 位，
表现是「调用返回失败但错误码看着没问题」，极难查。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

try:                                    # 只有 Windows 有
    import winreg
except ImportError:
    winreg = None                       # type: ignore[assignment]

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
else:                                   # 只为了让非 Windows 上也能 import 做单元测试
    kernel32 = user32 = gdi32 = None    # type: ignore[assignment]

HANDLE = wintypes.HANDLE
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

MAX_PATH = 260
TH32CS_SNAPPROCESS = 0x00000002
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
IDLE_PRIORITY_CLASS = 0x00000040
ERROR_ALREADY_EXISTS = 183
GW_OWNER = 4
SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0
DWMWA_USE_IMMERSIVE_DARK_MODE = 20      # Win10 20H1+ / Win11
DWMWA_SYSTEMBACKDROP_TYPE = 38          # Win11 22H2（22621）+
DWMWA_MICA_EFFECT = 1029                # Win11 21H2（22000）上的未公开前身
#: DWM_SYSTEMBACKDROP_TYPE 里的 DWMSBT_MAINWINDOW，就是 Mica
DWMSBT_MAINWINDOW = 2
#: 支持 DWMWA_SYSTEMBACKDROP_TYPE 的最低内部版本号
_BUILD_BACKDROP = 22621
#: Windows 11 的起始内部版本号
_BUILD_WIN11 = 22000
#: SystemParametersInfo 的 SPI_GETCLIENTAREAANIMATION，「减少动态效果」的取反
SPI_GETCLIENTAREAANIMATION = 0x1042
SPI_GETHIGHCONTRAST = 0x0042
HCF_HIGHCONTRASTON = 0x00000001
DWMSBT_NONE = 1
#: 弹出菜单这类独立小窗口用系统圆角（Windows 11）
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


class HIGHCONTRASTW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwFlags", wintypes.DWORD),
                ("lpszDefaultScheme", wintypes.LPWSTR)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _declare() -> None:
    """给所有用到的 API 写死签名。见模块开头那条警告。"""
    k, u, g = kernel32, user32, gdi32

    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k.CreateToolhelp32Snapshot.restype = HANDLE
    k.Process32FirstW.argtypes = [HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k.Process32FirstW.restype = wintypes.BOOL
    k.Process32NextW.argtypes = [HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k.Process32NextW.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [HANDLE]
    k.CloseHandle.restype = wintypes.BOOL
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = HANDLE
    k.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.GetExitCodeProcess.restype = wintypes.BOOL
    k.QueryFullProcessImageNameW.argtypes = [
        HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k.QueryFullProcessImageNameW.restype = wintypes.BOOL
    k.GetCurrentProcess.argtypes = []
    k.GetCurrentProcess.restype = HANDLE
    k.SetPriorityClass.argtypes = [HANDLE, wintypes.DWORD]
    k.SetPriorityClass.restype = wintypes.BOOL
    k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateMutexW.restype = HANDLE
    k.ReadProcessMemory.argtypes = [
        HANDLE, wintypes.LPCVOID, wintypes.LPVOID, ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t)]
    k.ReadProcessMemory.restype = wintypes.BOOL
    k.VirtualQueryEx.argtypes = [HANDLE, wintypes.LPCVOID, wintypes.LPVOID, ctypes.c_size_t]
    k.VirtualQueryEx.restype = ctypes.c_size_t

    u.EnumWindows.argtypes = [ENUM_WINDOWS_PROC, wintypes.LPARAM]
    u.EnumWindows.restype = wintypes.BOOL
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.GetWindowThreadProcessId.restype = wintypes.DWORD
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.IsWindowVisible.restype = wintypes.BOOL
    u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    u.GetWindow.restype = wintypes.HWND
    u.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    u.GetClientRect.restype = wintypes.BOOL
    u.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
    u.ClientToScreen.restype = wintypes.BOOL
    u.GetDC.argtypes = [wintypes.HWND]
    u.GetDC.restype = wintypes.HDC
    u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    u.ReleaseDC.restype = ctypes.c_int
    u.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT,
                                        ctypes.c_void_p, wintypes.UINT]
    u.SystemParametersInfoW.restype = wintypes.BOOL

    g.CreateCompatibleDC.argtypes = [wintypes.HDC]
    g.CreateCompatibleDC.restype = wintypes.HDC
    g.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    g.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    g.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    g.SelectObject.restype = wintypes.HGDIOBJ
    g.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    g.BitBlt.restype = wintypes.BOOL
    g.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                            wintypes.LPVOID, ctypes.POINTER(BITMAPINFO), wintypes.UINT]
    g.GetDIBits.restype = ctypes.c_int
    g.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    g.DeleteObject.restype = wintypes.BOOL
    g.DeleteDC.argtypes = [wintypes.HDC]
    g.DeleteDC.restype = wintypes.BOOL


if _IS_WINDOWS:
    _declare()


# ----------------------------- 进程 -----------------------------------------
def _bare_name(name: str) -> str:
    """``chusanApp.exe`` → ``chusanapp``，比较用。"""
    n = (name or "").strip().lower()
    return n[:-4] if n.endswith(".exe") else n


def iter_processes() -> list[tuple[int, str]]:
    """当前所有进程的 ``(pid, 映像名)``。拿不到快照就返回空列表。"""
    if not _IS_WINDOWS:
        return []
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return []
    out: list[tuple[int, str]] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            return []
        while True:
            out.append((int(entry.th32ProcessID), entry.szExeFile))
            if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snap)
    return out


def pid_of(name: str) -> int:
    """按映像名找第一个进程的 pid；找不到返回 0。"""
    bare = _bare_name(name)
    if not bare:
        return 0
    for pid, exe in iter_processes():
        if _bare_name(exe) == bare:
            return pid
    return 0


def is_process_running(name: str) -> bool:
    return pid_of(name) != 0


def is_process_alive(pid: int) -> bool:
    """指定 pid 还活着没有。"""
    if not _IS_WINDOWS or pid <= 0:
        return False
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(h, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(h)


def process_image_path(pid: int) -> str:
    """进程的 exe 完整路径；拿不到返回空串。首次运行向导靠它自动认出游戏目录。"""
    if not _IS_WINDOWS or pid <= 0:
        return ""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(MAX_PATH * 4)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


def set_idle_priority() -> bool:
    """把自己降到 IDLE 优先级，OCR 再忙也抢不走游戏的帧。"""
    if not _IS_WINDOWS:
        return False
    try:
        return bool(kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), IDLE_PRIORITY_CLASS))
    except OSError:
        return False


# ----------------------------- 单实例 ---------------------------------------
_mutex_handle: int | None = None        # 进程活着期间一直握着


def acquire_single_instance(name: str) -> bool:
    """抢命名互斥体。抢到＝本进程是第一个，返回 ``True``。"""
    global _mutex_handle
    if not _IS_WINDOWS:
        return True
    handle = kernel32.CreateMutexW(None, True, name)
    if not handle:
        return True                                     # 建不出来就别拦着启动
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _mutex_handle = handle
    return True


# ----------------------------- 外观 -----------------------------------------
def set_app_user_model_id(app_id: str) -> None:
    """让任务栏显示本程序的名字和图标，而不是 ``python.exe``。"""
    if not _IS_WINDOWS:
        return
    try:
        shell32 = ctypes.WinDLL("shell32")
        shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
        shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (OSError, AttributeError):
        pass


def _dwm_set(hwnd: int, attr: int, value: int) -> bool:
    """``DwmSetWindowAttribute`` 设一个 int 属性。返回 0 只说明请求被接受，不等于桌面上真的变了。"""
    if not _IS_WINDOWS or not hwnd:
        return False
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
        arg = ctypes.c_int(value)
        return dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), attr, ctypes.byref(arg), ctypes.sizeof(arg)) == 0
    except (OSError, AttributeError):
        return False


def set_titlebar_dark(hwnd: int, dark: bool) -> None:
    """标题栏跟着应用主题走。非客户区归 DWM 管，Qt 的样式表刷不到那一条。"""
    _dwm_set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0)


def round_corners(hwnd: int) -> bool:
    """弹出菜单、下拉列表这类顶层小窗口用 Windows 11 的系统圆角。

    QSS 的圆角对顶层窗口无效，窗口本身还是方的。Windows 10 上静默失败。
    """
    return _dwm_set(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)


def apps_use_light_theme() -> bool | None:
    """系统的应用主题是不是浅色。读不到返回 ``None``。

    Qt 6.5 起 ``QStyleHints.colorScheme()`` 通常够用，这条只是兜底。
    """
    if not _IS_WINDOWS or winreg is None:
        return None
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return bool(winreg.QueryValueEx(key, "AppsUseLightTheme")[0])
    except (OSError, ValueError):
        return None


def text_scale_factor() -> float:
    """辅助功能里「放大文本」的倍数（1.0 ~ 2.25）。没设置过就是 1.0。

    这个设置**独立于**显示缩放：Qt 会处理显示缩放，但不碰它，所以字号要由
    我们自己乘一次。从没调过的机器上根本没有这个键，不是错误。
    """
    if not _IS_WINDOWS or winreg is None:
        return 1.0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Accessibility") as key:
            percent = int(winreg.QueryValueEx(key, "TextScaleFactor")[0])
    except (OSError, ValueError, TypeError):
        return 1.0
    return min(2.25, max(1.0, percent / 100.0))


def transparency_enabled() -> bool:
    """「设置 → 个性化 → 颜色 → 透明效果」。缺键时按开启处理，和系统默认一致。

    关掉之后 DWM 照样接受 Mica 请求，但画出来是一块系统灰，不是我们的底色，
    所以要主动退回实色（DESIGN.md 16.3）。
    """
    if not _IS_WINDOWS or winreg is None:
        return False
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return bool(winreg.QueryValueEx(key, "EnableTransparency")[0])
    except (OSError, ValueError):
        return True


def high_contrast() -> bool:
    """系统开了高对比度主题。材质要让位。"""
    if not _IS_WINDOWS:
        return False
    try:
        hc = HIGHCONTRASTW(ctypes.sizeof(HIGHCONTRASTW), 0, None)
        if user32.SystemParametersInfoW(SPI_GETHIGHCONTRAST, ctypes.sizeof(hc),
                                        ctypes.byref(hc), 0):
            return bool(hc.dwFlags & HCF_HIGHCONTRASTON)
    except (OSError, AttributeError):
        pass
    return False


def animations_enabled() -> bool:
    """系统是否允许动画。关掉「动画效果」＝要求减少动态效果。"""
    if not _IS_WINDOWS:
        return True
    try:
        enabled = wintypes.BOOL()
        if user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0,
                                        ctypes.byref(enabled), 0):
            return bool(enabled.value)
    except (OSError, AttributeError):
        pass
    return True


def windows_build() -> int:
    """当前系统的内部版本号（Win11 21H2 是 22000）。拿不到就返回 0。

    别用 ``sys.getwindowsversion()``：没在清单里声明兼容性的进程会被
    兼容性垫片糊住，Win11 上读回来是 6.2（Win8）。``RtlGetVersion`` 不受这层影响。
    """
    if not _IS_WINDOWS:
        return 0

    class _OSVERSIONINFOW(ctypes.Structure):
        _fields_ = [("dwOSVersionInfoSize", wintypes.ULONG),
                    ("dwMajorVersion", wintypes.ULONG),
                    ("dwMinorVersion", wintypes.ULONG),
                    ("dwBuildNumber", wintypes.ULONG),
                    ("dwPlatformId", wintypes.ULONG),
                    ("szCSDVersion", wintypes.WCHAR * 128)]

    try:
        ntdll = ctypes.WinDLL("ntdll")
        ntdll.RtlGetVersion.argtypes = [ctypes.POINTER(_OSVERSIONINFOW)]
        ntdll.RtlGetVersion.restype = ctypes.c_long
        info = _OSVERSIONINFOW()
        info.dwOSVersionInfoSize = ctypes.sizeof(info)
        if ntdll.RtlGetVersion(ctypes.byref(info)) != 0:
            return 0
        return int(info.dwBuildNumber)
    except (OSError, AttributeError):
        return 0


def supports_mica() -> bool:
    """这台机器画不画得出 Mica。Windows 11 起才有。

    要在建窗口**之前**问：窗口底色得先设成透明，材质才透得上来，
    而透明是个建窗口时就要定下来的属性。
    """
    return _IS_WINDOWS and windows_build() >= _BUILD_WIN11


class _MARGINS(ctypes.Structure):
    _fields_ = [("cxLeftWidth", ctypes.c_int), ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int), ("cyBottomHeight", ctypes.c_int)]


def enable_mica(hwnd: int) -> bool:
    """给窗口铺上 Mica 材质。成功返回 ``True``。

    22H2 起用公开的 ``DWMWA_SYSTEMBACKDROP_TYPE``，21H2 只有未公开的
    ``DWMWA_MICA_EFFECT``；两个都试。

    ⚠️ **两步缺一不可**，只做第一步的表现是「属性设上了、回读也对，但界面毫无变化」：

    1. ``DwmSetWindowAttribute`` 声明要哪种材质；
    2. ``DwmExtendFrameIntoClientArea`` 传 ``-1`` 的四边，把玻璃摊到整个客户区。
       不摊的话材质只出现在标题栏那一条，客户区还是老样子。

    另外调用方要负责让窗口自己那层像素透明，否则材质被整个盖在下面。
    """
    if not _IS_WINDOWS or not hwnd:
        return False
    build = windows_build()
    if build < _BUILD_WIN11:
        return False
    attr, value = ((DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_MAINWINDOW)
                   if build >= _BUILD_BACKDROP else (DWMWA_MICA_EFFECT, 1))
    if not _dwm_set(hwnd, attr, value):
        return False
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        dwmapi.DwmExtendFrameIntoClientArea.argtypes = [
            wintypes.HWND, ctypes.POINTER(_MARGINS)]
        dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
        margins = _MARGINS(-1, -1, -1, -1)
        return dwmapi.DwmExtendFrameIntoClientArea(
            wintypes.HWND(hwnd), ctypes.byref(margins)) == 0
    except (OSError, AttributeError):
        return False


def disable_mica(hwnd: int) -> None:
    """撤掉 Mica（关了透明效果、开了高对比度时）。窗口底由调用方换回实色。"""
    if windows_build() >= _BUILD_BACKDROP:
        _dwm_set(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE)
    else:
        _dwm_set(hwnd, DWMWA_MICA_EFFECT, 0)


def set_dpi_awareness() -> None:
    """声明 per-monitor DPI 感知。

    必须在建 Qt 应用之前调：不感知的话系统会做坐标缩放，
    ``GetClientRect`` 和抓屏坐标全部对不上，截出来的是画面的一角。
    """
    if not _IS_WINDOWS:
        return
    try:                                                # Win10 1703+
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):    # PER_MONITOR_AWARE_V2
            return
    except (OSError, AttributeError):
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)   # PROCESS_PER_MONITOR_DPI_AWARE
    except (OSError, AttributeError):
        try:
            user32.SetProcessDPIAware()
        except (OSError, AttributeError):
            pass


# ----------------------------- 窗口与抓帧 -----------------------------------
def main_window_of_pid(pid: int) -> int:
    """进程的主窗口句柄：第一个可见、无属主的顶层窗口。找不到返回 0。"""
    if not _IS_WINDOWS or pid <= 0:
        return 0
    found: list[int] = []

    def _cb(hwnd, _lparam):
        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value != pid:
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindow(hwnd, GW_OWNER):            # 有属主的是对话框，不是主窗口
            return True
        found.append(int(hwnd))
        return False                                    # 停止枚举

    callback = ENUM_WINDOWS_PROC(_cb)                   # 保持引用直到 EnumWindows 返回
    user32.EnumWindows(callback, 0)
    return found[0] if found else 0


def client_rect_on_screen(hwnd: int) -> tuple[int, int, int, int] | None:
    """窗口客户区在屏幕上的 ``(x, y, w, h)``；窗口没了或最小化返回 ``None``。"""
    if not _IS_WINDOWS or not hwnd:
        return None
    rc = RECT()
    if not user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(rc)):
        return None
    w, h = rc.right - rc.left, rc.bottom - rc.top
    if w <= 0 or h <= 0:
        return None
    origin = POINT(0, 0)
    if not user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(origin)):
        return None
    return origin.x, origin.y, w, h


def grab_screen(x: int, y: int, w: int, h: int) -> bytes | None:
    """屏幕上一块区域的原始像素，行优先、每像素 BGRX 四字节，自上而下。

    游戏跑的是无边框窗口，屏幕内容就是游戏画面，直接从屏幕 DC 拷比
    ``PrintWindow`` 稳（后者在 D3D 全屏窗口上经常拿到全黑）。
    锁屏 / 安全桌面下会失败，返回 ``None``。
    """
    if not _IS_WINDOWS or w <= 0 or h <= 0:
        return None
    screen_dc = user32.GetDC(None)
    if not screen_dc:
        return None
    mem_dc = None
    bitmap = None
    old = None
    try:
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, w, h)
        if not mem_dc or not bitmap:
            return None
        old = gdi32.SelectObject(mem_dc, bitmap)
        if not gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, x, y, SRCCOPY):
            return None

        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = w
        info.bmiHeader.biHeight = -h                    # 负数＝自上而下，省一次翻转
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB

        buf = ctypes.create_string_buffer(w * h * 4)
        got = gdi32.GetDIBits(mem_dc, bitmap, 0, h, buf, ctypes.byref(info), DIB_RGB_COLORS)
        if got != h:
            return None
        return buf.raw
    finally:
        if old and mem_dc:
            gdi32.SelectObject(mem_dc, old)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if mem_dc:
            gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)
