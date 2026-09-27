<div align="center">

<img src="奶奶蛙.png" width="120" alt="奶奶蛙">

# 寸录

CHUNITHM「寸」成绩自动识别 · 全截图归档 · DGHub 联动
*Near-miss detection, screenshot archiving and DGHub haptics for CHUNITHM. Python / PySide6.*

</div>

---

一个常驻托盘的 CHUNITHM 小工具，围绕「结算成绩」做三件事：

1. 识别与统计「寸」：按你自定义的判定规则（SSS寸 / AJ寸 / ATTACK+MISS…）把差一点的成绩**复制**到独立文件夹，并画出每日 寸 / AJ / FC 曲线；
2. 归档所有截图：按日期 / 评级 / 达成（AJ·FC）三个维度自动整理，维度可排序、自由嵌套；
3. DGHub 联动 + 自动截图（可选）：从游戏内存**只读**判定计数，打歌中 MISS / ATTACK 实时触发 DGHub 波形、结算「寸了」触发；结算画面由本程序自动截图入库，新截图完全不需要 OCR。

成绩数据有两条来路，可以混用：

| | 截图 + OCR（传统路径） | 游戏内存（联动路径） |
|---|---|---|
| 数据来源 | 读结算截图顶栏的 SCORE / ATTACK / MISS | 签名扫描判定计数，得分由判定数精确换算 |
| 截图来源 | 外部截图工具 / 手动 | 本程序曲终自动截取 |
| 依赖 | Tesseract OCR | 无 |
| 用途 | 历史截图重扫、不开联动时的日常 | 实时触发 + 新截图零 OCR 归档 |

> 「寸」判定**只复制原图**；「整理」开启后，识别到成绩的结算截图会被**移动**到归档文件夹（只移动、不删除，可还原）；无法识别的图片（壁纸等）留在原地不动。识别以最低 CPU 优先级运行，不影响游戏帧数。内存读取仅 `ReadProcessMemory` **只读**，不写内存、不注入、不 hook。

## 装在哪

