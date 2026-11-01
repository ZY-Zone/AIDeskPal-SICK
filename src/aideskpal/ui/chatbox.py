"""Small chat input that appears next to the pet."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

from aideskpal.ui.theme import app_font


class ChatBox(QWidget):
    submitted = Signal(str)
    dismissed = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFixedSize(370, 58)
        self._input = QLineEdit(self)
        self._input.setPlaceholderText("对桌宠说点什么…")
        self._input.setFont(app_font(10))
        self._input.setStyleSheet(
            "QLineEdit { background: rgba(20,17,32,245); color: #f5f1ff;"
            " border: 1px solid #b9a7ff; border-radius: 12px; padding: 10px 13px; }"
        )
        self._send = QPushButton("发送", self)
        self._send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send.setStyleSheet(
            "QPushButton { background: #b9a7ff; color: #171222; border: none;"
            " border-radius: 12px; padding: 10px 16px; font-weight: 700; }"
            " QPushButton:hover { background: #d3c6ff; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 7, 7, 9)
        layout.setSpacing(7)
        layout.addWidget(self._input, 1)
        layout.addWidget(self._send)
        self._send.clicked.connect(self._submit)
        self._input.returnPressed.connect(self._submit)
        self._anchor = QRect()
        self.hide()

    def open_at(self, anchor: QRect) -> None:
        """Show the input above ``anchor`` (the character), centred on it.

        ``anchor`` is the character silhouette, not the window box, so the input
        hovers over the head.  When the character sits near the top of the work
        area there is no room above it; the input then drops just *below* the
        head instead of below the whole body, which keeps it adjacent to the part
        the user double-clicked.
        """
        self._anchor = QRect(anchor)
        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        x = anchor.center().x() - self.width() // 2
        x = max(available.left() + 6, min(x, available.right() - self.width() - 6))
        y = anchor.top() - self.height() - 14
        if y < available.top() + 4:
            # No room overhead: sit under the head band rather than the feet.
            head_band = max(1, int(anchor.height() * 0.22))
            y = anchor.top() + head_band
            if y + self.height() > available.bottom() - 4:
                y = max(available.top() + 4, anchor.bottom() + 8)
        self.move(x, y)
        self._input.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()

    def _submit(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.hide()
        self.submitted.emit(text[:1000])

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.dismissed.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        # Do not hide immediately: clicking the send button also causes focus-out.
        super().focusOutEvent(event)
