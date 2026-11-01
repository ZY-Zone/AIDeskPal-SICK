"""First-run market chooser.

The chooser is deliberately separate from Settings: a new user should pick a
self-contained model/action pack before the desktop pet is created.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
)

from aideskpal import APP_NAME
from aideskpal.config import AppConfig
from aideskpal.market.client import MarketClient
from aideskpal.market.installer import BundleInstaller, InstallError
from aideskpal.paths import AppPaths
from aideskpal.ui.theme import app_icon, settings_stylesheet
from aideskpal.ui.workers import WorkerPool

logger = logging.getLogger(__name__)


def _failure_hint(message: str) -> str:
    if any(token in message for token in ("请先登录", "登录已过期", "401")):
        return "市场服务端仍是旧版本，尚未开放游客访问；请部署最新 server/ 并重启服务。"
    return message



class MarketStartDialog(QDialog):
    def __init__(
        self,
        config: AppConfig,
        paths: AppPaths,
        installer: BundleInstaller,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.paths = paths
        self.installer = installer
        self._workers = WorkerPool(self)
        self._selected: dict[str, Any] | None = None
        self._busy = False

        self.setWindowTitle(f"{APP_NAME} · 选择第一位伙伴")
        self.setWindowIcon(app_icon(128))
        self.setModal(True)
        self.setMinimumSize(860, 560)
        self.setStyleSheet(settings_stylesheet())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(12)
        title = QLabel("选择一位伙伴开始")
        title.setObjectName("Title")
        outer.addWidget(title)
        lead = QLabel(
            "从示例角色、已安装角色或资源市场中选择一个模型与动作套装。\n"
            "选定后会直接进入桌面；以后可以在设置里更换。"
        )
        lead.setObjectName("Subtitle")
        lead.setWordWrap(True)
        outer.addWidget(lead)
        self.status = QLabel("正在准备可选资源…")
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._show_details)
        self.details = QTextBrowser()
        splitter.addWidget(self.list)
        splitter.addWidget(self.details)
        splitter.setSizes([330, 470])
        outer.addWidget(splitter, 1)

        footer = QHBoxLayout()
        skip = QPushButton("稍后再说")
        skip.setObjectName("Ghost")
        skip.clicked.connect(self.reject)
        self.choose = QPushButton("开始使用")
        self.choose.setObjectName("Primary")
        self.choose.setEnabled(False)
        self.choose.clicked.connect(self._choose)
        footer.addWidget(skip)
        footer.addStretch(1)
        footer.addWidget(self.choose)
        outer.addLayout(footer)

        self._add_sample()
        self._add_installed()
        self._load_market()

    def _add(self, data: dict[str, Any], label: str) -> None:
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, data)
        self.list.addItem(item)

    def _add_sample(self) -> None:
        model = self.paths.root / "sample_content" / "starling" / "model.pmx"
        if model.is_file():
            self._add(
                {
                    "kind": "sample",
                    "name": "星灵·露米",
                    "version": "示例",
                    "model_id": "starling",
                    "pmx_path": str(model),
                    "summary": "内置示例角色，包含一套可直接使用的动作。",
                },
                "星灵·露米 · 内置示例\n本地 · 无需登录",
            )

    def _add_installed(self) -> None:
        for item in self.installer.list_installed():
            if not Path(str(item.get("pmx_path", ""))).is_file():
                continue
            self._add(
                {
                    "kind": "installed",
                    "name": str(item.get("name") or item.get("model_id")),
                    "version": str(item.get("version") or ""),
                    "model_id": str(item.get("model_id") or ""),
                    "pmx_path": str(item.get("pmx_path") or ""),
                    "summary": str(item.get("description") or "已安装的模型与动作套装。"),
                },
                f"{item.get('name') or item.get('model_id')} · v{item.get('version', '?')}\n本地 · 已安装",
            )

    def _load_market(self) -> None:
        self.status.setText("正在获取市场目录…")
        client = MarketClient(self._market_base(), self.config.market.session_cookie)

        def done(items) -> None:
            for item in items:
                self._add(
                    {
                        "kind": "market",
                        "name": str(item.get("title") or item.get("name") or "未命名"),
                        "version": str(item.get("version") or ""),
                        "summary": str(item.get("summary") or item.get("description") or ""),
                        "resource_id": int(item["id"]),
                    },
                    f"{item.get('title') or '未命名'} · v{item.get('version', '?')}\n市场 · 无需登录即可下载",
                )
            if self.list.count() == 0:
                self.status.setText("市场暂时没有可用资源。")
            else:
                scope = "已登录" if self.config.market.session_cookie else "游客模式"
                self.status.setText(f"{scope}：已加载 {self.list.count()} 个可选资源。")
                self.list.setCurrentRow(0)

        def failed(message: str) -> None:
            self.status.setText(f"市场目录加载失败：{_failure_hint(message)}")

        self._workers.start(client.bundles, on_result=done, on_error=failed)

    def _market_base(self) -> str:
        return (self.config.market.base_url or "http://sickcc.online/cwusr").rstrip("/")

    def _show_details(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None:
            self.choose.setEnabled(False)
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        self._selected = data
        self.choose.setEnabled(True)
        self.details.setHtml(
            f"<h2>{data.get('name', '')}</h2>"
            f"<p style='color:#a9a3c2'>v{data.get('version', '?')}</p>"
            f"<p>{data.get('summary', '')}</p>"
            "<p style='color:#a9a3c2'>套装内的动作会随角色一起加载。</p>"
        )

    def _choose(self) -> None:
        data = self._selected
        if not data or self._busy:
            return
        if data.get("kind") in {"sample", "installed"}:
            self._apply(
                str(data.get("pmx_path", "")),
                str(data.get("model_id", "")),
                str(data.get("name", "")),
            )
            self.accept()
            return
        self._busy = True
        self.choose.setEnabled(False)
        self.status.setText("正在下载并安装…")
        client = MarketClient(self._market_base(), self.config.market.session_cookie)
        resource_id = int(data.get("resource_id", 0))

        def work():
            archive = client.download("bundle", resource_id)
            return self.installer.install_bundle(archive)

        def done(installed) -> None:
            self._apply(str(installed.pmx_path), installed.model_id, installed.name)
            self._busy = False
            self.accept()

        def failed(message: str) -> None:
            self._busy = False
            self.choose.setEnabled(True)
            self.status.setText(f"安装失败：{_failure_hint(message)}")

        self._workers.start(work, on_result=done, on_error=failed)

    def _apply(self, pmx_path: str, model_id: str, name: str) -> None:
        self.config.model.pmx_path = pmx_path
        self.config.model.id = model_id
        self.config.model.actions_model_id = model_id
        self.config.model.name = name
        self.config.last_action_id = ""

    def closeEvent(self, event) -> None:  # noqa: N802
        self._workers.stop()
        super().closeEvent(event)
