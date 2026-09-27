# -*- coding: utf-8 -*-
"""界面里用到的几个图标，用 QPainterPath 现画。

线性单色、圆头，线宽约 1.4（DESIGN.md 第 13 章）；颜色在画的时候传进来，所以跟着主题走，
不用为深浅色各备一套图片。导航图标有线性和实心两版：选中换实心。

所有图形都在一个 20×20 的设计格里描，画的时候按目标矩形缩放。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

_GRID = 20.0
STROKE = 1.4


def _line(*points: tuple[float, float]) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(*points[0])
    for p in points[1:]:
        path.lineTo(*p)
    return path


def _circle(x: float, y: float, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(x, y), r, r)
    return path


def _rounded(x: float, y: float, w: float, h: float, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)
    return path


def _stroke(p: QPainter, color: QColor, *paths: QPainterPath) -> None:
    p.setPen(QPen(color, STROKE, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for path in paths:
        p.drawPath(path)


def _fill(p: QPainter, color: QColor, *paths: QPainterPath) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    for path in paths:
        p.drawPath(path)


# ----------------------------- 导航 -----------------------------------------
def _settings(p: QPainter, c: QColor, solid: bool) -> None:
    """两根滑杆。"""
    if solid:
        _stroke(p, c, _line((3, 6.5), (17, 6.5)), _line((3, 13.5), (17, 13.5)))
        _fill(p, c, _circle(7, 6.5, 2.8), _circle(13, 13.5, 2.8))
    else:
        _stroke(p, c, _line((3, 6.5), (4.7, 6.5)), _line((9.3, 6.5), (17, 6.5)),
                _line((3, 13.5), (10.7, 13.5)), _line((15.3, 13.5), (17, 13.5)),
                _circle(7, 6.5, 2.3), _circle(13, 13.5, 2.3))


def _stats(p: QPainter, c: QColor, solid: bool) -> None:
    """三根柱子。"""
    bars = (_rounded(3, 10, 3.6, 7, 1.2), _rounded(8.2, 4, 3.6, 13, 1.2),
            _rounded(13.4, 7.5, 3.6, 9.5, 1.2))
    if solid:
        _fill(p, c, *bars)
    else:
        _stroke(p, c, *bars)


def _run(p: QPainter, c: QColor, solid: bool) -> None:
    """圆里一个播放三角。"""
    triangle = _line((8.2, 6.6), (13.6, 10), (8.2, 13.4))
    triangle.closeSubpath()
    if solid:
        _fill(p, c, _circle(10, 10, 7.6).subtracted(triangle))
    else:
        _stroke(p, c, _circle(10, 10, 7), triangle)


# ----------------------------- 操作 -----------------------------------------
def _chevron_down(p: QPainter, c: QColor, _solid: bool) -> None:
    _stroke(p, c, _line((5.6, 8.1), (10, 12.5), (14.4, 8.1)))


def _chevron_up(p: QPainter, c: QColor, _solid: bool) -> None:
    _stroke(p, c, _line((5.6, 11.9), (10, 7.5), (14.4, 11.9)))


def _check(p: QPainter, c: QColor, _solid: bool) -> None:
    _stroke(p, c, _line((4.4, 10.4), (8.2, 14.1), (15.6, 6)))


def _more(p: QPainter, c: QColor, _solid: bool) -> None:
    _fill(p, c, _circle(4.5, 10, 1.4), _circle(10, 10, 1.4), _circle(15.5, 10, 1.4))


def _refresh(p: QPainter, c: QColor, _solid: bool) -> None:
    arc = QPainterPath()
    arc.arcMoveTo(QRectF(3.5, 3.5, 13, 13), 60)
    arc.arcTo(QRectF(3.5, 3.5, 13, 13), 60, 300)
    _stroke(p, c, arc, _line((13.4, 3.2), (13.6, 5.6), (11.2, 6.2)))


def _folder(p: QPainter, c: QColor, _solid: bool) -> None:
    body = _line((2.8, 6), (2.8, 15), (17.2, 15), (17.2, 7.2), (9.6, 7.2), (8, 5), (3.8, 5))
    body.closeSubpath()
    _stroke(p, c, body)


def _add(p: QPainter, c: QColor, _solid: bool) -> None:
    _stroke(p, c, _line((10, 4.5), (10, 15.5)), _line((4.5, 10), (15.5, 10)))


_ICONS: dict[str, Callable[[QPainter, QColor, bool], None]] = {
    "settings": _settings, "stats": _stats, "run": _run,
    "chevron-down": _chevron_down, "chevron-up": _chevron_up, "check": _check,
    "more": _more, "refresh": _refresh, "folder": _folder, "add": _add,
}


def paint(p: QPainter, name: str, rect: QRectF, color: QColor, solid: bool = False) -> None:
    """在 ``rect`` 里画一个图标。``solid`` 只对导航图标有意义（选中态的实心版）。"""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(rect.topLeft())
    k = min(rect.width(), rect.height()) / _GRID
    p.scale(k, k)
    _ICONS[name](p, color, solid)
    p.restore()


def names() -> tuple[str, ...]:
    return tuple(_ICONS)
