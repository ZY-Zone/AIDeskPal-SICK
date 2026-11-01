"""Startup account gate: login, register, or continue as a guest."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from aideskpal import APP_NAME
from aideskpal.market.client import MarketClient
from aideskpal.ui.theme import app_icon, settings_stylesheet
from aideskpal.ui.workers import WorkerPool

logger = logging.getLogger(__name__)

MARKET_BASE = "http://sickcc.online/cwusr"


class LoginDialog(QDialog):
    """Shown once at startup when no session is saved.

    Closing the window is a valid guest path; the caller then clears the saved
    session and continues with local features only.
    """

    def __init__(self, username: str = "", parent=None) -> None:
        super().__init__(parent)
        self.session = ""
        self.username = ""
        self.guest = True
        self._busy = False
        self._workers = WorkerPool(self)
        self._client = MarketClient(MARKET_BASE)

        self.setWindowTitle(f"{APP_NAME} · 登录")
        self.setWindowIcon(app_icon(128))
        self.setModal(True)
        self.setMinimumWidth(430)
        self.setStyleSheet(settings_stylesheet())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 24, 26, 20)
        outer.setSpacing(14)
        title = QLabel("登录账号")
        title.setObjectName("Title")
        outer.addWidget(title)
        lead = QLabel(
            "登录后可以记录下载身份；游客也可以浏览市场并下载公开资源。\n"
            "关闭这个窗口即可按游客继续。"
        )
        lead.setObjectName("Subtitle")
        lead.setWordWrap(True)
        outer.addWidget(lead)

        group = QGroupBox("账号")
        form = QFormLayout(group)
        form.setContentsMargins(16, 20, 16, 14)
        form.setSpacing(10)
        self.mode = QComboBox()
        self.mode.addItems(["登录已有账号", "注册新账号"])
        self.mode.currentIndexChanged.connect(self._mode_changed)
        form.addRow("方式", self.mode)
        self.username_edit = QLineEdit(username)
        self.username_edit.setPlaceholderText("用户名（3-32 位）")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("密码（至少 8 位）")
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("邮箱（注册时可选）")
        form.addRow("用户名", self.username_edit)
        form.addRow("密码", self.password_edit)
        form.addRow("邮箱", self.email_edit)
        self.status = QLabel("")
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        form.addRow(self.status)
        outer.addWidget(group)

        buttons = QHBoxLayout()
        self.login_button = QPushButton("登录")
        self.login_button.setObjectName("Primary")
        self.login_button.setDefault(True)
        self.login_button.clicked.connect(self._submit)
        guest = QPushButton("以游客继续")
        guest.setObjectName("Ghost")
        guest.clicked.connect(self._guest)
        buttons.addWidget(self.login_button)
        buttons.addWidget(guest)
        buttons.addStretch(1)
        outer.addLayout(buttons)

    def _mode_changed(self, index: int) -> None:
        self.login_button.setText("登录" if index == 0 else "注册并登录")
        self.email_edit.setPlaceholderText(
            "邮箱（登录不需要）" if index == 0 else "邮箱（注册时可选）"
        )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for widget in (
            self.mode,
            self.username_edit,
            self.password_edit,
            self.email_edit,
            self.login_button,
        ):
            widget.setEnabled(not busy)
        self.login_button.setText("请稍候…" if busy else (
            "登录" if self.mode.currentIndex() == 0 else "注册并登录"
        ))

    def _submit(self) -> None:
        if self._busy:
            return
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        email = self.email_edit.text().strip()
        if len(username) < 3:
            self._error("用户名至少 3 位。")
            return
        if self.mode.currentIndex() == 0 and not password:
            self._error("请输入密码。")
            return
        if self.mode.currentIndex() == 1 and len(password) < 8:
            self._error("注册密码至少 8 位。")
            return
        self._client = MarketClient(MARKET_BASE)
        self._set_busy(True)
        self.status.setText("正在连接账号服务…")

        def work() -> dict[str, Any]:
            if self.mode.currentIndex() == 1:
                return self._client.register(username, password, email)
            return self._client.login(username, password)

        def done(_data: dict[str, Any]) -> None:
            self.session = self._client.session_cookie
            self.username = username
            self.guest = False
            self._set_busy(False)
            self.accept()

        def failed(message: str) -> None:
            self._set_busy(False)
            self._error(f"连接失败：{message}")

        self._workers.start(work, on_result=done, on_error=failed)

    def _guest(self) -> None:
        self.guest = True
        self.session = ""
        self.username = ""
        self.accept()

    def _error(self, message: str) -> None:
        self.status.setStyleSheet("color:#ff8fa8;")
        self.status.setText(message)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._workers.stop()
        super().closeEvent(event)
