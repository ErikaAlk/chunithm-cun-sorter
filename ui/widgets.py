# -*- coding: utf-8 -*-
"""界面部件：动效、焦点环、胶囊按钮、输入框、下拉框、开关、卡片与设置行、Toast、面板、曲线。

胶囊按钮、输入框、下拉框、开关、卡片都**自己画**：QSS 的 ``border-radius`` 不做抗锯齿，
32 高的胶囊画出来边缘全是台阶。自绘的只是外观；交互、键盘和朗读仍是原生
QPushButton / QLineEdit / QComboBox / QAbstractButton 的。

键盘焦点环统一由 :class:`FocusTracker` 画在控件外面（DESIGN.md 16.4：2px 实线、外扩 2px、
只在键盘操作时出现），各控件不各画一套。

颜色、字号、间距、圆角、动效**一律从 theme 取**，这里不写死视觉常量。
写法参照 ``lab\\pc-design-sample\\desktop\\widgets.py``（DESIGN.md 第 16 章的样板）。
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from PySide6.QtCore import (QEasingCurve, QElapsedTimer, QEvent, QObject, QPoint, QPointF,
                            QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox, QApplication, QComboBox,
                               QDialog, QDoubleSpinBox, QFrame, QGraphicsDropShadowEffect,
                               QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
                               QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from core import winapi

from . import icons, theme
from .theme import metrics as m
from .theme import spring as _spring

SPRINGS = {name: _spring.Spring(b, r) for name, (b, r) in m.SPRINGS.items()}


# ----------------------------- 动效 -----------------------------------------
class _Ticker(QObject):
    """所有弹簧共用一个计时器，没有在动的就停掉，不空转。"""

    def __init__(self) -> None:
        super().__init__(QApplication.instance())
        self.active: set[Anim] = set()
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(8)                  # 高刷屏上也跟得上
        self.timer.timeout.connect(self._tick)

    def add(self, anim: "Anim") -> None:
        self.active.add(anim)
        if not self.timer.isActive():
            self.clock.start()
            self.timer.start()

    def _tick(self) -> None:
        dt = min(self.clock.restart() / 1000.0, 0.05)
        for anim in list(self.active):
            moving = anim.motion.step(dt)
            if not anim.changed() or not moving:
                self.active.discard(anim)
                if not moving:
                    anim.finished()
        if not self.active:
            self.timer.stop()


_TICKER: _Ticker | None = None


def _ticker() -> _Ticker:
    global _TICKER
    if _TICKER is None:
        _TICKER = _Ticker()
    return _TICKER


def _bezier(x1: float, y1: float, x2: float, y2: float) -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2), QPointF(1, 1))
    return curve


class Anim:
    """跟着 COUI 弹簧走的一个数值（DESIGN.md 第 12 章）。

    ``to()`` 随时换目标，从当前位置和速度接着走，不会跳；系统关了动画就直接到位。
    """

    def __init__(self, owner: QWidget, value: float = 0.0,
                 on_change: Callable[[], None] | None = None,
                 on_done: Callable[[], None] | None = None) -> None:
        self.motion = _spring.Motion(value)
        self.on_change = on_change or owner.update
        self.on_done = on_done

    @property
    def value(self) -> float:
        return self.motion.value

    @value.setter
    def value(self, v: float) -> None:
        self.motion.jump(v)

    @property
    def target(self) -> float:
        return self.motion.target

    def running(self) -> bool:
        return self in _ticker().active

    def to(self, target: float, spring: str = "state", instant: bool = False) -> None:
        if instant or theme.reduce_motion():
            _ticker().active.discard(self)
            self.motion.jump(target)
            self.changed()
            self.finished()
            return
        self.motion.to(target, SPRINGS[spring])
        if self.motion.moving:
            _ticker().add(self)
        else:
            self.changed()

    def changed(self) -> bool:
        try:
            self.on_change()
            return True
        except RuntimeError:                       # 控件已经销毁
            return False

    def finished(self) -> None:
        if self.on_done is not None:
            try:
                self.on_done()
            except RuntimeError:
                pass


def fade_in(widget: QWidget) -> None:
    """换页时新页淡入（16.4：不做整页滑动）。"""
    if theme.reduce_motion():
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = Anim(widget, 0.0,
                on_change=lambda: effect.setOpacity(max(0.0, min(1.0, anim.value))),
                on_done=lambda: widget.setGraphicsEffect(None))
    widget._fade_anim = anim                        # 挂在控件上，别被回收
    anim.to(1.0, "page")


class _States:
    """悬停与按压两层蒙层的进度。混入 Qt 控件类的前面用。"""

    def _init_states(self) -> None:
        self._hover = Anim(self)
        self._press = Anim(self)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def enterEvent(self, e) -> None:                # noqa: N802 - Qt 的命名
        if self.isEnabled():
            self._hover.to(1, "state")
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:                # noqa: N802
        self._hover.to(0, "state")
        self._press.to(0, "release")
        super().leaveEvent(e)

    # 按下用 candyPress（不回弹），松手用 candyRelease（带回弹）：按钮会轻轻弹回原大小
    def mousePressEvent(self, e) -> None:           # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._press.to(1, "press")
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:         # noqa: N802
        self._press.to(0, "release")
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e) -> None:             # noqa: N802
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat() and self.isEnabled():
            self._press.to(1, "press")
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e) -> None:           # noqa: N802
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._press.to(0, "release")
        super().keyReleaseEvent(e)

    def changeEvent(self, e) -> None:               # noqa: N802
        if e.type() == QEvent.Type.EnabledChange and not self.isEnabled():
            self._hover.to(0, instant=True)         # 禁用时按压反馈立即清零（11.1）
            self._press.to(0, instant=True)
        super().changeEvent(e)


def _capsule(p: QPainter, r: QRectF, color: QColor, radius: float | None = None) -> None:
    rad = r.height() / 2 if radius is None else radius
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(r, rad, rad)


def _shadow(widget: QWidget, spec: m.Shadow) -> None:
    color, blur, y = theme.shadow(spec)
    fx = widget.graphicsEffect()
    if not isinstance(fx, QGraphicsDropShadowEffect):
        fx = QGraphicsDropShadowEffect(widget)
        widget.setGraphicsEffect(fx)
    fx.setColor(color)
    fx.setBlurRadius(blur)
    fx.setOffset(0, y)


# ----------------------------- 焦点环 ---------------------------------------
class _Ring(QWidget):
    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.radius = 0.0
        self.hide()

    def paintEvent(self, _e) -> None:               # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = m.FOCUS_RING_WIDTH
        r = QRectF(self.rect()).adjusted(w / 2, w / 2, -w / 2, -w / 2)
        p.setPen(QPen(theme.color("focusRing"), w))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, self.radius, self.radius)


class FocusTracker(QObject):
    """全局只有一个。记住最近一次输入是键盘还是鼠标，决定画不画焦点环。

    QSS 不支持 ``outline``（实测被静默忽略），所以环是一层覆盖在窗口上的部件。
    输入框点进去也显示（和浏览器 ``:focus-visible`` 一样）；导航列表自己画当前项，
    控件上设 ``ownFocusRing`` 就跳过。
    """

    KEYS = {Qt.Key.Key_Tab, Qt.Key.Key_Backtab, Qt.Key.Key_Up, Qt.Key.Key_Down,
            Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home, Qt.Key.Key_End,
            Qt.Key.Key_PageUp, Qt.Key.Key_PageDown}

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.keyboard = False
        self.target: QWidget | None = None
        self._rings: dict[int, _Ring] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(40)            # 跟住滚动中的控件
        self._timer.timeout.connect(self.sync)
        app.installEventFilter(self)
        app.focusChanged.connect(self._focus_changed)

    def eventFilter(self, _obj, e) -> bool:         # noqa: N802
        t = e.type()
        if t == QEvent.Type.KeyPress and e.key() in self.KEYS:
            if not self.keyboard:
                self.keyboard = True
                QTimer.singleShot(0, self.sync)
        elif t == QEvent.Type.MouseButtonPress and self.keyboard:
            self.keyboard = False
            QTimer.singleShot(0, self.sync)
        return False

    def _focus_changed(self, _old, new) -> None:
        self.target = new
        self.sync()

    def sync(self) -> None:
        for key, ring in list(self._rings.items()):
            try:
                ring.hide()
            except RuntimeError:                    # 面板关掉之后，环跟着它一起销毁了
                del self._rings[key]
        w = self.target
        try:
            if (w is None or not w.isVisible() or w.property("ownFocusRing")
                    or not (self.keyboard or w.property("alwaysRing"))):
                self._timer.stop()
                return
            win = w.window()
        except RuntimeError:
            self._timer.stop()
            return
        ring = self._rings.get(id(win))
        try:
            stale = ring is None or ring.parent() is not win
        except RuntimeError:                        # 同一个 id 被新窗口复用，旧环已销毁
            stale = True
        if stale:
            ring = self._rings[id(win)] = _Ring(win)
        pad = m.FOCUS_RING_WIDTH + m.FOCUS_RING_OFFSET
        top_left = w.mapTo(win, QPoint(0, 0))
        ring.setGeometry(top_left.x() - pad, top_left.y() - pad,
                         w.width() + 2 * pad, w.height() + 2 * pad)
        base = w.property("focusRadius")
        base = w.height() / 2 if base is None else float(base)
        ring.radius = base + pad - m.FOCUS_RING_WIDTH / 2
        ring.raise_()
        ring.show()
        ring.update()
        if not self._timer.isActive():
            self._timer.start()


_FOCUS: FocusTracker | None = None


def install_focus_tracker(app: QApplication) -> FocusTracker:
    global _FOCUS
    if _FOCUS is None:
        _FOCUS = FocusTracker(app)
    return _FOCUS


def keyboard_focus() -> bool:
    return bool(_FOCUS and _FOCUS.keyboard)


# ----------------------------- 文字 -----------------------------------------
def label(text: str = "", role: str = "body", *, wrap: bool = False) -> QLabel:
    """一个按角色上字号和颜色的标签（样式在 QSS 里按 ``role`` 属性选）。"""
    lb = QLabel(text)
    if role != "body":
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    lb.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return lb


class ElidedLabel(QLabel):
    """单行文字：装不下就从中间省略（路径头上的盘符和尾巴上的文件名都留着）。

    设置行的摘要**不能换行**：会换行的标签高度取决于宽度，窗口一窄就悄悄长成两三行，
    把整行顶高。省略之后完整文本挂在 Tooltip 上。
    """

    def __init__(self, text: str = "", role: str = "secondary",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", role)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._relayout()

    def setText(self, text: str) -> None:           # noqa: N802 - Qt 的命名
        self._full = text
        self._relayout()

    def text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:           # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    def changeEvent(self, event) -> None:           # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._relayout()

    def _relayout(self) -> None:
        shown = self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideMiddle, max(self.width(), 32))
        super().setText(shown)
        self.setToolTip(self._full if shown != self._full else "")


# ----------------------------- 按钮 -----------------------------------------
class Button(_States, QPushButton):
    """胶囊按钮（16.1：高 32，小按钮 28，左右内边距 16）。

    ``kind``：``primary`` 主色胶囊（每屏最多一个）；``secondary`` 灰胶囊；
    ``danger`` 灰胶囊 + 红字（删除类）；``quiet`` 没有底，主色字，只在悬停时出底（面板顶栏）。
    """

    def __init__(self, text: str, kind: str = "secondary", small: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.kind = kind
        self.small = small
        self._init_states()
        self.setAutoDefault(False)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.restyle()

    def restyle(self) -> None:
        self.setFont(theme.font(theme.BUTTON))
        self.setFixedHeight(theme.scaled(m.BUTTON_SMALL if self.small else m.BUTTON_HEIGHT))
        self.updateGeometry()
        self.update()

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.update()

    def sizeHint(self) -> QSize:                    # noqa: N802
        fm = QFontMetrics(self.font())
        w = fm.horizontalAdvance(self.text()) + 2 * m.PAD_CONTROL_X
        if self.kind != "quiet":
            w = max(w, m.BUTTON_MIN_WIDTH)
        return QSize(w, self.height() or m.BUTTON_HEIGHT)

    def minimumSizeHint(self) -> QSize:             # noqa: N802
        return self.sizeHint()

    def _colors(self) -> tuple[QColor, QColor]:
        on = self.isEnabled()
        if self.kind == "primary":
            return (theme.color("primary" if on else "primaryDisabled"),
                    theme.color("onPrimary" if on else "button.onPrimaryDisabled"))
        if self.kind == "quiet":
            return QColor(0, 0, 0, 0), theme.color("primaryText" if on else "label3")
        bg = theme.color("button.secondaryBg" if on else "button.secondaryDisabledBg")
        fg = "error" if self.kind == "danger" else "label1"
        return bg, theme.color(fg if on else "label3")

    def paintEvent(self, _e) -> None:               # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        press = self._press.value if self.isEnabled() else 0.0
        if abs(press) > 1e-4:
            # 胶囊按下缩小（11.1 / 16.4），桌面上不做跟手形变
            s = 1 - (1 - m.PRESS_SCALE) * press
            p.translate(r.center())
            p.scale(s, s)
            p.translate(-r.center())
        bg, fg = self._colors()
        _capsule(p, r, theme.state_color(bg, hover=self._hover.value, pressed=max(press, 0.0)))
        p.setPen(fg)
        p.setFont(self.font())
        text = QFontMetrics(self.font()).elidedText(
            self.text(), Qt.TextElideMode.ElideRight, int(r.width()) - 2 * m.GAP_INLINE)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)


class IconButton(_States, QPushButton):
    """只有图标的按钮：命中区 32×32、图标 20。必须有 Tooltip 和可访问名称（13 章）。"""

    def __init__(self, icon: str, tooltip: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon_name = icon
        self._init_states()
        self.setAutoDefault(False)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.restyle()

    def restyle(self) -> None:
        hit = theme.scaled(m.ICON_BUTTON)
        self.setFixedSize(hit, hit)
        self.update()

    def paintEvent(self, _e) -> None:               # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        _capsule(p, r, theme.state_color(QColor(0, 0, 0, 0), hover=self._hover.value,
                                         pressed=max(self._press.value, 0.0)))
        size = m.ICON_ACTION
        box = QRectF(r.center().x() - size / 2, r.center().y() - size / 2, size, size)
        icons.paint(p, self.icon_name, box,
                    theme.color("label1" if self.isEnabled() else "label3"))


# ----------------------------- 输入 -----------------------------------------
class _Field:
    """胶囊输入的底：fill8 填充、不描边（16.1）；错误时加一圈红边，主要线索是下方那行红字。"""

    def _paint_field(self) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        base = theme.color("fill8")
        if not self.isEnabled():
            base.setAlphaF(base.alphaF() / 2)
        _capsule(p, r, base)
        if self.property("state") == "error":
            p.setPen(QPen(theme.color("error"), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            rr = r.adjusted(0.5, 0.5, -0.5, -0.5)
            p.drawRoundedRect(rr, rr.height() / 2, rr.height() / 2)
        p.end()

    def set_error(self, error: bool) -> None:
        self.setProperty("state", "error" if error else "")
        self.update()


class LineEdit(_Field, QLineEdit):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("alwaysRing", True)
        self.restyle()

    def restyle(self) -> None:
        self.setFixedHeight(theme.scaled(m.INPUT_HEIGHT))
        pad = m.PAD_CONTROL_X
        self.setTextMargins(pad - 2, 0, pad - 2, 0)
        self.update()

    def paintEvent(self, e) -> None:                # noqa: N802
        self._paint_field()
        super().paintEvent(e)


class _Spin(_Field):
    """数字输入。滚轮不改值：鼠标停在上面滚页面时把数字改掉，是个没人想要的副作用。"""

    def _init_spin(self, width: int) -> None:
        self.setProperty("alwaysRing", True)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setKeyboardTracking(False)            # 敲完（回车或离开）才算改了
        self._width = width
        self.restyle()

    def restyle(self) -> None:
        self.setFixedSize(theme.scaled(self._width), theme.scaled(m.INPUT_HEIGHT))
        self.lineEdit().setTextMargins(m.PAD_CONTROL_X - 4, 0, m.PAD_CONTROL_X - 4, 0)
        self.update()

    def wheelEvent(self, event) -> None:            # noqa: N802
        event.ignore()

    def paintEvent(self, _e) -> None:               # noqa: N802
        self._paint_field()                         # 文字由里面那个 QLineEdit 画


class SpinBox(_Spin, QSpinBox):
    def __init__(self, minimum: int, maximum: int, value: int, width: int = 96,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setValue(value)
        self.setGroupSeparatorShown(maximum >= 10_000)
        self._init_spin(width)


class DoubleSpinBox(_Spin, QDoubleSpinBox):
    def __init__(self, minimum: float, maximum: float, value: float, step: float,
                 suffix: str = "", width: int = 96, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setSingleStep(step)
        self.setDecimals(1)
        self.setSuffix(suffix)
        self.setValue(value)
        self._init_spin(width)


class _PopupDelegate(QStyledItemDelegate):
    """下拉列表的一行：ColorOS 弹出菜单的样子（16.5）。行高 32，悬停叠蒙层、圆角 8；
    当前值用主题色、字重 500，行尾打勾。"""

    def __init__(self, combo: "ComboBox") -> None:
        super().__init__(combo)
        self.combo = combo

    def width_for(self, text: str) -> int:
        fm = QFontMetrics(theme.font(theme.TITLE))
        return (fm.horizontalAdvance(text) + 2 * m.PAD_CONTROL_X + m.GAP_INLINE + m.ICON_INLINE)

    def sizeHint(self, _option, index) -> QSize:    # noqa: N802
        return QSize(self.width_for(str(index.data())), theme.scaled(m.MENU_ITEM))

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect)
        if option.state & (QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_Selected):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.color("hover"))
            painter.drawRoundedRect(r, m.RADIUS_SMALL, m.RADIUS_SMALL)
        current = index.row() == self.combo.currentIndex()
        pad, icon = m.PAD_CONTROL_X, m.ICON_INLINE
        painter.setFont(theme.font(theme.TITLE if current else theme.BODY))
        painter.setPen(theme.color("primaryText" if current else "label1"))
        text_rect = r.adjusted(pad - m.GAP_RELATED, 0, -(pad + icon + m.GAP_INLINE), 0)
        text = QFontMetrics(painter.font()).elidedText(
            str(index.data()), Qt.TextElideMode.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         text)
        if current:
            icons.paint(painter, "check",
                        QRectF(r.right() - pad - icon, r.center().y() - icon / 2, icon, icon),
                        theme.color("primaryText"))
        painter.restore()


def animate_popup(popup: QWidget, from_above: bool = True) -> None:
    """下拉、菜单弹出：淡入，同时从控件那一侧滑出几个像素（COUI 菜单弹簧，略带回弹）。"""
    winapi.round_corners(int(popup.winId()))
    if theme.reduce_motion():
        return
    end = popup.pos()
    shift = m.MENU_OFFSET * (-1 if from_above else 1)

    def step() -> None:
        k = anim.value
        popup.setWindowOpacity(min(1.0, max(0.0, k * 1.6)))
        popup.move(end.x(), round(end.y() + shift * (1 - k)))

    anim = Anim(popup, 0.0, on_change=step)
    popup._popup_anim = anim                       # 挂在窗口上，别被回收
    step()
    anim.to(1.0, "menu")


class ComboBox(_States, QComboBox):
    """下拉选择。``quiet`` 没有底，只有当前值和箭头（设置行尾，16.5）；``filled`` 是胶囊。

    宽度跟着当前值走：文字和箭头作为一组，两边留白一样，不按最长的选项空出一大段。
    滚轮不改选项。
    """

    def __init__(self, items: Sequence[str] = (), kind: str = "quiet",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self._init_states()
        self.setView(QListView())
        self.view().setItemDelegate(_PopupDelegate(self))
        self.view().setMouseTracking(True)
        self.addItems(list(items))
        self.currentIndexChanged.connect(lambda _: self.updateGeometry())
        self.restyle()

    def restyle(self) -> None:
        self.setFont(theme.font(theme.BODY))
        self.setFixedHeight(theme.scaled(m.INPUT_HEIGHT))
        self.updateGeometry()
        self.update()

    def wheelEvent(self, event) -> None:            # noqa: N802
        event.ignore()

    def showPopup(self) -> None:                    # noqa: N802
        delegate = self.view().itemDelegate()
        widest = max((delegate.width_for(self.itemText(i)) for i in range(self.count())),
                     default=0)
        # 列表自己还有 4 的内边距（QSS），宽度要把它加上，不然最长的一项会被截断
        self.view().setMinimumWidth(max(self.width(), m.MENU_MIN_WIDTH,
                                        widest + 2 * m.GAP_RELATED))
        super().showPopup()
        # Qt 把列表贴着控件放；照 COUI 离开 8，设置行尾的下拉跟着右对齐，不往卡片外伸
        popup = self.view().window()
        top_left = self.mapToGlobal(QPoint(0, 0))
        gap = m.GAP_INLINE
        above = popup.geometry().top() < top_left.y()
        x = top_left.x() + (self.width() - popup.width() if self.kind == "quiet" else 0)
        y = top_left.y() - gap - popup.height() if above else top_left.y() + self.height() + gap
        screen = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        x = max(screen.left(), min(x, screen.right() - popup.width()))
        y = max(screen.top(), min(y, screen.bottom() - popup.height()))
        popup.move(x, y)
        animate_popup(popup, from_above=not above)

    def sizeHint(self) -> QSize:                    # noqa: N802
        fm = QFontMetrics(self.font())
        pad = m.PAD_CONTROL_X if self.kind == "filled" else m.GAP_INLINE
        w = (fm.horizontalAdvance(self.currentText() or " ") + 2 * pad
             + m.ICON_INLINE + m.GAP_RELATED)
        return QSize(w, self.height() or m.INPUT_HEIGHT)

    def minimumSizeHint(self) -> QSize:             # noqa: N802
        return self.sizeHint()

    def paintEvent(self, _e) -> None:               # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        filled = self.kind == "filled"
        base = theme.color("fill8") if filled else QColor(0, 0, 0, 0)
        hover = self._hover.value if self.isEnabled() else 0.0
        _capsule(p, r, theme.state_color(base, hover=hover, pressed=max(self._press.value, 0.0)))

        pad = m.PAD_CONTROL_X if filled else m.GAP_INLINE
        icon = m.ICON_INLINE
        chevron = QRectF(r.right() - pad - icon, (r.height() - icon) / 2, icon, icon)
        role = "label3" if not self.isEnabled() else ("label1" if filled else "label2")
        icons.paint(p, "chevron-down", chevron, theme.color(role))
        p.setPen(theme.color(role))
        p.setFont(self.font())
        text_rect = QRectF(pad, 0, chevron.left() - m.GAP_RELATED - pad, r.height())
        text = QFontMetrics(self.font()).elidedText(
            self.currentText(), Qt.TextElideMode.ElideRight, int(text_rect.width()))
        align = Qt.AlignmentFlag.AlignVCenter | (
            Qt.AlignmentFlag.AlignLeft if filled else Qt.AlignmentFlag.AlignRight)
        p.drawText(text_rect, align, text)


class Switch(QAbstractButton):
    """COUI 开关 44×24，滑块 18。开是主色轨道，关是 controlTrack；越过终点时滑块被挤扁一点。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(m.SWITCH_WIDTH, m.SWITCH_HEIGHT)
        self.setProperty("focusRadius", m.SWITCH_HEIGHT / 2)
        self._pos = Anim(self)
        # 还没显示出来时（页面初始化 setChecked）直接到位，不在打开页面时播一遍动画
        self.toggled.connect(lambda on: self._pos.to(1.0 if on else 0.0, "switch",
                                                     instant=not self.isVisible()))

    def restyle(self) -> None:
        self.update()

    def sizeHint(self) -> QSize:                    # noqa: N802
        return QSize(m.SWITCH_WIDTH, m.SWITCH_HEIGHT)

    def hitButton(self, pos) -> bool:               # noqa: N802
        return self.rect().contains(pos)

    def paintEvent(self, _e) -> None:               # noqa: N802
        # blockSignals 之后 setChecked 不发 toggled，动画没跑时以实际状态为准
        target = 1.0 if self.isChecked() else 0.0
        if not self._pos.running():
            self._pos.value = target
        raw = self._pos.value
        k = min(1.0, max(0.0, raw))
        squeeze = min(0.3, 3 * max(raw - 1.0, -raw, 0.0))     # COUI stretchMax 1.3
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.3)                       # COUI disabledOnAlpha 77/255
        on, off = theme.color("primary"), theme.color("controlTrack")
        track = QColor.fromRgbF(off.redF() + (on.redF() - off.redF()) * k,
                                off.greenF() + (on.greenF() - off.greenF()) * k,
                                off.blueF() + (on.blueF() - off.blueF()) * k,
                                off.alphaF() + (on.alphaF() - off.alphaF()) * k)
        r = QRectF(self.rect())
        _capsule(p, r, track)
        d = m.SWITCH_THUMB
        inset = (r.height() - d) / 2
        x = inset + k * (r.width() - 2 * inset - d)
        w = d * (1 + squeeze)
        if raw > 1.0:
            x -= w - d                                         # 顶在右端，往左挤
        thumb = QRectF(x, inset, w, d)
        p.setBrush(theme.color("switch.thumbShadowColor"))
        p.drawRoundedRect(thumb.adjusted(-0.5, 1, 0.5, 1.5), d / 2 + 0.5, d / 2 + 0.5)
        p.setBrush(theme.color("switch.thumb"))
        p.drawRoundedRect(thumb, d / 2, d / 2)


