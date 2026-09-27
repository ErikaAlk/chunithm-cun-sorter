# CLAUDE.md

Claude 在本仓库（寸录 / chunithm-cun-sorter）工作时的约定与速查。
人看的现状和用法在 [README.md](README.md)。

## 约定（必须遵守）

- **README 同步**：每次做了功能 / 行为 / 配置项 / 命令 / 版本上的改动，都要在**同一次改动**里
  更新 `README.md` 的相应小节（功能特性、界面说明、判定与整理、`cun_config.json` 配置表、
  版本号、FAQ 等），并在 [更新记录.md](更新记录.md) 里补一条带日期和版本号的条目。
- **版本号和应用名只有一处真源**：`core/version.py`。`__version__` 供 exe 的版本资源、
  安装包文件名、控制面板里的卸载项；`APP_NAME` 供窗口标题、托盘、exe 文件名、快捷方式、
  自启注册表值名。别在别处再写一份。
- 发版时一并更新 README 里的版本号与安装包文件名。
- **界面改动先读 `~\.claude\DESIGN.md`**。本项目遵循的规范版本记在
  `ui/theme/tokens.py` 的 `DESIGN_SYSTEM_REVISION`，当前是 `2026.08.31-a11y-baseline`。
  项目覆盖全局默认的地方全部登记在同文件的 `OVERRIDES` 里，加覆盖要连原因一起写。

## 这是什么

CHUNITHM「寸」成绩识别 + 截图归档 + DGHub 联动。**PySide6 桌面程序**，托盘常驻，
PyInstaller + Inno Setup 出安装包。

v2.0 之前是 WinUI 3 / .NET 8（`CunSorter/`），已整体删除；再往前 v1.0 是 Python + qfluentwidgets。
要看旧实现去 git 历史。

## 架构

方向单向，`core/` 不 import `ui/`：

```
main.py            界面入口（--watch 随游戏启动）    cli.py   命令行入口
   ↓                                                    ↓
ui/main_window.py  主窗口：导航 + 三页 + 托盘 + 服务生命周期
   ↓ 用
ui/page_config.py / page_stats.py / page_run.py / first_run.py / rule_dialog.py
   ↓ 都用
ui/theme/          主题入口，下分四个模块       ui/widgets.py  焦点环、开关、分段、卡片、曲线、浮条
   ├ tokens.py     固化色板（Light / Dark 两套，纯数据、不依赖 Qt）
   ├ metrics.py    字号 / 间距 / 圆角 / 动效 / 阴影 / 材质，全是单值
   ├ qss.py        语义 Token → QSS，唯一拼样式表的地方
   └ __init__.py   门面：当前模式、取色、取字体、接系统设置
   ↓
core/classifier.py 判定 / 复制 / 整理 / 扫描 / 缓存 / 统计   ←── 两个前端共用
   ↓ 用
core/ocr.py        结算截图 OCR（子进程调 tesseract）
core/config.py     配置读写 / 迁移 / 路径推导      core/models.py  数据结构
core/watcher.py    目录监视 + 游戏感知
core/judge_memory.py  内存签名扫描（只读）
core/link_server.py   本机 SSE 数据服务（DGHub 插件连它）
core/capture.py       结算画面自动截图 + 画面识别
core/start_bat.py  start.bat 注入      core/autostart.py  开机自启
core/game_locator.py  自动找游戏目录    core/paths.py  数据目录定位
core/winapi.py     ctypes 封装：进程 / 窗口 / 抓帧 / 单实例 / DPI
```

**`ui/__init__.py` 和 `core/__init__.py` 都不做急切导入。** 在那里 re-export 会让
`import core.config` 这种轻量用途把 PySide6 一起拉起来，命令行和测试就跑不了了。

## 不许破坏的不变量

1. **得分换算必须走整数、必须截断。**（`core/models.py` 的 `JudgeCounts.score`）
   游戏显示的是截断值：150 张真实截图上截断值 149 次完全吻合，四舍五入会高 1 分。
   而截断又必须用整数运算。浮点会把本该整除的值算成 `1009989.999…`，再截断就少 1，
   实测有 48 组判定数会踩到，其中 129 物量全 JC 会被算成 1,009,999 而不是满分。
   → 测试 `test_the_score_truncates_instead_of_rounding`、
   `test_an_all_justice_run_is_exactly_full_marks_even_at_awkward_note_counts`