**本程序不需要放进游戏目录。** 安装器默认装到 `%LOCALAPPDATA%\Programs\寸录\`，
不弹 UAC；游戏在哪由你在安装向导里选一次，之后记在配置里。

| | 位置 |
|---|---|
| 程序 | `%LOCALAPPDATA%\Programs\寸录\`（安装时可改） |
| 配置 / 缓存 / 日志 / 诊断图 | `%LOCALAPPDATA%\ChunithmCunSorter\` |
| 游戏目录 | 记在配置的 `game_root`，安装向导或首次运行向导里选 |

两个例外：

- **便携模式**：exe 同级或任一上级目录里放一份 `cun_config.json`，数据就落在那个目录。
  v1.x 装在 `<CHUNITHM>\bin\cun\` 的老部署靠这条原地升级，配置和缓存不会丢。
- **环境变量** `CUN_DATA_DIR` 优先于以上两者，给测试和多开用。

卸载不会删 `%LOCALAPPDATA%\ChunithmCunSorter\`，统计数据和配置留着。

v2.0.2 及更早叫「今天你寸了吗」。改名后的安装包仍是原地覆盖升级，配置、统计、开机自启都会自动接上；只有安装目录会沿用旧那个名字（安装器记着上次装在哪），想让它也改过来就先卸载再装。

## 功能特性

- 自定义判定规则（「寸」统计）：评级判定（SSS+寸 / SSS寸 / SS+寸 / SS寸 预设，下限可调，也可自定义区间）、AJ寸、ATTACK+MISS；每条可增删、可开关
- 整理归档（可选）：按日期（年/月/日）、评级、达成（AJ/FC/普通）归档；调整顺序决定文件夹嵌套，靠上的是外层；只移动识别到成绩的原图，无关图片不动
- DGHub 联动（可选）：内存判定计数（签名扫描，移植自 [Chuni2Api](https://github.com/iyxddw/Chuni2Api)）+ 配套 DGHub 外部插件（Release 附 zip，导入即用）。打歌中 MISS / ATTACK 实时触发波形，结算按你的寸规则判定、寸了触发；强度 / 时长 / 波形预设 / 通道全在 DGHub 插件配置页调
- 自动截图（可选）：判定数冻结（进入结算画面）即开始识别画面，等分数滚完、庆祝动画过去再截取结算画面存入截图目录；判定数据直接取自内存写入缓存，新截图零 OCR，外部截图工具可以下岗
- 接入 start.bat（可选）：一键向游戏 `start.bat` 注入自启动行，开游戏时本程序自动启动、开始监视并缩到托盘（原文件备份 `.cun-backup`，关掉开关精确还原；单实例不重复启动）
- 每日 寸 / AJ / FC 数量曲线 + 统计卡片（今天 / 近 7 天 / 累计 / 最高一天）
- 深色 / 浅色两套主题，可跟随系统；杏桃橙强调色，语义色板全部经过 WCAG AA 校验
- 低占用：IDLE 优先级、OCR 结果缓存、可选「关游戏后再处理」模式
- 命令行入口 `cli.py`，扫描 / 监视 / 统计不需要开界面

## 运行要求

- Windows 10 1809+ / 11，x64；游戏窗口 / 截图分辨率 1920×1080 最稳（其它分辨率按比例缩放）
- 窗口背景用 Windows 11 的 Mica 材质，色调跟随应用当前的深浅模式。Windows 10 或者系统
  「设置 → 个性化 → 颜色」里关掉了「透明效果」时自动退回不透明底色，功能不受影响
- 跟随系统辅助功能设置：「放大文本」会等比放大界面字号，「动画效果」关掉后过渡动效降为即时
- Tesseract OCR（<https://github.com/UB-Mannheim/tesseract/wiki>）：走截图 + OCR 这条路时必需。装到默认路径 `C:\Program Files\Tesseract-OCR\` 即可，或把含 `eng.traineddata` 的 `tessdata` 放数据目录下 / 在配置里改 `tesseract_cmd`。只用联动 + 自动截图的话，新成绩不需要它，历史截图重扫仍需要
- DGHub 主程序（<http://www.dghub.top/>）：只有开 DGHub 联动才要。DG-Lab 郊狼设备的联动主程序，从其「插件中心 → 外部插件」导入本项目的联动插件
- 安装包是自包含的，**不需要装 Python**。只有从源码跑才要 Python 3.11+

## 快速开始

### 基础使用（识别 + 归档）

1. 下载最新 `chunithm-cun-sorter-2.1.0-setup.exe`，双击。
2. 安装向导里会问 **CHUNITHM 装在哪**：选中游戏根目录（里面有 `bin` 文件夹的那一层）。
   它会先猜一个常见位置，不对就点「浏览」。现在不确定可以留空，第一次打开程序时还会再问。
3. 装完打开程序。「配置」页确认截图目录、添加判定规则、按需开启整理，保存；
   点「应用并重新扫描」可整理历史截图。
4. 想随游戏自动启动：「运行」页打开「接入 start.bat」，选中游戏的 `start.bat`，以后开游戏就全自动。

> 截图目录默认取 `<游戏目录>\bin\screenshots`；不在那儿就在「配置 → 目录」里浏览指定。

### DGHub 联动 + 自动截图（可选）

> 需要先安装 **DGHub 主程序**（<http://www.dghub.top/>）并连好 DG-Lab 设备；波形预设也在 DGHub 里管理。

1. 下载 Release 里的 `cun_dghub_plugin_v2.0.zip`，在 DGHub「插件中心 → 外部插件 → 导入 zip 包」安装「寸录 · 联动」并启用；触发开关 / 强度 / 波形预设 / 通道都在其插件配置页调，「启动检查」可看连接状态。
2. cun 的「配置 → DGHub 联动」打开开关（默认端口 8890），「配置 → 自动截图」按需打开，保存立即生效。
3. 开打。打歌中吃 MISS 即触发；每首歌结算自动截图、按寸规则判定并归档，全程零 OCR。

### 从 v1.x 升级

v2.0 是 Python 重写版，配置文件格式没变，`cun_config.json` 和 `cun_ocr_cache.json` 直接沿用。

1. 先退出正在跑的 v1.x（托盘右键 → 退出）。
2. 装 v2.0。想把数据一起带过来，就把老的 `<CHUNITHM>\bin\cun\cun_config.json` 和
   `cun_ocr_cache.json` 复制到 `%LOCALAPPDATA%\ChunithmCunSorter\`。
   不复制也行，重新扫一遍即可，只是要重跑 OCR。
3. **接入过 start.bat 的话，去「运行」页把开关关掉再打开一次。** 里面那行还指着老的 exe 路径，
   重新接入会把它换成新的（标记相同，不会留下两行）。
4. 确认无误后可以删掉 `<CHUNITHM>\bin\cun\`。

> v1.x 的 zip 解压到 `<CHUNITHM>\bin\cun\` 的部署方式仍然能用（便携模式），
> 但新版不再这么分发。

## 界面说明（三页）

- **配置**
  - 目录：游戏目录 / 截图目录（要扫描的原图）/ 输出目录（分类结果根目录）。
  - 判定规则（寸）：点「添加判定规则」→ 选评级判定 / AJ寸 / ATTACK+MISS；命中的图**复制**到 `寸/` 下并计入统计。
  - 整理：日期 / 评级 / 达成三行各自开关，用行尾的 ↑ ↓ 调整顺序决定嵌套层级（到头的方向会停用）；开启任一项后扫描会**移动**原图归档。
  - DGHub 联动：总开关 + 本机数据端口（默认 8890）；触发参数在 DGHub 插件配置页调。
  - 自动截图（结算画面）：开关 + 「等 N 秒再保存」（等结算分数滚完，默认 2.5）；本开关或联动任一开启即运行内存读取。
  - 外观：跟随系统 / 浅色 / 深色。
  - `保存配置` / `应用并重新扫描` / `打开输出文件夹`。
  - **保存边界**：开关和选择器（判定规则开关、整理开关与年月日、联动与自动截图开关、外观）改完**立即生效并写盘**；目录、端口、等待秒数、得分区间要点「保存配置」才提交。
- **统计**：每日 寸 / AJ / FC 曲线（三条线各有自己的颜色、线型和标记）+ 今天 / 近 7 天 / 累计 / 最高一天。
- **运行**：`realtime` / `on_close` 模式切换、启停监视、游戏状态、联动状态（数据服务 / 判定读取）、开机自启、接入 start.bat；「最近命中」实时滚动寸命中、结算与截图记录。
  监视运行时关窗口等于**最小化到托盘**继续后台监视（右键托盘菜单显示主界面 / 退出，双击图标直接显示）。

## 判定与整理

### 判定规则（「寸」统计，复制原图）

| 类型 | 判定 | 说明 |
|---|---|---|
| 评级判定 | `下限 ≤ 得分 ≤ 上限` | 预设档位 `SSS+寸 / SSS寸 / SS+寸 / SS寸`（下限可改、上限固定），或自定义区间 |
| AJ寸 | `ATTACK=0 且 0<MISS≤x` | 差一点 AJ |
| ATTACK+MISS | `ATTACK≤a 且 MISS≤m 且 A+M>0，评级≥门槛` | |

> 评价分数段：SSS+ `≥1,009,000`、SSS `≥1,007,500`、SS+ `≥1,005,000`、SS `≥1,000,000` …（满分 1,010,000）。
> 一张图可同时命中多条规则，分别复制到各自子文件夹，文件名标注类别与成绩，如 `2026-05-29_08-18-04__SSS寸_SSS_A2M0_1008792.png`。

### 整理维度（移动原图）

| 维度 | 生成文件夹 |
|---|---|
| 日期 | `2026` / `2026-05` / `2026-05-24`（按年 / 月 / 日） |
| 评级 | `SSS+` / `SSS` / `SS+` / … |
| 达成 | `AJ`（A0 M0）/ `FC`（无 MISS）/ `普通` |

> 顺序决定嵌套：「日期」在上、「评级」在下会得到 `2026-05/SSS+/图.png`。AJ / FC 属于整理维度，不计入「寸」。
> 某维度取不到值会跳过该层，不建「未知」文件夹；关掉整理后已归档的截图仍会被扫描统计。

## 配置 `cun_config.json`

放在 `%LOCALAPPDATA%\ChunithmCunSorter\`（便携模式下在 exe 旁边）。

| 键 | 说明 |
|---|---|
| `game_root` | CHUNITHM 游戏根目录（安装向导 / 首次运行向导写入）；截图目录和 start.bat 留空时从它推导 |
| `screenshots_dir` | 监视的截图目录（留空自动取 `<game_root>\bin\screenshots`） |
| `output_root` | 输出根目录（留空同 `screenshots_dir`） |
| `tesseract_cmd` | Tesseract 路径（OCR 路径用；留空 / 找不到回退 PATH） |
| `process_mode` | `realtime`（实时·低优先级）或 `on_close`（关游戏后处理） |
| `game_process` | 游戏进程名（默认 `chusanApp.exe`） |
| `rename_with_stats` | 复制时在文件名追加成绩与类别 |
| `rank_thresholds` | 各评级分数线 |
| `categories[]` | 自定义判定规则（界面增删） |
| `organize.steps[]` | 整理维度与顺序（`date` / `rank` / `achievement`，列表序等于嵌套序） |
| `boxes` / `dark_threshold` / `bright_threshold` | OCR 区域与阈值（基于 1920×1080） |
| `start_bat` | 已接入的游戏 `start.bat` 路径（「运行」页管理，是否接入以 bat 内容为准） |
| `dghub.enabled` / `dghub.port` | DGHub 联动开关 / 本机数据端口（默认 `8890`；触发参数在 DGHub 插件配置页） |
| `capture.enabled` | 自动截图开关（默认 `false`） |
| `capture.delay_s` / `capture.timeout_s` | 识别到结算画面后等几秒再存（默认 2.5）/ 单次尝试最长等待（默认 30） |
| `appearance` | 界面外观：`system`（默认，跟随系统）/ `light` / `dark` |

## 工作原理

**OCR 路径**：读结算画面顶部状态栏的清晰字体，隔离白字深色描边后交给 Tesseract 识别
`SCORE / ATTACK / MISS`，由得分换算评级（顶栏某项为 0 时游戏会整个隐藏它，据此判 0）。
顶栏那一行在送进 OCR 之前会补一圈留白：数字紧贴右边界时 tesseract 会把边缘噪点连上去，
实测把「MISS : 1」读成「14」。得分那一行不能补，补了 psm 7 会整行读空。
结果缓存于 `cun_ocr_cache.json`（按文件名 + 大小校验），改规则重判**瞬间**完成、无需重新识别。

**内存路径**：按 [Chuni2Api](https://github.com/iyxddw/Chuni2Api) 的方式在游戏进程里签名扫描
`NUM_jctirical` 等字段名定位四个判定计数地址（**只读**，20Hz 轮询）。CHUNITHM 无连击加成，
得分可由判定数精确换算：`得分 = 1,000,000/物量 × (1.01×JC + 1.0×JUSTICE + 0.5×ATTACK)`，
**向下取整**（游戏显示的就是截断值，150 张真实截图上验过 149 次完全吻合；
v1.x 用四舍五入，所以联动那条路的分数会系统性高 1 分，在评级边界上会改判）。
评级、AJ/FC、寸判定全部由此推出，不需要再逆向其它字段。

**DGHub 联动**采用与 Chuni2Api 一致的分工：cun 在 `127.0.0.1:8890` 提供 SSE 数据流
（`/events`：判定计数 + 带寸判定结果的 `settle` 事件；`/data`：快照）；触发在 DGHub 外部插件
（`dghub-plugin/`）里完成，由 DGHub 启动并传 token，按插件配置页的参数发 `trigger`。

**自动截图**的触发是判定数冻结：结算画面显示期间计数块仍存活、冻结在最终值（内存要到玩家
离开结算画面才释放，等释放就晚了）。计数连续 2.5 秒不变即开始每 0.5 秒抓帧（无边框窗口直接
屏幕拷贝），用三道叠加的检查确认是成绩画面，每一道都只看跨游戏版本不变的界面元素：

1. 顶栏「JUSTICE CRITICAL」那段黄字黑底：打歌、CLEAR 过场、成绩画面都有，TOTAL RESULT、选曲、地图没有；
2. 判定明细面板那几行紫色底条。曲终先出现的 CLEAR 过场与成绩画面共享**全部**顶部 chrome，只有这块面板能分开两者；
3. 画面中间没有被庆祝动画的深色横幅盖住（刷新纪录、Rating 上涨时会先铺一块横幅再闪一下，那一帧存下来是坏图）。

背景、顶栏底色、头像、称号、曲绘都会随游戏版本或玩家设置变，一律不当特征：v2.1 及之前的像素指纹
有 11 个点取在背景和顶栏底色上，游戏升到 2.50、主题换成黄色之后自动截图一张都截不到。
三道都通过后等 `delay_s` 让分数滚完、复验一次才保存；判定数据直接写入缓存，归档分类零 OCR。

## 目录结构

```
.
├─ main.py             界面入口（--watch 随游戏启动）
├─ cli.py              命令行入口（scan / watch / stats / config / game-root）
├─ core/               判定 / OCR / 监视 / 内存 / 联动 / 截图 / 配置 / Win32
├─ ui/                 PySide6 界面：主窗口、三页、部件、两个对话框
│  └─ theme/          主题入口：tokens（色板）/ metrics（字号间距）/ qss（样式表）
├─ packaging/          build.py（一条命令出安装包）/ cun.spec / installer.iss
├─ tests/              pytest，不需要装 Tesseract 也能跑
├─ dghub-plugin/       DGHub 外部插件（manifest.json + main.py；发版自动打 zip）
├─ assets/             icon.ico / 奶奶蛙.png
└─ .github/workflows/  build.yml（测试 + 打包 CI）/ release.yml（tag 触发发版）
```

## 开发

需要 Python 3.11+。打安装包还要 [Inno Setup 6](https://jrsoftware.org/isdl.php)
（`winget install --id JRSoftware.InnoSetup`）。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

.venv\Scripts\python -m pytest tests -q     # 测试
.venv\Scripts\python main.py                # 跑界面
.venv\Scripts\python cli.py config          # 看当前配置
.venv\Scripts\python packaging\build.py     # 测试 → exe → 启动冒烟 → 安装包
```