# ----------------------------- 卡片与设置行 ---------------------------------
class Surface(QFrame):
    """自绘圆角面，带抗锯齿。``fill`` 是颜色角色，可以半透明（暗色卡片是 10% 白）。"""

    def __init__(self, fill: str = "card", radius: int = m.RADIUS_CARD,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.fill_role = fill
        self.radius = radius

    def paintEvent(self, _e) -> None:               # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.color(self.fill_role))
        p.drawRoundedRect(QRectF(self.rect()), self.radius, self.radius)


class Divider(QWidget):
    """卡片内的分割线：一个设备像素，起点对齐文字左缘，终点离卡片右边 16（第 7 章）。"""

    def __init__(self, inset: int = m.PAD_CONTAINER, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.inset = inset
        self.setFixedHeight(1)

    def paintEvent(self, _e) -> None:               # noqa: N802
        p = QPainter(self)
        h = 1.0 / self.devicePixelRatioF()
        p.fillRect(QRectF(self.inset, 0, self.width() - 2 * self.inset, h),
                   theme.color("divider"))


class Card(Surface):
    """同一分组里相邻的行拼成一张卡；卡片不描边、不加阴影（第 3 章）。"""

    def __init__(self, fill: str = "card", parent: QWidget | None = None) -> None:
        super().__init__(fill, m.RADIUS_CARD, parent)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        self.rows: list[QWidget] = []
        self._dividers: list[Divider | None] = []
        self._hidden: set[int] = set()

    def add_row(self, widget: QWidget) -> QWidget:
        divider = None
        if self.rows:
            divider = Divider()
            self.body.addWidget(divider)
        self.rows.append(widget)
        self._dividers.append(divider)
        self.body.addWidget(widget)
        self._relink()
        return widget

    def set_row_visible(self, widget: QWidget, visible: bool) -> None:
        """藏起一行，连它上面那条分割线一起；首尾圆角跟着剩下的行走。"""
        (self._hidden.discard if visible else self._hidden.add)(id(widget))
        self._relink()

    def _relink(self) -> None:
        shown = [r for r in self.rows if id(r) not in self._hidden]
        for row, divider in zip(self.rows, self._dividers):
            visible = id(row) not in self._hidden
            row.setVisible(visible)
            if divider is not None:
                divider.setVisible(visible and bool(shown) and row is not shown[0])
            if isinstance(row, SettingRow) and visible:
                row.set_edges(row is shown[0], row is shown[-1])

    def clear(self) -> None:
        while self.body.count():
            item = self.body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.rows.clear()
        self._dividers.clear()
        self._hidden.clear()


class SettingRow(QWidget):
    """一行设置：标题（14 / 500）+ 摘要（12，次要色），行尾是控件或当前值。

    行高 40，带摘要 58（16.1）。开关行、下拉行整行可点：点在行上等于点控件，和 ColorOS
    的设置项一样；给了 ``on_click`` 的行整行是一个按钮（键盘上 Enter / Space 也能触发）。
    悬停叠一层蒙层，首尾行的蒙层跟着卡片的圆角走。

    ⚠️ 行高**不要用** ``setMinimumHeight`` 定：Qt 的 ``qSmartMinSize`` 里显式设过的最小高度会
    顶掉布局算出来的那个，空间一紧行就被压到比内容还矮。高度由文字列的上下内边距撑出来，
    行本身纵向 Fixed，文字随系统字号变大时行跟着长。
    """

    activated = Signal()

    def __init__(self, title: str, desc: str = "", *controls: QWidget,
                 on_click: Callable[[], None] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controls = controls
        self._top = self._bottom = False
        self._hover = Anim(self)
        self._on_click = on_click
        toggles = len(controls) == 1 and isinstance(controls[0], (Switch, ComboBox))
        self.interactive = on_click is not None or toggles
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, self.interactive)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        if on_click is not None:
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setProperty("focusRadius", m.RADIUS_SMALL)
            self.setAccessibleName(title)

        row = QHBoxLayout(self)
        row.setContentsMargins(m.PAD_CONTAINER, 0, m.PAD_CONTAINER, 0)
        row.setSpacing(m.GAP_GROUP)

        texts = QVBoxLayout()
        texts.setContentsMargins(0, m.PAD_CONTROL_Y, 0, m.PAD_CONTROL_Y)
        texts.setSpacing(2)
        self.title = label(title, "title")
        self.title.setMinimumHeight(theme.line_height(theme.TITLE))
        texts.addWidget(self.title)
        self.desc = ElidedLabel(desc)
        self.desc.setMinimumHeight(theme.line_height(theme.SECONDARY))
        self.desc.setVisible(bool(desc))
        texts.addWidget(self.desc)
        row.addLayout(texts, 1)

        for control in controls:
            if not isinstance(control, (QLabel, ElidedLabel)):
                control.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        if toggles:
            # 读屏要能把控件和它的标题对上，不能只念「开关」
            controls[0].setAccessibleName(title)

    def set_desc(self, text: str) -> None:
        self.desc.setText(text)
        self.desc.setVisible(bool(text))

    def set_edges(self, top: bool, bottom: bool) -> None:
        self._top, self._bottom = top, bottom

    def _can_activate(self) -> bool:
        if not self.isEnabled():
            return False
        return self._on_click is not None or self.controls[0].isEnabled()

    def enterEvent(self, e) -> None:                # noqa: N802
        if self.interactive and self._can_activate():
            self._hover.to(1, "state")
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:                # noqa: N802
        self._hover.to(0, "state")
        super().leaveEvent(e)

    def _activate(self) -> None:
        if self._on_click is not None:
            self._on_click()
        elif isinstance(self.controls[0], Switch):
            self.controls[0].click()
        else:
            self.controls[0].showPopup()

    def mouseReleaseEvent(self, e) -> None:         # noqa: N802
        if (self.interactive and e.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(e.position().toPoint()) and self._can_activate()):
            self._activate()
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e) -> None:             # noqa: N802
        if (self._on_click is not None and self._can_activate()
                and e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)):
            self._activate()
            return
        super().keyPressEvent(e)

    def paintEvent(self, _e) -> None:               # noqa: N802
        if self._hover.value <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = theme.color("hover")
        c.setAlphaF(c.alphaF() * min(1.0, self._hover.value))
        r = QRectF(self.rect())
        rad = float(m.RADIUS_CARD)
        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)
        # 中间的行是直角；只有卡片首尾那两个角是圆的
        if not self._top:
            path.addRect(QRectF(r.left(), r.top(), r.width(), rad))
        if not self._bottom:
            path.addRect(QRectF(r.left(), r.bottom() - rad, r.width(), rad))
        path.setFillRule(Qt.FillRule.WindingFill)
        p.fillPath(path.simplified(), c)