2. **判定命中只复制，整理才移动，而且只移动识别出成绩的图。**
   壁纸和识别失败的图片永远留在原地。→ `test_an_unrecognised_shot_is_never_moved`
3. **扫描按位置排除工具自己的副本**（`寸/` 及各规则目录），不是按文件名里有没有 `__`。
   用户截图里碰巧带 `__` 不能被误伤。而 `AJ/` `FC/` 兼作整理目的地，那两个目录下
   才用 `__` 标记区分。→ `test_our_own_copies_are_excluded_by_location`
4. **顶栏那一行 OCR 前要补留白，得分那一行不能补。**
   数字紧贴右边界时 tesseract 会把边缘噪点连上去（实测「MISS : 1」读成「14」，7 张真实
   截图上都是）。但同样的留白加在得分行上，psm 7 会整行读空，303 张真实截图上多出
   115 处得分错误。→ `core/ocr.py` 的 `TOP_LINE_PAD`
5. **成绩画面识别要三道检查叠加，而且只看跨版本不变的元素**：顶栏黄字黑底 + 判定明细面板
   紫色底条 + 中间没被庆祝动画盖住。曲终先出现的 CLEAR 过场和成绩画面共享**全部**顶部 chrome，
   只靠顶栏分不开，生产环境就是这么截错的。背景、顶栏底色、头像、称号都会随版本或玩家变，
   不许拿来当特征：v2.1 的 17 点指纹有 11 个点取在背景上，游戏升 2.50 换了黄色主题就一张都截不到。
   阈值是在 305 张旧版本成绩图和 2.50 实机帧上量的，数字写在 `core/capture.py` 各常量旁边。
   → `test_the_chrome_alone_is_not_enough_to_be_a_result_screen`、
   `test_a_result_screen_is_recognised_whatever_the_version_theme`
6. **内存读取只读。** `ReadProcessMemory` / `VirtualQueryEx`，不写、不注入、不 hook。
7. **后台线程的回调一律通过 Qt 信号回界面线程。** 直接从工作线程碰部件是未定义行为。
8. **字号一律按像素给**（`setPixelSize` / QSS 的 `px`）。`ui/theme/metrics.py` 的九个
   排版角色是**逻辑像素**——Qt 6 的高 DPI 缩放会按显示缩放自己放大，这正是规范说的
   「默认系统缩放下的逻辑尺寸」。写 `pt` 会让 Qt 在 Windows 上按 96 DPI 换算，13 变成 17，
   整屏字大三分之一、行还会被挤塌（v2.0 就是这样）。
   Windows 辅助功能里的「放大文本」是**另一个**设置，Qt 不管，`theme.font()` 自己乘一次
   ——规范要求系统字体缩放只应用一次，那就是唯一那一次，别在别处再乘。
   组标题必须比行标题大且 Semibold（14 / `text.primary`），规范点名禁止做成 caption 或弱灰。
9. **Mica 是两步，少一步等于没开。** `DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE)`
   之后必须再调 `DwmExtendFrameIntoClientArea` 传四边 `-1`，否则材质只铺在标题栏那一条，
   客户区毫无变化——而属性回读还是成功的（`hr=S_OK, value=2`），光看返回值查不出来。
   验收要用**屏幕**截图：`PrintWindow` 抓的是窗口自己画的那层，抓不到 DWM 铺在后面的材质。
   另外**窗口自己不画底色**。 材质是 DWM 铺在窗口**后面**的，窗口那层像素不透明就等于
   把它整个盖住，看上去毫无变化。所以 `stylesheet(mica=True)` 里 `QMainWindow` 和侧栏是
   `transparent`，其余各层半透明。两条连带的约束：`WA_TranslucentBackground` 必须在 `show()`
   **之前**设，之后设不生效；而材质一旦没铺上（`enable_mica` 返回 False），底色必须换回不透明
   那套，否则是一片全黑——`_after_shown` 里有这条回退，别删。
   ⚠️ **但那条回退只在底色画在 `QWidget#AppRoot` 上时才真的有效。**
   窗口一旦设过 `WA_TranslucentBackground`，`QMainWindow` 自己的 QSS 背景就**不画了**
   （实测：同一份样式表，非透明窗口取到 `#120F0C`，透明窗口取到 alpha=0），
   而那个属性 `show()` 之后撤不掉。所以画布底色画在中央容器上，不靠 `QMainWindow`。
   Mica 的色调**跟随窗口自己的深浅属性**，不是系统的——已实测：系统深色、应用强制浅色时
   材质也是浅的，所以不需要「两者不一致就关材质」的回退。

