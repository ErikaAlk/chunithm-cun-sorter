# -*- coding: utf-8 -*-
"""版本号与应用标识的唯一真源。

打包脚本、安装器文件名、控制面板里的卸载项版本全部从这里读，别在别处再写一份。
"""

__version__ = "2.2.0"

APP_NAME = "寸录"
APP_SLUG = "chunithm-cun-sorter"
APP_USER_MODEL_ID = "CunLu.App"

#: 单实例互斥体名，与 v1.x 保持一致，避免新旧版同时跑两个监视器
SINGLE_INSTANCE_MUTEX = "chunithm-cun-sorter-single-instance"

#: 用过的旧名。改名之后，开机自启的注册表值名、快捷方式名这些以名字为键的东西
#: 会留下一份对不上的旧记录，靠这张表找出来清掉。
LEGACY_APP_NAMES = ("今天你寸了吗",)
