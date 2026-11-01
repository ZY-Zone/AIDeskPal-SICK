"""First-run setup wizard: account, AI connection and a short readiness check."""

from __future__ import annotations

import copy
import logging
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from aideskpal import APP_NAME, __version__
from aideskpal.ai.client import LLMClient
from aideskpal.config import AppConfig
from aideskpal.market.client import MarketClient, MarketError, normalize_market_url
from aideskpal.paths import AppPaths
from aideskpal.ui.theme import app_icon, settings_stylesheet
from aideskpal.ui.workers import WorkerPool

logger = logging.getLogger(__name__)

DEFAULT_MARKET = "http://sickcc.online/cwusr"
DEFAULT_AI_BASE = "https://api.deepseek.com/v1"
DEFAULT_AI_MODEL = "deepseek-chat"


def _text(value: str, name: str) -> QLabel:
    label = QLabel(value)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


class OnboardingDialog(QDialog):
    """A small, resumable setup flow that never requires a network connection."""

    def __init__(self, config: AppConfig, paths: AppPaths, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = copy.deepcopy(config)
        self.paths = paths
        self._workers = WorkerPool(self)
        self._busy = False
        self._step = 0
        self._market_session = self.config.market.session_cookie
        try:
            self._pending_base = normalize_market_url(
                self.config.market.base_url or DEFAULT_MARKET
            )
        except MarketError:
            self._pending_base = DEFAULT_MARKET
        self._market_client = MarketClient(self._pending_base, self._market_session)
        self._account_ready = bool(
            self.config.market.username and self.config.market.session_cookie
        )
        self._guest = not self._account_ready
        self._saved_key = bool(self.config.ai.api_key)

        self.setWindowTitle(f"{APP_NAME} · 初次设置")
        self.setWindowIcon(app_icon(128))
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setModal(True)
        self.setMinimumSize(900, 620)
        self.resize(1000, 690)
        self.setStyleSheet(
            settings_stylesheet()
            + """
            QFrame#OnboardingSide {
                background: #0f0d18;
                border: 1px solid #332d4a;
                border-radius: 16px;
            }
            QLabel#OnboardingStep {
                color: #746c8e;
                font-size: 12px;
                padding: 9px 10px;
                border-radius: 8px;
            }
            QLabel#OnboardingStep[active="true"] {
                color: #f3efff;
                background: #2a2342;
            }
            QLabel#OnboardingStep[complete="true"] { color: #b9a7ff; }
            QLabel#PageTitle {
                font-size: 25px;
                font-weight: 700;
                color: #f3efff;
            }
            QLabel#PageLead { color: #c5bdd8; font-size: 13px; }
            QLabel#SummaryKey { color: #a9a3c2; font-size: 11px; }
            QLabel#SummaryValue { color: #f3efff; font-size: 14px; font-weight: 600; }
            QLabel#StatusOk { color: #a6e3a1; }
            QLabel#StatusBad { color: #ff8fa8; }
            QPushButton#Primary:disabled {
                background: #29233e;
                color: #6f6885;
            }
            """
        )
        self._build()

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 18)
        root.setSpacing(20)

        side = QFrame()
        side.setObjectName("OnboardingSide")
        side.setFixedWidth(226)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(20, 22, 20, 18)
        icon = QLabel()
        icon.setPixmap(app_icon(128).pixmap(54, 54))
        side_layout.addWidget(icon)
        title = QLabel("桌面伙伴\n初次设置")
        title.setObjectName("Title")
        side_layout.addWidget(title)
        side_layout.addWidget(_text("两步完成 AI 初始化，之后可在托盘设置中随时修改。", "Hint"))
        side_layout.addSpacing(18)

        steps = [
            ("AI 大脑", "API Key 与接口地址"),
            ("完成", "检查并进入桌面"),
        ]
        self.step_labels: list[QLabel] = []
        for index, (name, detail) in enumerate(steps):
            label = QLabel(f"{index + 1:02d}  {name}\n     {detail}")
            label.setObjectName("OnboardingStep")
            label.setWordWrap(True)
            label.setProperty("active", "false")
            label.setProperty("complete", "false")
            side_layout.addWidget(label)
            self.step_labels.append(label)
        side_layout.addStretch(1)
        side_layout.addWidget(_text(f"AIDeskPal-SICK {__version__}\n数据只保存在本机", "Hint"))
        root.addWidget(side)

        content = QVBoxLayout()
        content.setSpacing(12)
        self.stack = QStackedWidget()
        self.ai_page = self._build_ai_page()
        self.ready_page = self._build_ready_page()
        self.stack.addWidget(self.ai_page)
        self.stack.addWidget(self.ready_page)
        content.addWidget(self.stack, 1)

        footer = QHBoxLayout()
        self.skip_button = QPushButton("以后再说")
        self.skip_button.setObjectName("Ghost")
        self.skip_button.clicked.connect(self._skip)
        self.back_button = QPushButton("上一步")
        self.back_button.clicked.connect(self._back)
        self.next_button = QPushButton("下一步")
        self.next_button.setObjectName("Primary")
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self._next)
        footer.addWidget(self.skip_button)
        footer.addStretch(1)
        footer.addWidget(self.back_button)
        footer.addWidget(self.next_button)
        content.addLayout(footer)
        root.addLayout(content, 1)

        self._update_step()
        self._sync_account_state()

    def _page_header(self, title: str, lead: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(5)
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        lead_label = QLabel(lead)
        lead_label.setObjectName("PageLead")
        lead_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(lead_label)
        return layout

    def _build_account_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(14)
        layout.addLayout(
            self._page_header(
                "先登录，或者直接以游客开始",
                "登录后可以从资源市场下载模型/动作/插件，并把账号保存到本机。"
                "游客模式不联网，所有本地功能都可使用。",
            )
        )

        group = QGroupBox("账号")
        form = QFormLayout(group)
        form.setContentsMargins(16, 20, 16, 14)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.market_url_edit = QLineEdit(self.config.market.base_url or DEFAULT_MARKET)
        self.market_url_edit.setPlaceholderText("sickcc.online/cwusr")
        form.addRow("市场接口", self.market_url_edit)
        form.addRow(
            _text(
                "这是桌面端使用的接口，不是网页。可以省略 http://，程序会自动补全。",
                "Hint",
            )
        )
        self.auth_mode = QComboBox()
        self.auth_mode.addItems(["登录已有账号", "注册新账号"])
        self.auth_mode.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("方式", self.auth_mode)
        self.username_edit = QLineEdit(self.config.market.username)
        self.username_edit.setPlaceholderText("用户名（3-32 位）")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("密码（至少 8 位）")
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("邮箱（注册时可选）")
        form.addRow("用户名", self.username_edit)
        form.addRow("密码", self.password_edit)
        form.addRow("邮箱", self.email_edit)

        auth_buttons = QHBoxLayout()
        self.auth_button = QPushButton("登录")
        self.auth_button.setObjectName("Primary")
        self.auth_button.clicked.connect(self._account_action)
        self.guest_button = QPushButton("游客登录，跳过账号")
        self.guest_button.setObjectName("Ghost")
        self.guest_button.clicked.connect(self._guest_login)
        auth_buttons.addWidget(self.auth_button)
        auth_buttons.addWidget(self.guest_button)
        auth_buttons.addStretch(1)
        form.addRow(auth_buttons)
        self.account_status = _text("", "Hint")
        form.addRow(self.account_status)
        layout.addWidget(group)
        layout.addStretch(1)
        if self._account_ready:
            self.account_status.setText(f"已保存账号：{self.config.market.username}")
            self.account_status.setObjectName("StatusOk")
        elif self.config.market.username and not self.config.market.session_cookie:
            self.account_status.setText("账号信息不完整，请重新登录。")
        return page

    def _build_ai_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(14)
        layout.addLayout(
            self._page_header(
                "给桌宠接上大脑",
                "填写任意 OpenAI 兼容接口即可。没有 Key 也能继续，届时使用本地离线人格。"
            )
        )
        group = QGroupBox("AI 接口")
        form = QFormLayout(group)
        form.setContentsMargins(16, 20, 16, 14)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.ai_base_edit = QLineEdit(self.config.ai.base_url or DEFAULT_AI_BASE)
        self.ai_base_edit.setPlaceholderText(DEFAULT_AI_BASE)
        self.ai_model_edit = QLineEdit(self.config.ai.model or DEFAULT_AI_MODEL)
        self.ai_model_edit.setPlaceholderText(DEFAULT_AI_MODEL)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText(
            "已保存的 Key，留空保持不变" if self._saved_key else "sk-..."
        )
        form.addRow("Base URL", self.ai_base_edit)
        form.addRow("模型名", self.ai_model_edit)
        form.addRow("API Key", self.api_key_edit)
        key_row = QHBoxLayout()
        self.test_ai_button = QPushButton("测试连接")
        self.test_ai_button.clicked.connect(self._test_ai)
        help_button = QPushButton("获取 DeepSeek Key")
        help_button.setObjectName("Ghost")
        help_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://platform.deepseek.com/api_keys"))
        )
        key_row.addWidget(self.test_ai_button)
        key_row.addWidget(help_button)
        key_row.addStretch(1)
        form.addRow(key_row)
        self.ai_status = _text("", "Hint")
        form.addRow(self.ai_status)
        form.addRow(
            _text(
                "API Key 使用 Windows DPAPI 加密，只保存给当前 Windows 用户；"
                "不会写入 settings.json。",
                "Hint",
            )
        )
        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _build_ready_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(14)
        layout.addLayout(
            self._page_header("准备好了", "确认下面的选择，进入桌面后可以随时在托盘设置中修改。")
        )
        group = QGroupBox("本次初始化")
        form = QFormLayout(group)
        form.setContentsMargins(16, 20, 16, 14)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        self.summary_account = QLabel("")
        self.summary_account.setObjectName("SummaryValue")
        self.summary_ai = QLabel("")
        self.summary_ai.setObjectName("SummaryValue")
        self.summary_ai.setWordWrap(True)
        self.summary_model = QLabel("")
        self.summary_model.setObjectName("SummaryValue")
        self.summary_model.setWordWrap(True)
        self.summary_data = QLabel(str(self.paths.data))
        self.summary_data.setObjectName("Hint")
        self.summary_data.setWordWrap(True)
        form.addRow("账号", self.summary_account)
        form.addRow("AI", self.summary_ai)
        form.addRow("模型", self.summary_model)
        form.addRow("数据目录", self.summary_data)
        layout.addWidget(group)
        layout.addWidget(
            _text(
                "提示：如果暂时不登录，游客模式仍可使用本地模型、动作、拖拽、气泡和插件。"
                "之后在托盘右键 →「重新运行初始化向导」可再次配置。",
                "Hint",
            )
        )
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------ navigation
    def _sync_account_state(self) -> None:
        self.next_button.setEnabled(not self._busy)

    def _on_mode_changed(self, index: int) -> None:
        if index == 0:
            self.auth_button.setText("登录")
            self.email_edit.setPlaceholderText("邮箱（登录不需要）")
        else:
            self.auth_button.setText("注册并登录")
            self.email_edit.setPlaceholderText("邮箱（注册时可选）")

    def _update_step(self) -> None:
        for index, label in enumerate(self.step_labels):
            label.setProperty("active", "true" if index == self._step else "false")
            label.setProperty("complete", "true" if index < self._step else "false")
            label.style().unpolish(label)
            label.style().polish(label)
        self.stack.setCurrentIndex(self._step)
        self.back_button.setVisible(self._step > 0)
        if self._step == 0:
            self.next_button.setText("保存并继续")
        else:
            self.next_button.setText("进入桌面")
        self._sync_account_state()

    def _go_to(self, step: int) -> None:
        self._step = max(0, min(1, step))
        self._update_step()
        if self._step == 1:
            self._refresh_summary()

    def _back(self) -> None:
        if self._step > 0:
            self._go_to(self._step - 1)

    def _next(self) -> None:
        if self._step == 0:
            if self._commit_ai():
                self._go_to(1)
        else:
            self._finish()

    def _finish(self) -> None:
        self.config.first_run = False
        self._workers.stop()
        self.accept()

    def _skip(self) -> None:
        self.config.first_run = False
        self._workers.stop()
        self.reject()

    # ------------------------------------------------------------------ account
    def _set_account_busy(self, busy: bool) -> None:
        self._busy = busy
        for widget in (
            self.market_url_edit,
            self.auth_mode,
            self.username_edit,
            self.password_edit,
            self.email_edit,
            self.auth_button,
            self.guest_button,
        ):
            widget.setEnabled(not busy)
        self._sync_account_state()

    def _account_action(self) -> None:
        if self._busy:
            return
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        mode = self.auth_mode.currentIndex()
        if len(username) < 3:
            self._account_status("用户名至少 3 位。", error=True)
            return
        if len(password) < (8 if mode == 1 else 1):
            self._account_status("注册密码至少 8 位。" if mode == 1 else "请输入密码。", error=True)
            return
        try:
            base = normalize_market_url(self.market_url_edit.text())
        except MarketError as exc:
            self._account_status(str(exc), error=True)
            return
        client = MarketClient(base, self._market_session)
        email = self.email_edit.text().strip()
        self._pending_base = base
        self._set_account_busy(True)
        self._account_status("正在连接资源市场…")

        def work() -> dict[str, Any]:
            if mode == 1:
                return client.register(username, password, email)
            return client.login(username, password)

        def done(data: dict[str, Any]) -> None:
            self._set_account_busy(False)
            self._market_client = client
            self._market_session = client.session_cookie
            self.config.market.base_url = base
            self.config.market.username = username
            self.config.market.session_cookie = self._market_session
            self._account_ready = True
            self._guest = False
            self._account_status(f"登录成功：{username}")
            self._sync_account_state()

        def failed(message: str) -> None:
            self._set_account_busy(False)
            self._account_status(f"连接失败：{message}", error=True)

        self._workers.start(work, on_result=done, on_error=failed)

    def _guest_login(self) -> None:
        if self._busy:
            return
        try:
            base = normalize_market_url(self.market_url_edit.text())
        except MarketError:
            base = DEFAULT_MARKET
        self.config.market.base_url = base
        self.config.market.username = ""
        self.config.market.session_cookie = ""
        self._market_session = ""
        self._market_client = MarketClient(base, "")
        self._pending_base = base
        self._account_ready = True
        self._guest = True
        self._account_status("游客模式：不登录，继续使用本地功能。")
        self._go_to(1)

    def _account_status(self, text: str, *, error: bool = False) -> None:
        self.account_status.setText(text)
        self.account_status.setObjectName("StatusBad" if error else "StatusOk")
        self.account_status.style().unpolish(self.account_status)
        self.account_status.style().polish(self.account_status)

    # ------------------------------------------------------------------ AI
    def _collect_ai(self) -> bool:
        base = self.ai_base_edit.text().strip() or DEFAULT_AI_BASE
        if not (base.startswith("http://") or base.startswith("https://")):
            self._ai_status("Base URL 必须以 http:// 或 https:// 开头。", error=True)
            return False
        model = self.ai_model_edit.text().strip() or DEFAULT_AI_MODEL
        key = self.api_key_edit.text().strip()
        self.config.ai.base_url = base.rstrip("/")
        self.config.ai.model = model
        self.config.ai.enabled = True
        if key:
            self.config.ai.api_key = key
            self._saved_key = True
        if not self.config.ai.api_key:
            self.config.ai.offline_fallback = True
        return True

    def _test_ai(self) -> None:
        if self._busy:
            return
        base = self.ai_base_edit.text().strip() or DEFAULT_AI_BASE
        model = self.ai_model_edit.text().strip() or DEFAULT_AI_MODEL
        key = self.api_key_edit.text().strip() or self.config.ai.api_key
        if not key:
            self._ai_status("请先填写 API Key。", error=True)
            return
        if not (base.startswith("http://") or base.startswith("https://")):
            self._ai_status("Base URL 必须以 http:// 或 https:// 开头。", error=True)
            return
        probe = copy.deepcopy(self.config)
        probe.ai.base_url = base.rstrip("/")
        probe.ai.model = model
        probe.ai.api_key = key
        probe.ai.enabled = True
        self._busy = True
        self.test_ai_button.setEnabled(False)
        self._ai_status("正在连接 AI 接口…")

        def work() -> str:
            return LLMClient(probe.ai).ping()

        def done(reply: str) -> None:
            self._busy = False
            self.test_ai_button.setEnabled(True)
            self._ai_status(f"连接成功：{reply[:70]}")

        def failed(message: str) -> None:
            self._busy = False
            self.test_ai_button.setEnabled(True)
            self._ai_status(f"连接失败：{message}", error=True)

        self._workers.start(work, on_result=done, on_error=failed)

    def _commit_ai(self) -> bool:
        if self._busy:
            return False
        if not self._collect_ai():
            return False
        return True

    def _ai_status(self, text: str, *, error: bool = False) -> None:
        self.ai_status.setText(text)
        self.ai_status.setObjectName("StatusBad" if error else "StatusOk")
        self.ai_status.style().unpolish(self.ai_status)
        self.ai_status.style().polish(self.ai_status)

    # ------------------------------------------------------------------ summary
    def _refresh_summary(self) -> None:
        if self._guest or not self.config.market.username:
            self.summary_account.setText("游客模式（不登录）")
        else:
            self.summary_account.setText(f"{self.config.market.username} · 已保存登录")
        if self.config.ai.api_key:
            self.summary_ai.setText(
                f"{self.config.ai.model} · {self.config.ai.base_url}\nAPI Key 已配置"
            )
        else:
            self.summary_ai.setText("离线人格 · 未配置 API Key\n之后可在设置里添加")
        model_name = self.config.model.name or (
            self.config.model.pmx_path.rsplit("\\", 1)[-1] if self.config.model.pmx_path else "未选择"
        )
        self.summary_model.setText(model_name)
        self.summary_data.setText(str(self.paths.data))

    # ------------------------------------------------------------------ lifecycle
    def closeEvent(self, event) -> None:  # noqa: N802
        self._workers.stop()
        super().closeEvent(event)