命令行子命令：

```bash
python cli.py game-root "C:\Chuni\CHUNITHM"   # 设置游戏目录（不给路径就自动探测）
python cli.py scan --rebuild                  # 全量重扫，先清掉旧副本
python cli.py watch                           # 无界面常驻监视
python cli.py stats                           # 打印每日统计
```

> **发版**：推送 `v*` tag（如 `git tag v2.0 && git push origin v2.0`），
> `release.yml` 会在 Windows runner 上自动打包并发布 GitHub Release。

## FAQ

- **识别不到 / 全是空？** 确认是 1920×1080 截图、装了 Tesseract（能找到 `eng.traineddata`）、截图目录正确。`python cli.py config` 能一眼看全。
- **程序必须放在游戏目录里吗？** v2.0 起不用了。装到哪都行，游戏目录在安装向导或「配置 → 目录」里指定。
- **DGHub 联动连不上？** ① cun「运行」页联动状态是否「监听 …8890」；② DGHub 插件「启动检查」里 cun 数据服务是否 OK（核对端点端口一致）；③ 插件已启用。
- **自动截图偶尔提示「未捕获到结算画面：没等到判定明细面板」？** 曲中长空档的良性误触发，画面检查已正确拦截，不影响任何东西。每首歌的结算画面照常会截到。
- **联动会改游戏内存吗？** 不会。只读判定计数，不写入、不注入、不 hook。
- **「接入 start.bat」改了什么？** 在 `@echo off` 后插入一行 `start "chunithm-cun-sorter" "<本程序路径>" --watch`（保留原内容与编码，换行统一 CRLF，cmd 对纯 LF 的 bat 会吞行首字符），并留 `.cun-backup` 备份；关掉开关精确移除。已在运行则不重复启动。
- **开了整理后原图不见了？** 只是**移动**到了归档文件夹（如 `日期/评级/达成`），没有删除，可手动移回。
- **会不会掉帧？** 识别在结算后、IDLE 优先级；截图抓帧只在计数冻结（结算 / 长空档）期间发生。
- **想同时开两个实例？** 设 `CUN_ALLOW_MULTIPLE=1` 绕过单实例检查。正常使用不需要。
- **界面怎么切浅色？** 「配置 → 外观」选跟随系统 / 浅色 / 深色，立即生效。跟随系统时改系统主题会实时跟着变。
- **改了开关没点保存，退出后会丢吗？** 不会。开关和选择器是改完就写盘的；只有目录、端口、秒数和得分区间需要点「保存配置」。

