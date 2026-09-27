# -*- coding: utf-8 -*-
"""COUI 弹簧：(bounce, response) → 解析解。纯 Python，不依赖 Qt。

换算和设计库 spec 07 §2 一致：ζ = 1 − bounce，k = (2π / response)²，m = 1。
:class:`Motion` 驱动界面动画：可以中途换目标，从当前位置和速度接着走，不会跳。
移植自 ``lab\\pc-design-sample\\desktop\\spring.py``。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SETTLE = 0.002      # 离目标不到行程的 0.2% 就算停住


@dataclass(frozen=True)
class Spring:
    bounce: float
    response: float

    @property
    def omega(self) -> float:
        return 2 * math.pi / self.response

    @property
    def zeta(self) -> float:
        return 1.0 - self.bounce


def state(spec: Spring, x0: float, v0: float, t: float) -> tuple[float, float]:
    """从位移 x0、速度 v0 出发，t 秒后的位移和速度。位移是相对目标的（目标处为 0）。"""
    w0, z = spec.omega, spec.zeta
    if z < 1:
        wd = w0 * math.sqrt(1 - z * z)
        e = math.exp(-z * w0 * t)
        a, b = x0, (v0 + z * w0 * x0) / wd
        c, s = math.cos(wd * t), math.sin(wd * t)
        return (e * (a * c + b * s),
                e * ((b * wd - z * w0 * a) * c - (a * wd + z * w0 * b) * s))
    e = math.exp(-w0 * t)                 # 临界阻尼（bounce = 0）
    b = v0 + w0 * x0
    return e * (x0 + b * t), e * (b - w0 * (x0 + b * t))


class Motion:
    """一个会动的数值。``to()`` 随时换目标，从当前位置和速度接着走，不会跳。"""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value
        self.velocity = 0.0
        self.target = value
        self._spec: Spring | None = None
        self._x0 = self._v0 = self._t = 0.0
        self._span = 1.0

    @property
    def moving(self) -> bool:
        return self._spec is not None

    def jump(self, value: float) -> None:
        self.value = self.target = value
        self.velocity = 0.0
        self._spec = None

    def to(self, target: float, spec: Spring) -> None:
        if target == self.target and self._spec is spec:
            return
        self.target = target
        self._spec = spec
        self._x0 = self.value - target
        self._v0 = self.velocity
        self._t = 0.0
        self._span = max(abs(self._x0), 1e-6)
        if abs(self._x0) < 1e-9 and abs(self._v0) < 1e-9:
            self.jump(target)

    def step(self, dt: float) -> bool:
        """推进 dt 秒；还在动返回 True。"""
        if self._spec is None:
            return False
        self._t += dt
        x, v = state(self._spec, self._x0, self._v0, self._t)
        if abs(x) < SETTLE * self._span and abs(v) < SETTLE * self._span * self._spec.omega:
            self.jump(self.target)
            return False
        self.value = self.target + x
        self.velocity = v
        return True