10. **Light 与 Dark 的 Token 键集合必须完全一致，对比度按「文字承载面集合」逐一校验。**
    少一个键就是那个模式下 KeyError，或者更糟——QSS 里静默变成空串，界面塌了却不报错。
    承载面有十一个（四个 Surface + `fill.control` + `accent.subtle` + 四个语义 `subtle`），
    只对 `canvas` 校一次会放过一批实际读不清的组合：候选色板的 `text.tertiary` 对 canvas
    有 4.45:1，对 `fill.control` 就不够。→ 测试
    `test_light_and_dark_define_exactly_the_same_tokens`、
    `test_neutral_text_is_readable_on_every_text_bearing_surface`

11. **业务代码不许散写 Hex、字号、间距、圆角、阴影和动画时长。** 全部走 `ui/theme`。
    自绘控件（Switch、Segmented、Combo 的箭头、DailyChart）尤其容易漏——v2.0 的
    `DailyChart` 就写死了 `QColor(235, 235, 245, 77)` 这种只在深色下成立的值。

## 会浪费半小时的坑

- **改 `APP_NAME` 要连带清两处以名字为键的旧记录**，否则「看着正常，实际失效」：
  开机自启的注册表值名（`core/autostart.py` 的 `migrate_legacy()`，从
  `version.LEGACY_APP_NAMES` 取旧名）、以及安装器里的旧 exe 和旧 `.lnk`
  （`installer.iss` 的 `[InstallDelete]`）。改名时往 `LEGACY_APP_NAMES` 补一条、
  往 `[InstallDelete]` 补三行。`APP_SLUG` / 数据目录 / `AppId` / 单实例互斥体名
  / start.bat 的标记全都**不要**跟着改——那几样一动，老用户的配置和统计就接不上了。

- **ctypes 的句柄参数必须写 `argtypes`/`restype`。** 默认按 `c_int` 传，64 位下
  `HANDLE`/`HWND`/`HDC` 被截成低 32 位，表现是「调用失败但错误码看着正常」。
  `core/winapi.py` 里 `_declare()` 集中写死了所有签名，加新 API 要一起加。
- **QSS 里绝不要写 `QWidget { background: ... }`。** Qt 的类型选择器连子类一起命中，
  每个 QLabel 都会被刷上底色，在卡片上显示成一条条横杠。背景只画在容器上，
  用 objectName 选择器。
- **字体要用 `QFont.setFamilies(整条字体栈)`**，不要「挑第一个装了的家族」。
  Segoe UI 没有汉字字形，选中它之后中文走系统兜底、行高对不齐。
- **`QFontDatabase.families()` 在 offscreen 平台返回空列表**，所以离屏截图里中文全是豆腐块。
  那是平台的事，不是代码的问题，别去追。
- **`_ocr()` 不负责关 PIL 图像**：第二行可能要换个 psm 再喂一次，提前关掉就 `ValueError:
  Operation on closed image`。生命周期由 `detect()` 管。
- **QSS 不支持 `outline` / `outline-offset`。** 属性被静默忽略，一个像素都不画（实测）。
  焦点环由 `ui/widgets.py` 的 `FocusRing` 画：一个跟随焦点的覆盖层，`setParent` 到获得焦点
  那个控件的父级，于是被同样的祖先裁剪，滚出可视区会跟着消失。别在 QSS 里加 `:focus` 边框
  「补救」——那会让控件获得焦点时跳一下，还和环叠在一起。测试钉着这条。
- **QSS 也不认 `line-height`，但 Qt 的富文本引擎认。** 会换行的标签（组级说明）用
  `theme.rich_text()` 包一层 `<div style="line-height:…">`，实测 200px 宽的标签从 26 高
  变成 56 高。包之前必须转义，路径里的 `&` 不转义会被当成 HTML 实体吃掉。
- **`QButtonGroup.idClicked` 只在用户点击时发，程序化 `setChecked` 不发。**
  `Segmented` 靠这个区分「用户改的」和「重建界面时置的」，自动保存不会被构建过程触发。
  但 `Switch.toggled` **会**被程序化置位触发，所以 `ConfigPage` 有个 `_loading` 闸，
  `RunPage` 有个 `_initializing` 闸。