## 更新记录

完整记录见 [更新记录.md](更新记录.md)。

### v2.1.0（2026-08-31）

- 按新版全局设计规范（`2026.08.31-a11y-baseline`）重做界面：语义 Token 主题、深浅两套独立映射、
  杏桃橙品牌方向。
- 新增「配置 → 外观」，可跟随系统或强制深浅；标题栏和 Mica 材质跟着走。
- 开关和选择器改完立即生效并写盘，数值与目录仍走「保存配置」，界面上写明了边界。
- 补齐键盘焦点环、Loading / Empty 状态、停用整行降级；删除判定规则改为带「撤销」。
- 统计曲线换成专用分类色板，三条线各带线型与标记，颜色不再是唯一区分手段。

### v2.0.3（2026-08-28）

- **改名为「寸录」**，原名「今天你寸了吗」。窗口标题、exe、快捷方式、DGHub 插件名跟着变；配置目录、仓库名、安装包文件名都没动。

### v2.0（2026-08-27）

- **整体重写为 Python + PySide6**，WinUI 3 / .NET 8 那套（`CunSorter/`）已删除。功能对齐 v1.3，配置与缓存格式不变。
- **不再要求装进游戏目录**：安装到 `%LOCALAPPDATA%\Programs\`，数据落 `%LOCALAPPDATA%\ChunithmCunSorter\`，游戏目录在**安装向导里选**（会先自动猜一个），程序里也能改。老的 `bin\cun\` 部署走便携模式继续可用。
- **发行形式改为安装包**（PyInstaller + Inno Setup），不再是解压到指定位置的 zip。
- **修正得分换算**：改成向下取整并用整数运算。游戏显示的是截断值，v1.x 的四舍五入会让联动那条路的分数系统性高 1 分，在评级边界上会改判。
- **修正 OCR 的 MISS 误读**：顶栏送进 OCR 前补一圈留白，数字紧贴右边界时不再被读成两位数（303 张真实截图上，ATTACK / MISS 与 v1.3 生产数据零差异）。
- **修正带 BOM 的 start.bat**：自启动行不再被插到 BOM 前面（这个缺陷 v1.x 也有）。
- 新增命令行入口 `cli.py`，新增首次运行向导，新增 `game_root` 配置项。
- 界面按 Apple HIG 深色模式重做：inset grouped 版式、拨动开关、活力橙强调色。

### v1.3（2026-07-04）

- 新增 DGHub 联动、自动截图、接入 start.bat；详见 [更新记录.md](更新记录.md)。

## 致谢

- [Chuni2Api](https://github.com/iyxddw/Chuni2Api)（内存签名扫描方案）· [DGHub](http://www.dghub.top/)（外部插件协议）
- [PySide6 / Qt](https://doc.qt.io/qtforpython/) · [Pillow](https://python-pillow.org/) · [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) · [PyInstaller](https://pyinstaller.org/) · [Inno Setup](https://jrsoftware.org/isinfo.php)

## 许可

[MIT](LICENSE)。本项目为非官方同人工具，与 SEGA 无关；CHUNITHM 及相关素材归 SEGA 所有。