def value_label(text: str = "") -> QLabel:
    """行尾的当前值：正文字号、次要色。"""
    return label(text, "value")


class Section(QWidget):
    """分组标题（12 / 500，次要色，可省）+ 卡片 + 页脚说明。标题和页脚跟卡片里的文字左缘对齐。"""

    def __init__(self, title: str = "", note: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        inset = m.PAD_CONTAINER
        if title:
            head = label(title, "groupTitle")
            head.setContentsMargins(inset, 0, inset, 0)
            lay.addWidget(head)
            lay.addSpacing(m.GAP_INLINE)
        self.card = Card()
        lay.addWidget(self.card)
        self.note = label(note, "secondary", wrap=True)
        self.note.setContentsMargins(inset, m.GAP_INLINE, inset, 0)
        self.note.setVisible(bool(note))
        lay.addWidget(self.note)

    def add_row(self, widget: QWidget) -> QWidget:
        return self.card.add_row(widget)

    def set_note(self, text: str) -> None:
        self.note.setText(text)
        self.note.setVisible(bool(text))


# ----------------------------- 页面 -----------------------------------------
def _centered(child: QWidget) -> QHBoxLayout:
    """把 ``child`` 放进一行：最宽 720，多出来的宽度两侧均分（16.2）。"""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    child.setMaximumWidth(m.CONTENT_MAX_WIDTH)
    # 列的拉伸因子压过两侧留白：先长到可用宽度、被 720 截住，剩下的空间才由两侧均分
    child.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    row.addStretch(1)
    row.addWidget(child, 100)
    row.addStretch(1)
    return row


class Page(QWidget):
    """一页：固定在顶上的页面标题 + 右侧操作，下面是会滚动的内容列。

    标题和内容列用同一套居中规则，所以左边缘天然对齐，不用量了再挪。
    **每一页都要套滚动**：不套的话窗口一矮，布局会去压每张卡片。
    """

    def __init__(self, title: str) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("PageHeader")
        head = QHBoxLayout(header)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(m.GAP_CONTROL)
        self.title = label(title, "pageTitle")
        self.title.setMinimumHeight(theme.line_height(theme.PAGE_TITLE))
        head.addWidget(self.title)
        head.addStretch(1)
        self.actions = head
        self._header_row = _centered(header)
        self._header_holder = QWidget()
        self._header_holder.setObjectName("PageHeader")
        self._header_holder.setLayout(self._header_row)
        outer.addWidget(self._header_holder)

        scroll = QScrollArea()
        scroll.setObjectName("PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll, 1)

        host = QWidget()
        host.setObjectName("PageBody")
        column = QWidget()
        column.setObjectName("PageBody")
        self._column_row = _centered(column)
        host.setLayout(self._column_row)
        scroll.setWidget(host)
        self.body = QVBoxLayout(column)
        self.body.setContentsMargins(0, 0, 0, m.PAGE_BOTTOM)
        # 卡间 12；带分组标题时 12 + 标题 16 + 8，正好是「分组之间约 32」（16.1）
        self.body.setSpacing(m.GAP_CARD)
        self.set_margin(m.PAGE_MARGIN_EXPANDED)

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)

    def set_margin(self, margin: int) -> None:
        """页边距跟着窗口类走：≥840 为 40，600～840 为 24（16.2）。"""
        self.margin = margin
        self._header_row.setContentsMargins(margin, m.PAGE_TOP, margin, m.GAP_GROUP)
        self._column_row.setContentsMargins(margin, 0, margin, 0)


# ----------------------------- 反馈 -----------------------------------------
class EmptyState(QWidget):
    """空状态：标题写「暂无 X」；首次使用加一句怎么开始（11.3）。"""

    def __init__(self, title: str = "", desc: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 48, 0, 48)       # COUI emptyState.unboundedPaddingV
        lay.setSpacing(2)
        self.title_label = label(title, "emptyTitle")
        self.desc_label = label(desc, "secondary", wrap=True)
        for w in (self.title_label, self.desc_label):
            w.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)
        self.set_state(title, desc)

    def set_state(self, title: str, desc: str = "") -> None:
        self.title_label.setText(title)
        self.desc_label.setText(desc)
        self.desc_label.setVisible(bool(desc))


