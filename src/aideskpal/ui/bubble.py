"""Frameless, always-on-top speech bubble that follows the pet."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QWidget

from aideskpal.ui.theme import STYLE_NAMES, app_font

MAX_WIDTH = 330
MIN_WIDTH = 160


class SpeechBubble(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._accent = QColor(185, 167, 255)
        self._surface = QColor(21, 18, 36, 242)
        self._tail_below = True
        self._anchor = QRect()
        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setFont(app_font(10))
        self._label.setStyleSheet("color: #f5f1ff; background: transparent;")
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_message)
        self.hide()

    def show_message(
        self,
        text: str,
        *,
        anchor: QRect,
        seconds: float = 8.0,
        style: str = "soft",
    ) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._anchor = QRect(anchor)
        accent, surface = STYLE_NAMES.get(style, STYLE_NAMES["soft"])
        self._accent = QColor(accent)
        self._surface = QColor(surface)
        self._label.setText(text)
        self._label.setFont(app_font(10))
        metrics = QFontMetrics(self._label.font())
        available = MAX_WIDTH - 34
        bounds = metrics.boundingRect(
            QRect(0, 0, available, 1200),
            int(
                Qt.TextFlag.TextWordWrap
                | Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter
            ),
            text,
        )
        width = max(MIN_WIDTH, min(MAX_WIDTH, bounds.width() + 36))
        # Ask the label to wrap at the calculated width and measure again.
        self._label.setFixedWidth(max(80, width - 32))
        self._label.adjustSize()
        height = self._label.height() + 28 + 10
        self.setFixedSize(width, height)
        self._position_near_anchor()
        self.setWindowOpacity(0.0)
        self.show()
        self._label.show()
        from PySide6.QtCore import QPropertyAnimation

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(150)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(max(1500, int(seconds * 1000)))

    def _position_near_anchor(self) -> None:
        anchor = self._anchor
        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        x = anchor.center().x() - self.width() // 2
        x = max(available.left() + 6, min(x, available.right() - self.width() - 6))
        desired_top = anchor.top() - self.height() - 8
        if desired_top >= available.top() + 4:
            self._tail_below = True
            y = desired_top
        else:
            self._tail_below = False
            y = min(anchor.bottom() + 8, available.bottom() - self.height() - 4)
        self.move(QPoint(x, y))

    def reposition(self, anchor: QRect) -> None:
        if not self.isVisible() or self.height() <= 0:
            return
        self._anchor = QRect(anchor)
        self._position_near_anchor()

    def hide_message(self) -> None:
        self._timer.stop()
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 12)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        tail_x = max(24.0, min(self.width() - 24.0, self.width() * 0.5 + 24))
        if self._tail_below:
            path.moveTo(tail_x - 8, rect.bottom() - 1)
            path.lineTo(tail_x, self.height() - 2)
            path.lineTo(tail_x + 9, rect.bottom() - 1)
        else:
            path.moveTo(tail_x - 8, rect.top() + 1)
            path.lineTo(tail_x, 1)
            path.lineTo(tail_x + 9, rect.top() + 1)
        path.closeSubpath()
        painter.setBrush(self._surface)
        painter.setPen(QPen(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 190), 1.2))
        painter.drawPath(path)
        # Inner glow line at the top.
        glow = QColor(self._accent)
        glow.setAlpha(50)
        painter.setPen(QPen(glow, 4))
        painter.drawLine(rect.left() + 20, rect.top() + 2, rect.right() - 20, rect.top() + 2)
        painter.end()
        # Place the label below/above depending on tail direction.
        top = 13 if self._tail_below else 19
        self._label.move(17, top)

    def set_anchor(self, anchor: QRect) -> None:
        self._anchor = anchor
        if self.isVisible():
            self.reposition(anchor)