- **别在仓库根放 `cun_config.json`。** 源码运行时 `portable_dir()` 会往上找到它，
  整个程序误判成便携部署，截图目录被推到仓库旁边去。`_fill_paths` 里有一道守卫，别拿掉。
- **`installer.iss` 必须存成 UTF-8 with BOM**，否则 ISCC 按 ANSI 读，中文全是乱码。
- **别拿 `setMinimumHeight` 给一行定高。** Qt 的 `qSmartMinSize` 里显式设过的最小高度会
  **顶掉**布局算出来的那个，于是空间一紧，这一行会被压到比内容还矮、子部件叠在一起。
  地板要加在里面的标签上，行本身用纵向 `Fixed`（`ui/widgets.py` 的 `Row`）。
- **卡片行里的副标题不能用会换行的 QLabel。** 换行标签的高度取决于宽度，窗口一窄就悄悄折成
  两三行，把整行顶高、连累同一张卡片里别的行。用 `widgets.ElidedLabel`（不换行，放不下从
  中间省略）。同理，会换行的标签放进 `QHBoxLayout` 只拿得到自己 sizeHint 那么宽，右边空着
  也不用——「统计」页顶部那行就这么折过。
- **`QComboBox::drop-down` 一styled，Windows 样式就不画箭头了**，下拉框看着和只读输入框
  一模一样。QSS 里拿边框拼三角在 Qt 里会画成一个实心方块。箭头是 `widgets.Combo` 在
  `paintEvent` 里自己描的，应用内的下拉框都要用这个类。
- **CI 的检出路径里带着仓库名**：`D:\a\chunithm-cun-sorter\chunithm-cun-sorter\`。
  所以测试里别去数 `chunithm-cun-sorter` 出现了几次——插进 start.bat 的那行自带程序路径，
  在 runner 上一行就有三个，本地零个。认注入行要按行首 `start "标记"`。
- **runner 的控制台是 cp1252，中文 `print` 当场 UnicodeEncodeError**。开发机是中文
  Windows，GBK 编得出，所以这类失败本地一次都复现不出来；想复现就
  `PYTHONIOENCODING=cp1252` 跑一遍。`packaging/build.py` 开头已经把 stdout / stderr
  reconfigure 成 UTF-8，两个 workflow 也设了 `PYTHONIOENCODING: utf-8`。
- **每个页面都要套滚动容器。** 不套的话窗口一矮，布局会去压每张卡片，压到比内容还矮就糊了。

## 数据落在哪

| | 位置 |
|---|---|
| 程序 | `%LOCALAPPDATA%\Programs\寸录\`（安装器默认，装到用户目录不弹 UAC） |
| 配置 / 缓存 / 日志 / 诊断图 | `%LOCALAPPDATA%\ChunithmCunSorter\` |
| 游戏目录 | 记在配置的 `game_root`，安装向导或首次运行向导里选 |

两个例外：环境变量 `CUN_DATA_DIR` 优先于一切（测试用）；exe 同级或任一上级目录里有
`cun_config.json` 就是**便携模式**，数据落那儿（v1.x 装在 `bin\cun\` 的老部署靠这条原地升级）。

## 命令

```powershell
.venv\Scripts\python -m pytest tests -q          # 测试
.venv\Scripts\python main.py                     # 跑界面
.venv\Scripts\python cli.py config               # 看当前配置
.venv\Scripts\python cli.py scan --rebuild       # 全量重扫
.venv\Scripts\python packaging\build.py          # 测试→exe→冒烟→安装包
```

**发版**：推送 `v*` tag → `.github/workflows/release.yml` 在 Windows runner 上打包并发布
GitHub Release（安装包 + DGHub 插件 zip）。

## 相关项目

- **DGHub 插件**在 `dghub-plugin/`，发版自动打 zip。它通过 `http://127.0.0.1:8890/events`
  读 SSE，用 `urllib.request.urlopen` 逐行读。改 `core/link_server.py` 的响应格式前先看它。
- **ChuniOptionManager** 2026-08-27 同一天也从 WinUI 重写成了 Python + PySide6、
  搬到了 `~\Workspace\code\ChuniOptionManager`。两个项目现在是同一套形态
  （PySide6 + PyInstaller + Inno Setup、装到 `%LOCALAPPDATA%`、目标目录记在配置里），
  但**各自独立**，没有共享代码。游戏目录里 `bin\option\ChuniOptionManager\` 那份
  是搬家前的旧副本。