class Toast(QFrame):
    """窗口底部居中的一条提示（COUI Snackbar，16.5：距底 24），不抢焦点。

    成功写「已 X」，失败写原因和补救。失败的提示不自动消失，留一个「关闭」；
    带动作（撤销）的也留着，不然按钮一闪就没。
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(m.PAD_CONTROL_X, m.GAP_RELATED, m.GAP_RELATED, m.GAP_RELATED)
        lay.setSpacing(m.GAP_INLINE)
        self._text = label("", "title")
        self._text.setMinimumHeight(theme.scaled(m.BUTTON_HEIGHT))
        lay.addWidget(self._text, 1)
        self._action = Button("", "quiet")
        self._action.clicked.connect(self._run_action)
        lay.addWidget(self._action)
        self._on_action: Callable[[], None] | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._offset = Anim(self, on_change=self._place, on_done=self._settled)
        self.restyle()
        self.hide()

    def restyle(self) -> None:
        _shadow(self, m.SHADOW_FLOAT)
        self.update()

    def paintEvent(self, _e) -> None:               # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        _capsule(p, QRectF(self.rect()), theme.color("snackBar.bg"),
                 min(self.height() / 2, m.RADIUS_CARD))

    def _away(self) -> float:
        return self.height() + m.TOAST_BOTTOM + 24     # 连阴影一起滑出窗口

    def _place(self) -> None:
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2,
                  round(parent.height() - self.height() - m.TOAST_BOTTOM + self._offset.value))

    def _settled(self) -> None:
        if self._offset.target > 0:
            self.hide()

    def show_message(self, text: str, *, error: bool = False,
                     action: tuple[str, Callable[[], None]] | None = None) -> None:
        self._text.setText(text)
        self.setAccessibleName(text)
        if action is None and error:
            action = ("关闭", self.dismiss)
        self._on_action = action[1] if action else None
        self._action.setText(action[0] if action else "")
        self._action.setVisible(action is not None)
        self._action.updateGeometry()
        parent = self.parentWidget()
        self.setMaximumWidth(max(240, parent.width() - 2 * m.PAGE_MARGIN_EXPANDED))
        self.adjustSize()
        if not self.isVisible():
            self._offset.value = self._away()
        self._place()
        self.raise_()
        self.show()
        self._offset.to(0, "toastIn")
        self._timer.stop()
        if action is None:
            self._timer.start(m.TOAST_MS)

    def _run_action(self) -> None:
        callback, self._on_action = self._on_action, None
        self.dismiss()
        if callback is not None and callback != self.dismiss:
            callback()

    def dismiss(self) -> None:
        self._timer.stop()
        if self.isVisible():
            self._offset.to(self._away(), "toastOut")

    def parent_resized(self) -> None:
        if self.isVisible():
            self._place()


# ----------------------------- 面板 -----------------------------------------
class Panel(QDialog):
    """居中浮起的面板（16.5：手机的底部面板在电脑上居中浮起，最宽 540，四角全圆）。

    盖住父窗口客户区：一层遮罩 + 中间一张卡。顶栏左「取消」、中间标题、右「完成」
    （第 8 章面板顶栏）。点遮罩、Esc 都是取消；Enter 触发「完成」。
    进场从 0.8 放大淡入，出场只淡出（COUI 居中对话框，DESIGN.md 16.4）。
    """

    def __init__(self, parent: QWidget, title: str, confirm: str = "完成",
                 cancel: str = "取消", width: int = m.PANEL_MAX_WIDTH) -> None:
        super().__init__(parent.window(), Qt.WindowType.Dialog
                         | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAccessibleName(title)
        self._width = width
        self._progress = 1.0
        self._snapshot: QPixmap | None = None
        self._closing = False
        self._result_code = QDialog.DialogCode.Rejected
        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._animate)
        self._anim.finished.connect(self._animated)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(m.PAGE_MARGIN_COMPACT, m.PAGE_MARGIN_COMPACT,
                                 m.PAGE_MARGIN_COMPACT, m.PAGE_MARGIN_COMPACT)
        outer.addStretch(1)
        self.card = Surface("surfaceGrouped", m.RADIUS_DIALOG)
        self.card.setFixedWidth(width)
        outer.addWidget(self.card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(m.GAP_INLINE, m.GAP_INLINE, m.GAP_INLINE, m.DIALOG_PADDING)
        lay.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        self.cancel_button = Button(cancel, "quiet")
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button = Button(confirm, "quiet")
        self.confirm_button.clicked.connect(self._confirm)
        head = label(title, "dialogTitle")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar.addWidget(self.cancel_button)
        bar.addWidget(head, 1)
        bar.addWidget(self.confirm_button)
        lay.addLayout(bar)
        lay.addSpacing(m.GAP_INLINE)
        self._bar = bar
        # 正文放进滚动区：窗口矮到放不下时可以滚，而不是把行挤扁
        self._body_holder = QWidget()
        self._body_holder.setObjectName("PageBody")
        self.body = QVBoxLayout(self._body_holder)
        self.body.setContentsMargins(m.PAD_CONTAINER - m.GAP_INLINE, 0,
                                     m.PAD_CONTAINER - m.GAP_INLINE, 0)
        self.body.setSpacing(m.GAP_CARD)
        self._scroll = QScrollArea()
        self._scroll.setObjectName("PageScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._body_holder)
        lay.addWidget(self._scroll)
        # 正文里的行会随选择显示 / 隐藏（换规则类型），卡片高度要跟着重算
        self._body_holder.installEventFilter(self)
        install_focus_tracker(QApplication.instance())

    def eventFilter(self, obj, e) -> bool:          # noqa: N802
        if obj is self._body_holder and e.type() == QEvent.Type.LayoutRequest:
            self._fit_card()
        return False

    def _fit_card(self) -> None:
        """卡片高度 = 顶栏 + 正文的自然高度，但不超过窗口；超出的部分在正文里滚动。

        正文可能有折行的标签，高度得按宽度算；没有折行时 heightForWidth 返回 -1。
        """
        inner = self._width - 2 * m.GAP_INLINE
        body = self.body
        natural = (body.totalHeightForWidth(inner) if body.hasHeightForWidth()
                   else body.totalSizeHint().height())
        margins = self.card.layout().contentsMargins()
        want = (margins.top() + self._bar.sizeHint().height() + m.GAP_INLINE + natural
                + margins.bottom())
        room = self.height() - 2 * m.PAGE_MARGIN_COMPACT
        self.card.setFixedHeight(min(want, room) if room > 0 else want)

    # ---- 结果 ----
    def validate(self) -> bool:
        """子类覆盖：数据不对就在对应字段下写原因并返回 False，面板不关。"""
        return True

    def _confirm(self) -> None:
        if self.validate():
            self._close_animated(QDialog.DialogCode.Accepted)

    def reject(self) -> None:
        self._close_animated(QDialog.DialogCode.Rejected)

    def keyPressEvent(self, e) -> None:             # noqa: N802
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.confirm_button.isEnabled():
                self._confirm()
            return
        super().keyPressEvent(e)

    def mousePressEvent(self, e) -> None:           # noqa: N802
        if not self.card.geometry().contains(e.position().toPoint()):
            self.reject()
            return
        super().mousePressEvent(e)

    def run(self) -> bool:
        """模态打开，关掉之后返回是不是点了「完成」。焦点会回到打开它之前的控件。"""
        before = QApplication.focusWidget()
        win = self.parentWidget()
        central = getattr(win, "centralWidget", lambda: None)() or win
        top_left = central.mapToGlobal(QPoint(0, 0))
        self.setGeometry(top_left.x(), top_left.y(), central.width(), central.height())
        self._fit_card()
        if not theme.reduce_motion():
            # 先透明地显示一帧，拿到排好版的卡片截图，再从截图开始放大淡入
            self.setWindowOpacity(0.0)
            QTimer.singleShot(0, self._open_animated)
        else:
            QTimer.singleShot(0, self._focus_first)
        accepted = self.exec() == QDialog.DialogCode.Accepted
        if before is not None:
            try:
                before.setFocus()
            except RuntimeError:
                pass
        return accepted

    def _focus_first(self) -> None:
        self.focusNextChild()

    # ---- 动画 ----
    def _animate(self, v) -> None:
        self._progress = float(v)
        self.update()

    def _play(self, start: float, end: float, ms: int, curve: tuple) -> None:
        self._anim.stop()
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setDuration(ms)
        self._anim.setEasingCurve(_bezier(*curve))
        self._anim.start()

    def _animated(self) -> None:
        if self._closing:
            super().done(self._result_code)
            return
        self._snapshot = None
        self.card.show()
        self._focus_first()

    def _snapshot_card(self) -> QPixmap:
        """卡片截图，圆角外面透明。不能用 ``grab()``：它会先用窗口底色铺满整个矩形。"""
        dpr = self.devicePixelRatioF()
        pix = QPixmap(round(self.card.width() * dpr), round(self.card.height() * dpr))
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.GlobalColor.transparent)
        self.card.render(pix, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
        return pix

    def _open_animated(self) -> None:
        self._snapshot = self._snapshot_card()
        self.card.hide()
        self._progress = 0.0
        self.setWindowOpacity(1.0)
        self._play(0.0, 1.0, m.DIALOG_IN_MS, m.DIALOG_IN_BEZIER)

    def _close_animated(self, code) -> None:
        if self._closing:
            return
        self._closing = True
        self._result_code = code
        if theme.reduce_motion():
            super().done(code)
            return
        if self._snapshot is None:
            self._snapshot = self._snapshot_card()
        self.card.hide()
        self._play(self._progress, 0.0, m.DIALOG_OUT_MS, m.DIALOG_OUT_BEZIER)

    def _paint_shadow(self, p: QPainter, rect: QRectF, alpha: float) -> None:
        color, blur, y = theme.shadow(m.SHADOW_DIALOG)
        steps = 10
        rad = float(m.RADIUS_DIALOG)
        for i in range(steps, 0, -1):
            grow = blur / 2 * i / steps
            c = QColor(color)
            c.setAlphaF(color.alphaF() * alpha * (1 - i / (steps + 1)) ** 2 * 3 / steps)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(rect.adjusted(-grow, -grow + y * 0.6, grow, grow + y),
                              rad + grow, rad + grow)

    def paintEvent(self, _e) -> None:               # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        k = self._progress
        scrim = theme.color("scrim")
        scrim.setAlphaF(scrim.alphaF() * k)
        p.fillRect(self.rect(), scrim)
        rect = QRectF(self.card.geometry())
        if self._snapshot is not None:
            s = 1.0 if self._closing else m.DIALOG_SCALE_FROM + (1 - m.DIALOG_SCALE_FROM) * k
            c = rect.center()
            rect = QRectF(c.x() - rect.width() * s / 2, c.y() - rect.height() * s / 2,
                          rect.width() * s, rect.height() * s)
        self._paint_shadow(p, rect, k)
        if self._snapshot is not None:
            p.setOpacity(k)
            p.drawPixmap(rect, self._snapshot, QRectF(self._snapshot.rect()))


# ----------------------------- 统计 -----------------------------------------
class StatTile(Surface):
    """一块汇总：大数字 + 一行标签。"""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__("card", m.RADIUS_CARD, parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(m.PAD_CONTAINER, m.PAD_CONTROL_Y + 2,
                               m.PAD_CONTAINER, m.PAD_CONTROL_Y + 4)
        box.setSpacing(0)
        self.value = label("0", "metric")
        self.caption = label(caption, "secondary")
        box.addWidget(self.value)
        box.addWidget(self.caption)

    def set_value(self, value: int) -> None:
        self.value.setText(f"{value:,}")
        self.setAccessibleName(f"{self.caption.text()} {value}")

    def set_caption(self, text: str) -> None:
        self.caption.setText(text)


class DailyChart(QWidget):
    """每日 寸 / AJ / FC 三条折线，画在实色内容面上（16.3：平铺内容不直接铺在 Mica 上）。

    颜色克制：只有「寸」这条用主题色，是这一屏的焦点；AJ、FC 用两级中性色。
    **颜色不是唯一区分手段**：三条线各有自己的线型和标记形状，图例上一模一样。
    """

    _PAD_L, _PAD_R, _PAD_T, _PAD_B = 44, 16, 36, 30
    _SERIES = (("寸", "primary", Qt.PenStyle.SolidLine, "circle"),
               ("AJ", "label1", Qt.PenStyle.DashLine, "square"),
               ("FC", "label2", Qt.PenStyle.DotLine, "triangle"))

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, int, int, int]] = []
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("每日寸、AJ、FC 曲线")

    def set_data(self, data: Sequence[tuple[str, int, int, int]]) -> None:
        self._data = list(data)
        self.update()

    def paintEvent(self, _e) -> None:               # noqa: N802
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        plot_w = max(1, w - self._PAD_L - self._PAD_R)
        plot_h = max(1, h - self._PAD_T - self._PAD_B)
        # 纵轴取整数刻度：4 格，每格是整数，顶上留一点空
        steps = 4
        peak = max(max(d[1], d[2], d[3]) for d in self._data)
        step = max(1, math.ceil((peak + 1) / steps))
        y_top = step * steps

        def xpos(i: int) -> float:
            if len(self._data) == 1:
                return self._PAD_L + plot_w / 2
            return self._PAD_L + plot_w * i / (len(self._data) - 1)

        def ypos(v: float) -> float:
            return self._PAD_T + plot_h * (1 - v / y_top)

        p.setFont(theme.font(theme.SECONDARY))
        grid, axis = theme.color("divider"), theme.color("label2")
        for s in range(steps + 1):
            y = ypos(step * s)
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(self._PAD_L, y), QPointF(w - self._PAD_R, y))
            p.setPen(axis)
            p.drawText(QRectF(0, y - 8, self._PAD_L - 8, 16),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                       str(step * s))

        for idx, (_name, role, style, marker) in enumerate(self._SERIES, start=1):
            color = theme.color(role)
            path = QPainterPath()
            for i, row in enumerate(self._data):
                x, y = xpos(i), ypos(row[idx])
                path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(color, 2, style, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)
            if len(self._data) <= 60:        # 点太多就只留线，不然是一条毛毛虫
                for i, row in enumerate(self._data):
                    self._marker(p, color, marker, xpos(i), ypos(row[idx]))

        # 横轴：首、中、末三个日期。两头的对齐到曲线端点往里写，别被边缘切掉
        p.setPen(axis)
        last = len(self._data) - 1
        for i in sorted({0, len(self._data) // 2, last}):
            month, day = self._data[i][0][5:7], self._data[i][0][8:10]
            text = f"{int(month)}月{int(day)}日"
            x, width = xpos(i), 80
            if i == 0 and last > 0:
                box, align = QRectF(x - 4, 0, width, 0), Qt.AlignmentFlag.AlignLeft
            elif i == last and last > 0:
                box, align = QRectF(x - width + 4, 0, width, 0), Qt.AlignmentFlag.AlignRight
            else:
                box, align = QRectF(x - width / 2, 0, width, 0), Qt.AlignmentFlag.AlignHCenter
            box.setTop(h - self._PAD_B + 8)
            box.setHeight(16)
            p.drawText(box, int(align | Qt.AlignmentFlag.AlignVCenter), text)

        # 图例：线型和标记跟绘制时一致，顺序也一致
        x = float(self._PAD_L)
        fm = QFontMetrics(p.font())
        for name, role, style, marker in self._SERIES:
            color = theme.color(role)
            p.setPen(QPen(color, 2, style))
            p.drawLine(QPointF(x, 14), QPointF(x + 18, 14))
            self._marker(p, color, marker, x + 9, 14)
            p.setPen(theme.color("label2"))
            p.drawText(QRectF(x + 24, 6, 60, 16),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), name)
            x += 24 + fm.horizontalAdvance(name) + m.GAP_GROUP + m.GAP_INLINE
        p.end()

    @staticmethod
    def _marker(p: QPainter, color: QColor, kind: str, x: float, y: float) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        if kind == "circle":
            p.drawEllipse(QRectF(x - 3, y - 3, 6, 6))
        elif kind == "square":
            p.drawRect(QRectF(x - 2.6, y - 2.6, 5.2, 5.2))
        else:
            tri = QPainterPath()
            tri.moveTo(x, y - 3.4)
            tri.lineTo(x + 3.2, y + 2.6)
            tri.lineTo(x - 3.2, y + 2.6)
            tri.closeSubpath()
            p.fillPath(tri, color)


# ----------------------------- 换主题 ---------------------------------------
def restyle_tree(root: QWidget) -> None:
    """换主题时就地重新上色，**不重建页面**：选中项、输入到一半的内容、滚动位置都不受影响。"""
    for widget in [root, *root.findChildren(QWidget)]:
        restyle = getattr(widget, "restyle", None)
        if callable(restyle):
            restyle()
        else:
            widget.update()
