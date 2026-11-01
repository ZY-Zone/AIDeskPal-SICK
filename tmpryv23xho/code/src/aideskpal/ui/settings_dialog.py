"""Tabbed settings window, including AI, privacy, market and plugin management."""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QTime, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from aideskpal import APP_NAME
from aideskpal.ai.character import CharacterError
from aideskpal.ai.client import LLMClient
from aideskpal.config import DEFAULT_PERSONALITY, AppConfig
from aideskpal.market.client import MarketClient
from aideskpal.market.installer import BundleInstaller, InstallError, InstalledBundle
from aideskpal.ui.theme import app_icon, app_font, settings_stylesheet
from aideskpal.ui.hotkey import DEFAULT_SEQUENCE as DEFAULT_HIDE_HOTKEY
from aideskpal.ui.hotkey import parse_sequence
from aideskpal.ui.pet_window import (
    HIDE_TRIGGER_DOUBLE_CLICK,
    HIDE_TRIGGER_HOTKEY,
    HIDE_TRIGGER_OFF,
    HIDE_TRIGGER_RIGHT_DOUBLE_CLICK,
)
from aideskpal.ui.workers import WorkerPool

logger = logging.getLogger(__name__)


def _market_failure_hint(message: str) -> str:
    """Turn the old server's auth error into an actionable deployment hint."""
    if any(token in message for token in ("请先登录", "登录已过期", "401")):
        return (
            "市场服务端仍是旧版本，尚未开放游客访问。"
            "请部署最新 server/ 并重启市场服务后再试。"
        )
    return message



def _version_key(text: str) -> tuple[int, ...]:
    parts = []
    for chunk in str(text).replace("-", ".").replace("_", ".").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Hint")
    label.setWordWrap(True)
    return label


def _group(title: str) -> tuple[QGroupBox, QFormLayout]:
    group = QGroupBox(title)
    form = QFormLayout(group)
    form.setContentsMargins(14, 18, 14, 12)
    form.setHorizontalSpacing(18)
    form.setVerticalSpacing(10)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return group, form


def _scroll_tab() -> tuple[QWidget, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(14)
    scroll.setWidget(content)
    wrapper = QWidget()
    wrapper_layout = QVBoxLayout(wrapper)
    wrapper_layout.setContentsMargins(0, 0, 0, 0)
    wrapper_layout.addWidget(scroll)
    return wrapper, layout


class SettingsDialog(QDialog):
    saved = Signal(object)

    def __init__(self, app) -> None:
        super().__init__(None)
        self.app = app
        self.config: AppConfig = copy.deepcopy(app.config)
        self.store = app.store
        self.actions = app.actions
        self._model_path = self.config.model.pmx_path
        self._pending_character: Path | None = None
        self._market_session = self.config.market.session_cookie
        self._original_scale = float(self.config.window.pet_scale)
        self._market_client = MarketClient(
            self.config.market.base_url, self._market_session
        )
        self._market_items: dict[str, list[dict[str, Any]]] = {"bundle": [], "plugin": []}
        self._market_page: dict[str, int] = {"bundle": 0, "plugin": 0}
        self._market_query = ""
        self._market_loaded = False
        self._plugin_enabled = set(self.config.plugins.enabled)
        self._plugin_enabled.difference_update(self.config.plugins.disabled)
        self._workers = WorkerPool(self)
        self._busy = False
        self._preview_timer: QTimer | None = None
        self._saved = False

        self.setWindowTitle(f"{APP_NAME} · 设置")
        self.setWindowIcon(app_icon(128))
        self.setStyleSheet(settings_stylesheet())
        self.setMinimumSize(900, 660)
        self.resize(1020, 760)
        self.setWindowModality(Qt.WindowModality.NonModal)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 16)
        outer.setSpacing(12)
        outer.addLayout(self._build_header())
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_model_tab(), "角色与动作")
        self.tabs.addTab(self._build_ai_tab(), "AI 大脑")
        self.tabs.addTab(self._build_privacy_tab(), "感知与隐私")
        self.tabs.addTab(self._build_market_tab(), "市场")
        self.tabs.addTab(self._build_plugin_tab(), "插件")
        self.tabs.addTab(self._build_about_tab(), "外观与关于")
        outer.addWidget(self.tabs, 1)
        outer.addLayout(self._build_footer())
        self._refresh_model_summary()
        self._refresh_preview()
        self._refresh_market_links()
        self.tabs.currentChanged.connect(self._on_main_tab_changed)

    # ------------------------------------------------------------------ chrome
    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(app_icon(64).pixmap(48, 48))
        icon.setFixedSize(52, 52)
        row.addWidget(icon)
        text = QVBoxLayout()
        title = QLabel("桌宠控制台")
        title.setObjectName("Title")
        subtitle = QLabel("桌宠的行为、记忆与本地资源 · 所有设置只保存在本机")
        subtitle.setObjectName("Subtitle")
        text.addWidget(title)
        text.addWidget(subtitle)
        row.addLayout(text, 1)
        badge = QLabel("AIDeskPal-SICK")
        badge.setObjectName("Accent")
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存并应用")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(save)
        return row

    # ------------------------------------------------------------------ model
    def _build_model_tab(self) -> QWidget:
        tab, layout = _scroll_tab()
        info_group, info_form = _group("当前模型")
        self.model_summary = QLabel()
        self.model_summary.setWordWrap(True)
        info_form.addRow(self.model_summary)
        path_row = QHBoxLayout()
        self.model_path_edit = QLineEdit(self._model_path)
        self.model_path_edit.setReadOnly(True)
        browse = QPushButton("选择 PMX…")
        browse.clicked.connect(self._browse_pmx)
        path_row.addWidget(self.model_path_edit, 1)
        path_row.addWidget(browse)
        info_form.addRow("模型文件", path_row)
        self.action_model_edit = QLineEdit(self.config.model.actions_model_id or self.config.model.id)
        self.action_model_edit.setPlaceholderText("动作包使用的模型 ID")
        info_form.addRow("动作包模型 ID", self.action_model_edit)
        info_form.addRow(
            _hint("动作 JSON 的 model 字段必须与这个 ID 一致。更换模型后请选择配套动作包。")
        )
        layout.addWidget(info_group)

        installed_group, installed_layout = _group("已安装的模型/动作套装")
        self.installed_list = QListWidget()
        self.installed_list.setMaximumHeight(130)
        installed_layout.addRow(self.installed_list)
        use_row = QHBoxLayout()
        use_bundle = QPushButton("使用选中的套装")
        use_bundle.clicked.connect(self._use_installed_bundle)
        open_bundles = QPushButton("打开安装目录")
        open_bundles.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.app.paths.character_root)))
        )
        use_row.addWidget(use_bundle)
        use_row.addWidget(open_bundles)
        use_row.addStretch(1)
        installed_layout.addRow(use_row)
        layout.addWidget(installed_group)
        self._reload_installed_list()

        actions_group = QGroupBox("动作库")
        actions_layout = QVBoxLayout(actions_group)
        actions_layout.setContentsMargins(12, 18, 12, 12)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.action_list = QListWidget()
        self.action_list.setMinimumWidth(230)
        self.action_list.currentItemChanged.connect(self._show_action_details)
        splitter.addWidget(self.action_list)
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(10, 0, 0, 0)
        self.action_details = QTextBrowser()
        self.action_details.setOpenExternalLinks(False)
        details_layout.addWidget(self.action_details, 1)
        buttons = QHBoxLayout()
        self.preview_button = QPushButton("预览动作")
        self.preview_button.clicked.connect(self._preview_action)
        self.idle_button = QPushButton("设为待机")
        self.idle_button.clicked.connect(self._set_idle_action)
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.idle_button)
        buttons.addStretch(1)
        details_layout.addLayout(buttons)
        splitter.addWidget(details_widget)
        splitter.setSizes([280, 500])
        actions_layout.addWidget(splitter, 1)
        actions_group.setMinimumHeight(280)
        layout.addWidget(actions_group, 1)
        self._reload_action_list()

        window_group, window_form = _group("窗口与显示")
        size_row = QHBoxLayout()
        self.width_spin = QSpinBox()
        self.width_spin.setRange(260, 1200)
        self.width_spin.setValue(self.config.window.width)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(420, 1600)
        self.height_spin.setValue(self.config.window.height)
        self.size_combo = QComboBox()
        self.size_combo.addItems(["自定义", "小（320×520）", "中（380×620）", "大（440×720）"])
        self.size_combo.currentIndexChanged.connect(self._size_preset)
        size_row.addWidget(QLabel("宽"))
        size_row.addWidget(self.width_spin)
        size_row.addWidget(QLabel("高"))
        size_row.addWidget(self.height_spin)
        size_row.addWidget(self.size_combo)
        size_row.addStretch(1)
        window_form.addRow("基准尺寸", size_row)
        scale_row = QHBoxLayout()
        self.pet_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.pet_scale_slider.setRange(50, 150)
        self.pet_scale_slider.setSingleStep(5)
        self.pet_scale_slider.setPageStep(10)
        self.pet_scale_slider.setValue(int(round(self.config.window.pet_scale * 100)))
        self.pet_scale_value = QLabel(f"{self.pet_scale_slider.value()}%")
        self.pet_scale_value.setMinimumWidth(44)
        self.pet_scale_slider.valueChanged.connect(self._on_pet_scale_changed)
        reset_scale = QPushButton("100%")
        reset_scale.setToolTip("恢复 100% 缩放")
        reset_scale.clicked.connect(lambda: self.pet_scale_slider.setValue(100))
        scale_row.addWidget(self.pet_scale_slider, 1)
        scale_row.addWidget(self.pet_scale_value)
        scale_row.addWidget(reset_scale)
        window_form.addRow("缩放比例", scale_row)
        window_form.addRow(
            _hint("缩放会按基准尺寸等比放大或缩小窗口；滑动时可实时预览，保存后永久生效。")
        )
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(35, 100)
        self.opacity_slider.setValue(int(self.config.window.opacity * 100))
        self.opacity_value = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_slider.valueChanged.connect(
            lambda value: self.opacity_value.setText(f"{value}%")
        )
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value)
        window_form.addRow("不透明度", opacity_row)
        self.always_on_top = QCheckBox("始终置顶（在其他窗口上方）")
        self.always_on_top.setChecked(self.config.window.always_on_top)
        self.click_through = QCheckBox("透明像素鼠标穿透（只对角色区域可点击）")
        self.click_through.setChecked(self.config.window.click_through_transparent)
        self.hide_fullscreen = QCheckBox("全屏游戏/视频时自动隐藏")
        self.hide_fullscreen.setChecked(self.config.window.hide_when_fullscreen)
        self.edge_behaviors = QCheckBox("启用屏幕边缘行为（侧边扒屏、顶部悬挂、底部鸭子坐）")
        self.edge_behaviors.setChecked(self.config.window.edge_behaviors)
        window_form.addRow(self.always_on_top)
        window_form.addRow(self.click_through)
        window_form.addRow(self.hide_fullscreen)
        window_form.addRow(self.edge_behaviors)
        window_form.addRow(
            _hint(
                "边缘行为会每隔几分钟自动切换；把角色拖到超过一半移出屏幕后松手，"
                "会吸附到最近的边缘。顶部或侧边偶尔会失去平衡，摔到底部并坐下。"
            )
        )
        # How the pet is tucked into the notification area.
        self.hide_trigger = QComboBox()
        for label, value in (
            ("双击身体", HIDE_TRIGGER_DOUBLE_CLICK),
            ("右键双击", HIDE_TRIGGER_RIGHT_DOUBLE_CLICK),
            ("自定义快捷键", HIDE_TRIGGER_HOTKEY),
            ("不启用该功能", HIDE_TRIGGER_OFF),
        ):
            self.hide_trigger.addItem(label, value)
        current_trigger = str(self.config.window.hide_trigger or HIDE_TRIGGER_OFF)
        index = self.hide_trigger.findData(current_trigger)
        self.hide_trigger.setCurrentIndex(index if index >= 0 else 0)
        window_form.addRow("收起桌宠", self.hide_trigger)
        self.hide_hotkey_edit = QLineEdit(self.config.window.hide_hotkey or DEFAULT_HIDE_HOTKEY)
        self.hide_hotkey_edit.setPlaceholderText(DEFAULT_HIDE_HOTKEY)
        window_form.addRow("自定义快捷键", self.hide_hotkey_edit)
        hide_hint = _hint(
            "无论选哪一项，双击头部始终打开聊天输入框。收起后桌宠、气泡和输入框"
            "会一起从桌面消失，可从托盘图标恢复。快捷键形如 Ctrl+Alt+H。"
        )
        window_form.addRow(hide_hint)
        self.hide_trigger.currentIndexChanged.connect(self._sync_hide_hotkey_state)
        self._sync_hide_hotkey_state()

        layout.addWidget(window_group)
        layout.addStretch(1)
        return tab

    def _sync_hide_hotkey_state(self) -> None:
        """Only the custom-hotkey mode needs the sequence field to be editable."""
        uses_hotkey = self.hide_trigger.currentData() == HIDE_TRIGGER_HOTKEY
        self.hide_hotkey_edit.setEnabled(uses_hotkey)

    def _browse_pmx(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "选择 PMX 模型", str(Path(self._model_path).parent), "PMX 模型 (*.pmx)"
        )
        if not selected:
            return
        self._model_path = selected
        try:
            Path(selected).resolve().relative_to(self.app.paths.character_root.resolve())
            self._pending_character = None
        except ValueError:
            self._pending_character = Path(selected)
        self.model_path_edit.setText(selected)
        if not self.action_model_edit.text().strip():
            self.action_model_edit.setText(Path(selected).stem)
        self.model_summary.setText(
            f"<b>{Path(selected).stem}</b><br>"
            "<span style='color:#a9a3c2'>保存时会把模型、动作和角色设定复制到角色目录。</span>"
        )

    def _size_preset(self, index: int) -> None:
        presets = {1: (320, 520), 2: (380, 620), 3: (440, 720)}
        if index in presets:
            width, height = presets[index]
            self.width_spin.setValue(width)
            self.height_spin.setValue(height)

    def _on_pet_scale_changed(self, value: int) -> None:
        self.pet_scale_value.setText(f"{value}%")
        self.app.preview_pet_scale(value / 100.0)

    def _reload_installed_list(self) -> None:
        self.installed_list.clear()
        for item in self.app.installer.list_installed():
            label = (
                f"{item.get('name', item.get('model_id'))}  ·  "
                f"v{item.get('version', '?')}  ·  {item.get('model_id', '')}"
            )
            widget_item = QListWidgetItem(label)
            widget_item.setData(Qt.ItemDataRole.UserRole, item)
            self.installed_list.addItem(widget_item)
        if self.installed_list.count() == 0:
            placeholder = QListWidgetItem("还没有已安装的角色")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.installed_list.addItem(placeholder)

    def _use_installed_bundle(self) -> None:
        item = self.installed_list.currentItem()
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        installed = InstalledBundle(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            version=str(data.get("version", "")),
            path=Path(str(data.get("path", ""))),
            pmx_path=Path(str(data.get("pmx_path", ""))),
            actions_dir=Path(str(data.get("actions_dir", ""))),
            model_id=str(data.get("model_id", "")),
            description=str(data.get("description", "")),
        )
        if not installed.pmx_path.is_file():
            QMessageBox.warning(self, APP_NAME, "套装文件不完整，PMX 不存在。")
            return
        if not self.app.switch_to_installed_bundle(installed):
            QMessageBox.warning(self, APP_NAME, "模型切换失败，请查看日志。")
            return
        self.config = copy.deepcopy(self.app.config)
        self._model_path = self.config.model.pmx_path
        self.model_path_edit.setText(self._model_path)
        self.action_model_edit.setText(self.config.model.actions_model_id)
        self.actions = self.app.actions
        self._reload_action_list()
        self._refresh_model_summary()
        QMessageBox.information(self, APP_NAME, "已切换到选中的模型与动作套装。")

    def _reload_action_list(self) -> None:
        self.action_list.clear()
        for clip in sorted(self.actions.values(), key=lambda item: (item.category, item.name)):
            item = QListWidgetItem(f"{clip.name}   ·   {clip.id}")
            item.setData(Qt.ItemDataRole.UserRole, clip.id)
            self.action_list.addItem(item)
        if self.action_list.count():
            self.action_list.setCurrentRow(0)
        else:
            placeholder = QListWidgetItem("未找到动作；请导入配套动作包")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.action_list.addItem(placeholder)
            self.action_details.setHtml("<p style='color:#a9a3c2'>动作库为空。桌宠会保持静止。</p>")

    def _show_action_details(self, current: QListWidgetItem | None, previous=None) -> None:
        if current is None:
            return
        clip = self.actions.get(str(current.data(Qt.ItemDataRole.UserRole)))
        if clip is None:
            return
        tags = " ".join(f"#{tag}" for tag in clip.tags)
        self.action_details.setHtml(
            f"<h2>{clip.name}</h2>"
            f"<p style='color:#b9a7ff'>{clip.id} · {clip.category} · {clip.duration:.1f}s · "
            f"{'循环' if clip.loop else '单次'}</p>"
            f"<p>{clip.description}</p>"
            f"<p style='color:#a9a3c2'>{tags}</p>"
        )

    def _preview_action(self) -> None:
        item = self.action_list.currentItem()
        if not item:
            return
        action_id = item.data(Qt.ItemDataRole.UserRole)
        if action_id:
            self.app.preview_action(str(action_id))

    def _set_idle_action(self) -> None:
        item = self.action_list.currentItem()
        if not item:
            return
        action_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        clip = self.actions.get(action_id)
        if clip is None:
            return
        if not clip.loop:
            QMessageBox.information(self, APP_NAME, "只有循环动作可以设为待机。")
            return
        self.app.set_idle_action(action_id)
        self.config.last_action_id = action_id
        QMessageBox.information(self, APP_NAME, f"已把「{clip.name}」设为待机动作。")

    def _refresh_model_summary(self) -> None:
        model = self.app.model
        if model is None:
            self.model_summary.setText("尚未加载模型")
            return
        self._model_path = self.config.model.pmx_path
        self.model_path_edit.setText(self._model_path)
        self.model_summary.setText(f"<b>{model.name}</b><br><span style='color:#a9a3c2'>当前模型已加载</span>")

    # ------------------------------------------------------------------ AI
    def _build_ai_tab(self) -> QWidget:
        tab, layout = _scroll_tab()
        api_group, api_form = _group("模型服务（OpenAI 兼容）")
        self.ai_enabled = QCheckBox("启用 AI 大脑（关闭后使用本地离线人格）")
        self.ai_enabled.setChecked(self.config.ai.enabled)
        api_form.addRow(self.ai_enabled)
        self.base_url_edit = QLineEdit(self.config.ai.base_url)
        self.base_url_edit.setPlaceholderText("https://api.deepseek.com/v1")
        api_form.addRow("Base URL", self.base_url_edit)
        self.planner_model_edit = QLineEdit(self.config.ai.model_for("planner"))
        self.planner_model_edit.setPlaceholderText("主控体验模型，例如 deepseek-chat")
        api_form.addRow("Planner 模型", self.planner_model_edit)
        self.replier_model_edit = QLineEdit(self.config.ai.model_for("replier"))
        self.replier_model_edit.setPlaceholderText("最终台词模型；可与 Planner 不同")
        api_form.addRow("Replier 模型", self.replier_model_edit)
        self.actor_model_edit = QLineEdit(self.config.ai.model_for("actor"))
        self.actor_model_edit.setPlaceholderText("动作决策模型；可用更快的小模型")
        api_form.addRow("Actor 模型", self.actor_model_edit)
        api_form.addRow(_hint("三者使用独立的模型客户端与提示词；当前共用上方接口和 API Key。"))
        key_row = QHBoxLayout()
        self.api_key_edit = QLineEdit(self.config.ai.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("sk-...（用 Windows DPAPI 加密保存）")
        reveal = QPushButton("显示")
        reveal.setCheckable(True)
        reveal.toggled.connect(
            lambda checked: self.api_key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        self.test_ai_button = QPushButton("测试连接")
        self.test_ai_button.clicked.connect(self._test_ai)
        key_row.addWidget(self.api_key_edit, 1)
        key_row.addWidget(reveal)
        key_row.addWidget(self.test_ai_button)
        api_form.addRow("API Key", key_row)
        self.ai_status = _hint(
            "AI 不可用时自动使用本地离线人格。上下文会发送给你配置的服务商，请阅读其隐私政策。"
        )
        api_form.addRow(self.ai_status)
        layout.addWidget(api_group)

        behavior_group, behavior_form = _group("行为策略")
        self.speech_enabled = QCheckBox("允许气泡说话")
        self.speech_enabled.setChecked(self.config.ai.speech_enabled)
        self.proactive_enabled = QCheckBox("允许主动发起互动")
        self.proactive_enabled.setChecked(self.config.ai.proactive)
        self.offline_fallback_enabled = QCheckBox("没有 API Key 或请求失败时使用离线人格")
        self.offline_fallback_enabled.setChecked(self.config.ai.offline_fallback)
        behavior_form.addRow(self.speech_enabled)
        behavior_form.addRow(self.proactive_enabled)
        behavior_form.addRow(self.offline_fallback_enabled)
        self.autonomy_slider, self.autonomy_label = self._slider_row(
            behavior_form, "主动性", int(self.config.ai.autonomy * 100), 0, 100
        )
        self.temperature_slider, self.temperature_label = self._slider_row(
            behavior_form, "表达温度", int(self.config.ai.temperature * 100), 0, 150
        )
        ticks = QHBoxLayout()
        self.tick_spin = QSpinBox()
        self.tick_spin.setRange(30, 1800)
        self.tick_spin.setSuffix(" 秒")
        self.tick_spin.setValue(int(self.config.ai.tick_seconds))
        self.idle_tick_spin = QSpinBox()
        self.idle_tick_spin.setRange(60, 3600)
        self.idle_tick_spin.setSuffix(" 秒")
        self.idle_tick_spin.setValue(int(self.config.ai.idle_tick_seconds))
        ticks.addWidget(QLabel("活跃时每"))
        ticks.addWidget(self.tick_spin)
        ticks.addWidget(QLabel("  空闲时每"))
        ticks.addWidget(self.idle_tick_spin)
        ticks.addStretch(1)
        behavior_form.addRow("思考间隔", ticks)
        limits = QHBoxLayout()
        self.max_actions_spin = QSpinBox()
        self.max_actions_spin.setRange(1, 200)
        self.max_actions_spin.setValue(int(self.config.ai.max_actions_per_hour))
        self.min_gap_spin = QSpinBox()
        self.min_gap_spin.setRange(0, 3600)
        self.min_gap_spin.setSuffix(" 秒")
        self.min_gap_spin.setValue(int(self.config.ai.min_action_gap_seconds))
        limits.addWidget(QLabel("每小时最多"))
        limits.addWidget(self.max_actions_spin)
        limits.addWidget(QLabel(" 个动作，最短间隔"))
        limits.addWidget(self.min_gap_spin)
        limits.addStretch(1)
        behavior_form.addRow("动作节流", limits)
        layout.addWidget(behavior_group)

        persona_group, persona_form = _group("额外补充设定与长期偏好")
        personality_seed = self.config.ai.personality
        if personality_seed.strip() == DEFAULT_PERSONALITY.strip():
            personality_seed = ""
        self.personality_edit = QPlainTextEdit(personality_seed)
        self.personality_edit.setPlaceholderText(
            "可选：只追加称呼、雷区、额外语气等补充内容；不能在这里改写模型自带角色设定。"
        )
        self.personality_edit.setFixedHeight(110)
        persona_form.addRow("额外补充设定", self.personality_edit)
        self.instructions_edit = QPlainTextEdit(self.config.ai.instructions)
        self.instructions_edit.setFixedHeight(85)
        persona_form.addRow("用户偏好", self.instructions_edit)
        persona_form.addRow(
            _hint(
                "模型动作包自带的角色设定始终作为主体；这里只能追加补充，留空也完全可用。"
                "不要填写密码、密钥或敏感信息。"
            )
        )
        layout.addWidget(persona_group)

        allowed_group = QGroupBox("可调用动作")
        allowed_layout = QVBoxLayout(allowed_group)
        allowed_layout.setContentsMargins(12, 18, 12, 12)
        self.all_actions_check = QCheckBox("全部允许（推荐）")
        self.all_actions_check.setChecked(not self.config.ai.allowed_actions)
        self.all_actions_check.toggled.connect(self._toggle_all_actions)
        allowed_layout.addWidget(self.all_actions_check)
        self.allowed_list = QListWidget()
        self.allowed_list.setMinimumHeight(150)
        allowed = set(self.config.ai.allowed_actions)
        for clip in sorted(self.actions.values(), key=lambda item: (item.category, item.name)):
            if not clip.ai_visible:
                continue
            item = QListWidgetItem(f"{clip.name}  ·  {clip.category}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.ItemDataRole.UserRole, clip.id)
            item.setCheckState(
                Qt.CheckState.Unchecked
                if allowed and clip.id not in allowed
                else Qt.CheckState.Checked
            )
            self.allowed_list.addItem(item)
        self.allowed_list.setEnabled(bool(self.config.ai.allowed_actions))
        allowed_layout.addWidget(self.allowed_list)
        layout.addWidget(allowed_group)

        dnd_group, dnd_form = _group("勿扰时段")
        self.dnd_enabled = QCheckBox("在指定时段不主动说话或行动")
        self.dnd_enabled.setChecked(self.config.ai.dnd_enabled)
        dnd_form.addRow(self.dnd_enabled)
        dnd_row = QHBoxLayout()
        self.dnd_start = QTimeEdit(QTime.fromString(self.config.ai.dnd_start, "HH:mm"))
        self.dnd_start.setDisplayFormat("HH:mm")
        self.dnd_end = QTimeEdit(QTime.fromString(self.config.ai.dnd_end, "HH:mm"))
        self.dnd_end.setDisplayFormat("HH:mm")
        dnd_row.addWidget(self.dnd_start)
        dnd_row.addWidget(QLabel("至"))
        dnd_row.addWidget(self.dnd_end)
        dnd_row.addStretch(1)
        dnd_form.addRow("时段", dnd_row)
        layout.addWidget(dnd_group)

        memory_group, memory_form = _group("短期记忆")
        self.memory_label = QLabel()
        memory_form.addRow(self.memory_label)
        memory_row = QHBoxLayout()
        clear_memory = QPushButton("清空对话记忆")
        clear_memory.setObjectName("Danger")
        clear_memory.clicked.connect(self._clear_memory)
        export_memory = QPushButton("打开记忆文件")
        export_memory.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.app.paths.data / "memory.json")))
        )
        memory_row.addWidget(clear_memory)
        memory_row.addWidget(export_memory)
        memory_row.addStretch(1)
        memory_form.addRow(memory_row)
        layout.addWidget(memory_group)

        long_group, long_form = _group("长期向量记忆")
        self.long_memory_enabled = QCheckBox("记忆交互经历与用户画像（向量检索）")
        self.long_memory_enabled.setChecked(self.config.memory.enabled)
        long_form.addRow(self.long_memory_enabled)
        self.long_embedding_base = QLineEdit(self.config.memory.embedding_base_url)
        self.long_embedding_base.setPlaceholderText("留空 = 使用上面的 AI Base URL")
        self.long_embedding_model = QLineEdit(self.config.memory.embedding_model)
        self.long_embedding_model.setPlaceholderText("text-embedding-3-small")
        self.long_embedding_key = QLineEdit(self.config.memory.api_key)
        self.long_embedding_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.long_embedding_key.setPlaceholderText("留空 = 使用 AI API Key")
        long_form.addRow("Embedding Base URL", self.long_embedding_base)
        long_form.addRow("Embedding 模型", self.long_embedding_model)
        long_form.addRow("Embedding API Key", self.long_embedding_key)
        top_row = QHBoxLayout()
        self.long_top_spin = QSpinBox()
        self.long_top_spin.setRange(1, 12)
        self.long_top_spin.setValue(int(self.config.memory.top_k))
        top_row.addWidget(QLabel("每次召回"))
        top_row.addWidget(self.long_top_spin)
        top_row.addWidget(QLabel("条相关记忆"))
        top_row.addStretch(1)
        long_form.addRow("召回数量", top_row)
        long_form.addRow(
            _hint(
                "Embedding 同时服务于动作检索、语感样例检索和长期记忆读写：远程接口优先，"
                "不可用时自动回退本地特征向量，因此离线仍可工作。"
                "Planner 只在需要时召回，并只把它判断值得长期保留的摘要送出；不会自动上传每段原始对话。请确认服务商隐私政策。"
            )
        )
        self.long_memory_info = QLabel("")
        self.long_memory_info.setObjectName("Hint")
        self.long_memory_info.setWordWrap(True)
        long_form.addRow(self.long_memory_info)
        self.long_memory_preview = QTextBrowser()
        self.long_memory_preview.setFixedHeight(118)
        self.long_memory_preview.setOpenExternalLinks(False)
        long_form.addRow("用户画像", self.long_memory_preview)
        long_buttons = QHBoxLayout()
        refresh_long = QPushButton("刷新记忆")
        refresh_long.clicked.connect(self._refresh_long_memory)
        clear_long = QPushButton("清空长期记忆")
        clear_long.setObjectName("Danger")
        clear_long.clicked.connect(self._clear_long_memory)
        long_buttons.addWidget(refresh_long)
        long_buttons.addWidget(clear_long)
        long_buttons.addStretch(1)
        long_form.addRow(long_buttons)
        layout.addWidget(long_group)
        layout.addStretch(1)
        self._refresh_memory_label()
        self._refresh_long_memory()
        return tab

    def _refresh_long_memory(self) -> None:
        memory = getattr(self.app, "long_memory", None)
        if memory is None:
            self.long_memory_info.setText("长期记忆数据库不可用。")
            self.long_memory_preview.setPlainText("")
            return
        stats = memory.stats()
        self.long_memory_info.setText(
            f"已保存 {stats.get('count', 0)} 条交互记忆 · "
            f"{stats.get('facts', 0)} 条用户画像 · "
            f"索引：{', '.join(stats.get('models', [])) or '尚未建立'}"
        )
        self.long_memory_preview.setPlainText(memory.profile_text())

    def _clear_long_memory(self) -> None:
        memory = getattr(self.app, "long_memory", None)
        if memory is None:
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            "确定清空长期记忆与用户画像吗？此操作不可撤销。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        memory.clear()
        self._refresh_long_memory()

    def _slider_row(self, form: QFormLayout, label: str, value: int, low: int, high: int):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setValue(value)
        value_label = QLabel(f"{value / 100:.2f}")
        slider.valueChanged.connect(lambda v: value_label.setText(f"{v / 100:.2f}"))
        row = QHBoxLayout()
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        form.addRow(label, row)
        return slider, value_label

    def _toggle_all_actions(self, checked: bool) -> None:
        self.allowed_list.setEnabled(not checked)
        if checked:
            for index in range(self.allowed_list.count()):
                self.allowed_list.item(index).setCheckState(Qt.CheckState.Checked)

    def _refresh_memory_label(self) -> None:
        memory = self.app.memory
        self.memory_label.setText(
            f"已记录 {memory.interaction_count} 次互动 · 好感度 {memory.affinity}/100 · "
            f"最近 {len(memory.recent_conversations(8))} 条对话上下文"
        )

    def _clear_memory(self) -> None:
        if QMessageBox.question(
            self,
            APP_NAME,
            "确定清空本地对话记忆吗？这不会删除动作、模型或插件。",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.app.clear_memory()
        self._refresh_memory_label()

    def _test_ai(self) -> None:
        if self._busy:
            return
        config = copy.deepcopy(self.config)
        config.ai.enabled = self.ai_enabled.isChecked()
        config.ai.base_url = self.base_url_edit.text().strip()
        config.ai.planner_model = self.planner_model_edit.text().strip()
        config.ai.replier_model = self.replier_model_edit.text().strip()
        config.ai.actor_model = self.actor_model_edit.text().strip()
        config.ai.model = config.ai.planner_model or "deepseek-chat"
        config.ai.api_key = self.api_key_edit.text().strip()
        if not config.ai.api_key:
            QMessageBox.information(self, APP_NAME, "请先填写 API Key。")
            return
        if not (config.ai.base_url.startswith("http://") or config.ai.base_url.startswith("https://")):
            QMessageBox.warning(self, APP_NAME, "Base URL 必须以 http:// 或 https:// 开头。")
            return
        self._busy = True
        self.test_ai_button.setEnabled(False)
        self.ai_status.setText("正在连接…")
        self.ai_status.setObjectName("Hint")

        def work() -> str:
            replies = []
            for role, label in (
                ("planner", "Planner"),
                ("replier", "Replier"),
                ("actor", "Actor"),
            ):
                reply = LLMClient(config.ai.for_role(role)).ping()
                replies.append(f"{label}={reply[:12]}")
            return " · ".join(replies)

        def done(reply: str) -> None:
            self._busy = False
            self.test_ai_button.setEnabled(True)
            self.ai_status.setText(f"连接成功：{reply[:60]}")
            self.ai_status.setStyleSheet("color:#a6e3a1;")

        def failed(message: str) -> None:
            self._busy = False
            self.test_ai_button.setEnabled(True)
            self.ai_status.setText(f"连接失败：{message}")
            self.ai_status.setStyleSheet("color:#ff8fa8;")

        self._workers.start(work, on_result=done, on_error=failed)

    # ------------------------------------------------------------------ privacy
    def _build_privacy_tab(self) -> QWidget:
        tab, layout = _scroll_tab()
        keyboard_group, keyboard_form = _group("键盘与输入")
        self.keyboard_enabled = QCheckBox("读取全局键盘活动（仅统计频率，不记录具体内容）")
        self.keyboard_enabled.setChecked(self.config.perception.keyboard_enabled)
        self.raw_keys_enabled = QCheckBox("允许把最近按键名称作为上下文（敏感，默认关闭）")
        self.raw_keys_enabled.setChecked(self.config.perception.raw_keys_enabled)
        keyboard_form.addRow(self.keyboard_enabled)
        keyboard_form.addRow(self.raw_keys_enabled)
        keyboard_form.addRow(
            _hint("注意：按键名称仍可能包含隐私。开启后请避免在敏感应用中输入密码；下文的排除列表会阻止相关上下文上传。")
        )
        self.keyboard_status = _hint("")
        keyboard_form.addRow(self.keyboard_status)
        layout.addWidget(keyboard_group)

        apps_group, apps_form = _group("前台应用与空闲")
        self.foreground_enabled = QCheckBox("读取正在运行的前台应用")
        self.foreground_enabled.setChecked(self.config.perception.foreground_enabled)
        self.share_titles = QCheckBox("允许把窗口标题发送给 AI")
        self.share_titles.setChecked(self.config.perception.share_window_titles)
        self.idle_enabled = QCheckBox("使用系统空闲时间判断用户是否离开")
        self.idle_enabled.setChecked(self.config.perception.idle_enabled)
        apps_form.addRow(self.foreground_enabled)
        apps_form.addRow(self.share_titles)
        apps_form.addRow(self.idle_enabled)
        self.excluded_apps = QPlainTextEdit("\n".join(self.config.perception.excluded_apps))
        self.excluded_apps.setFixedHeight(100)
        apps_form.addRow("排除的应用进程（每行一个）", self.excluded_apps)
        self.excluded_titles = QPlainTextEdit("\n".join(self.config.perception.excluded_title_keywords))
        self.excluded_titles.setFixedHeight(80)
        apps_form.addRow("排除的标题关键词（每行一个）", self.excluded_titles)
        poll_row = QHBoxLayout()
        self.idle_threshold_spin = QSpinBox()
        self.idle_threshold_spin.setRange(30, 7200)
        self.idle_threshold_spin.setSuffix(" 秒")
        self.idle_threshold_spin.setValue(self.config.perception.idle_threshold_seconds)
        poll_row.addWidget(QLabel("空闲阈值"))
        poll_row.addWidget(self.idle_threshold_spin)
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(2, 120)
        self.poll_spin.setSuffix(" 秒")
        self.poll_spin.setValue(self.config.perception.poll_seconds)
        poll_row.addWidget(QLabel("  采样间隔"))
        poll_row.addWidget(self.poll_spin)
        poll_row.addStretch(1)
        apps_form.addRow(poll_row)
        layout.addWidget(apps_group)

        preview_group, preview_form = _group("当前感知预览")
        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setFixedHeight(150)
        self.preview_edit.setStyleSheet("font-family: Consolas, 'Microsoft YaHei UI'; font-size: 12px;")
        refresh = QPushButton("立即刷新")
        refresh.clicked.connect(self._refresh_preview)
        preview_form.addRow(self.preview_edit)
        preview_form.addRow(refresh)
        layout.addWidget(preview_group)
        layout.addWidget(
            _hint(
                "隐私说明：所有感知数据只用于本地上下文和本轮 AI 请求。程序不记录完整击键内容，不保存窗口标题历史，也不会把密码字段作为目标。"
            )
        )
        layout.addStretch(1)
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(2500)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._preview_timer.start()
        return tab

    def _refresh_preview(self) -> None:
        if not hasattr(self, "preview_edit"):
            return
        snapshot = self.app.perception.snapshot()
        text = (
            f"应用：{'受保护' if snapshot.is_private else (snapshot.process_name or '桌面')}\n"
            f"标题：{'（已隐藏）' if snapshot.is_private or not self.config.perception.share_window_titles else snapshot.window_title}\n"
            f"分类：{snapshot.app_category}    空闲：{int(snapshot.idle_seconds)} 秒\n"
            f"最近一分钟击键：{int(snapshot.typing_rate)} 次    App 切换(10min)：{snapshot.app_switch_count}\n"
            f"键盘钩子：{'运行中' if self.app.perception.keyboard_running else '未运行'}"
        )
        if self.app.perception.keyboard_error:
            text += f"\n钩子错误：{self.app.perception.keyboard_error}"
        if snapshot.recent_keys:
            text += f"\n最近按键名称：{' '.join(snapshot.recent_keys[-8:])}"
        self.preview_edit.setPlainText(text)
        if hasattr(self, "keyboard_status"):
            self.keyboard_status.setText(
                "键盘钩子状态："
                + ("运行中" if self.app.perception.keyboard_running else "未运行")
                + ("（失败：" + self.app.perception.keyboard_error + "）" if self.app.perception.keyboard_error else "")
            )

    # ------------------------------------------------------------------ market
    def _build_market_tab(self) -> QWidget:
        tab, layout = _scroll_tab()
        layout.addWidget(
            _hint(
                "资源市场用于浏览和安装模型/动作套装与插件。游客也可以浏览和下载；"
                "登录账号只用于记录身份，所有下载都在设置窗口内完成。"
            )
        )
        self.market_status = QLabel("")
        self.market_status.setObjectName("Hint")
        self.market_status.setWordWrap(True)
        if self._market_session:
            self.market_status.setText(
                f"已登录：{self.config.market.username or '当前账号'}"
            )
        else:
            self.market_status.setText("游客模式：可浏览和下载公开资源。")
        layout.addWidget(self.market_status)

        catalog_group = QGroupBox("资源市场")
        catalog_layout = QVBoxLayout(catalog_group)
        catalog_layout.setContentsMargins(12, 18, 12, 12)
        toolbar = QHBoxLayout()
        self.market_search = QLineEdit()
        self.market_search.setPlaceholderText("搜索名称或描述（留空显示全部）…")
        self.market_search.returnPressed.connect(self._refresh_market)
        self.market_refresh_button = QPushButton("刷新")
        self.market_refresh_button.clicked.connect(lambda: self._refresh_market())
        refresh_button = self.market_refresh_button
        toolbar.addWidget(self.market_search, 1)
        toolbar.addWidget(refresh_button)
        catalog_layout.addLayout(toolbar)
        self.market_tabs = QTabWidget()
        bundles_widget = QWidget()
        bundles_layout = QVBoxLayout(bundles_widget)
        bundles_layout.setContentsMargins(0, 6, 0, 0)
        bundle_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.bundle_list = QListWidget()
        self.bundle_details = QTextBrowser()
        self.bundle_list.currentItemChanged.connect(lambda cur, prev: self._show_market_details("bundle", cur))
        bundle_splitter.addWidget(self.bundle_list)
        bundle_splitter.addWidget(self.bundle_details)
        bundle_splitter.setSizes([300, 460])
        bundles_layout.addWidget(bundle_splitter, 1)
        bundle_pager = QHBoxLayout()
        self.bundle_page_prev = QPushButton("上一页")
        self.bundle_page_prev.clicked.connect(lambda: self._change_market_page("bundle", -1))
        self.bundle_page_label = QLabel("0 / 0")
        self.bundle_page_label.setObjectName("Hint")
        self.bundle_page_next = QPushButton("下一页")
        self.bundle_page_next.clicked.connect(lambda: self._change_market_page("bundle", 1))
        bundle_pager.addWidget(self.bundle_page_prev)
        bundle_pager.addWidget(self.bundle_page_label)
        bundle_pager.addWidget(self.bundle_page_next)
        bundle_pager.addStretch(1)
        bundles_layout.addLayout(bundle_pager)
        bundle_actions = QHBoxLayout()
        self.install_bundle_button = QPushButton("下载并安装模型套装")
        self.install_bundle_button.setObjectName("Primary")
        self.install_bundle_button.clicked.connect(lambda: self._install_selected("bundle"))
        self.open_bundles_button = QPushButton("打开角色目录")
        self.open_bundles_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.app.paths.character_root)))
        )
        bundle_actions.addWidget(self.install_bundle_button)
        bundle_actions.addWidget(self.open_bundles_button)
        bundle_actions.addStretch(1)
        bundles_layout.addLayout(bundle_actions)
        plugins_widget = QWidget()
        plugins_layout = QVBoxLayout(plugins_widget)
        plugins_layout.setContentsMargins(0, 6, 0, 0)
        plugin_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.market_plugin_list = QListWidget()
        self.market_plugin_details = QTextBrowser()
        self.market_plugin_list.currentItemChanged.connect(
            lambda cur, prev: self._show_market_details("plugin", cur)
        )
        plugin_splitter.addWidget(self.market_plugin_list)
        plugin_splitter.addWidget(self.market_plugin_details)
        plugin_splitter.setSizes([300, 460])
        plugins_layout.addWidget(plugin_splitter, 1)
        plugin_pager = QHBoxLayout()
        self.plugin_page_prev = QPushButton("上一页")
        self.plugin_page_prev.clicked.connect(lambda: self._change_market_page("plugin", -1))
        self.plugin_page_label = QLabel("0 / 0")
        self.plugin_page_label.setObjectName("Hint")
        self.plugin_page_next = QPushButton("下一页")
        self.plugin_page_next.clicked.connect(lambda: self._change_market_page("plugin", 1))
        plugin_pager.addWidget(self.plugin_page_prev)
        plugin_pager.addWidget(self.plugin_page_label)
        plugin_pager.addWidget(self.plugin_page_next)
        plugin_pager.addStretch(1)
        plugins_layout.addLayout(plugin_pager)
        plugin_actions = QHBoxLayout()
        self.install_plugin_button = QPushButton("下载并安装插件")
        self.install_plugin_button.setObjectName("Primary")
        self.install_plugin_button.clicked.connect(lambda: self._install_selected("plugin"))
        plugin_actions.addWidget(self.install_plugin_button)
        plugin_actions.addStretch(1)
        plugins_layout.addLayout(plugin_actions)
        self.market_tabs.addTab(bundles_widget, "模型与动作")
        self.market_tabs.addTab(plugins_widget, "插件")
        catalog_layout.addWidget(self.market_tabs, 1)
        self.market_progress = QProgressBar()
        self.market_progress.setRange(0, 0)
        self.market_progress.setMaximumHeight(6)
        self.market_progress.hide()
        catalog_layout.addWidget(self.market_progress)
        layout.addWidget(catalog_group, 1)
        return tab

    def _market_base(self) -> str:
        return (self.config.market.base_url or "http://sickcc.online/cwusr").rstrip("/")

    def _refresh_market_links(self) -> None:
        self._market_client = MarketClient(self._market_base(), self._market_session)

    def _market_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        self._refresh_market_links()
        for button in (
            self.market_refresh_button,
            self.install_bundle_button,
            self.install_plugin_button,
        ):
            button.setEnabled(not busy)
        self.market_progress.setVisible(busy)
        if message:
            self.market_status.setStyleSheet("color:#a9a3c2;")
            self.market_status.setText(message)

    def _on_main_tab_changed(self, index: int) -> None:
        # The market tab must show its catalogue on first visit, even when the
        # search box is empty. It should not require a search or a manual refresh.
        if index == 3 and not self._market_loaded:
            self._refresh_market()

    def _refresh_market(self, query: str | None = None) -> None:
        if self._busy:
            return
        if query is None:
            query = self.market_search.text().strip()
        self._market_query = query
        client = MarketClient(self._market_base(), self._market_session)
        self._market_busy(True, "正在获取市场目录…" if not query else f"正在搜索「{query}」…")

        def work():
            return client.bundles(query), client.plugins(query)

        def done(data) -> None:
            bundles, plugins = data
            self._market_items["bundle"] = bundles
            self._market_items["plugin"] = plugins
            self._market_page = {"bundle": 0, "plugin": 0}
            self._market_loaded = True
            self._populate_market_list("bundle", bundles)
            self._populate_market_list("plugin", plugins)
            self.market_status.setStyleSheet("color:#a6e3a1;")
            scope = f"搜索「{query}」" if query else "全部资源"
            self.market_status.setText(
                f"{scope}：{len(bundles)} 个模型套装 · {len(plugins)} 个插件"
            )
            self._market_busy(False)

        def failed(message: str) -> None:
            self._market_loaded = False
            self._market_busy(False, f"目录获取失败：{_market_failure_hint(message)}")
            self.market_status.setStyleSheet("color:#ff8fa8;")

        self._workers.start(work, on_result=done, on_error=failed)

    def _change_market_page(self, kind: str, delta: int) -> None:
        items = self._market_items[kind]
        page_size = 8
        pages = max(1, (len(items) + page_size - 1) // page_size)
        next_page = max(0, min(pages - 1, self._market_page[kind] + delta))
        if next_page == self._market_page[kind]:
            return
        self._market_page[kind] = next_page
        self._populate_market_list(kind, items)

    def _populate_market_list(self, kind: str, items: list[dict[str, Any]]) -> None:
        widget = self.bundle_list if kind == "bundle" else self.market_plugin_list
        page_size = 8
        pages = max(1, (len(items) + page_size - 1) // page_size)
        page = max(0, min(pages - 1, self._market_page[kind]))
        self._market_page[kind] = page
        start = page * page_size
        visible = items[start:start + page_size]
        widget.clear()
        for item in visible:
            title = item.get("title") or item.get("name") or "未命名"
            author = item.get("creator_name") or item.get("author") or "创作者"
            version = item.get("version") or ""
            widget_item = QListWidgetItem(f"{title}\n{author}  ·  v{version}")
            widget_item.setData(Qt.ItemDataRole.UserRole, item)
            widget.addItem(widget_item)
        if widget.count():
            widget.setCurrentRow(0)
        else:
            widget.addItem(QListWidgetItem("市场暂时没有已审核的资源"))

        page_label = self.bundle_page_label if kind == "bundle" else self.plugin_page_label
        prev_button = self.bundle_page_prev if kind == "bundle" else self.plugin_page_prev
        next_button = self.bundle_page_next if kind == "bundle" else self.plugin_page_next
        page_label.setText(f"{page + 1} / {pages}" if items else "0 / 0")
        prev_button.setEnabled(page > 0)
        next_button.setEnabled(page + 1 < pages)

    def _show_market_details(self, kind: str, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        browser = self.bundle_details if kind == "bundle" else self.market_plugin_details
        if not isinstance(data, dict):
            browser.setHtml("<p style='color:#a9a3c2'>暂无资源。</p>")
            return
        tags = "".join(f"<span style='color:#b9a7ff'>#{tag}</span> " for tag in data.get("tags", []))
        browser.setHtml(
            f"<h2>{data.get('title', '未命名')}</h2>"
            f"<p style='color:#a9a3c2'>v{data.get('version', '?')} · "
            f"{data.get('creator_name', '创作者')} · 下载 {data.get('downloads', 0)} 次</p>"
            f"<p>{data.get('summary', '')}</p>"
            f"<p>{data.get('description', '')}</p>"
            f"<p>{tags}</p>"
            f"<hr><p style='color:#a9a3c2'>安装前会校验 ZIP 路径与资源清单。模型与动作按套装安装，不会覆盖当前模型。</p>"
        )

    def _install_selected(self, kind: str) -> None:
        if self._busy:
            return
        widget = self.bundle_list if kind == "bundle" else self.market_plugin_list
        current = widget.currentItem()
        if current is None:
            return
        item = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(item, dict) or not item.get("id"):
            return
        resource_id = int(item["id"])
        title = item.get("title") or kind
        client = MarketClient(self._market_base(), self._market_session)
        self._market_busy(True, f"正在下载「{title}」…")

        def work():
            archive = client.download(kind, resource_id)
            if kind == "bundle":
                installed = self.app.installer.install_bundle(archive)
                return installed
            plugin = self.app.installer.install_plugin(archive)
            return plugin

        def done(result) -> None:
            self._market_busy(False)
            self._refresh_market_links()
            if kind == "bundle":
                self._refresh_installed_after_install(result)
            else:
                self._clear_plugin_tombstone(result.id)
                self.market_status.setStyleSheet("color:#a6e3a1;")
                self.market_status.setText(
                    f"插件「{result.name}」已安装。保存设置后会重新加载插件，或在插件页手动启用。"
                )
                self._reload_plugins_list()
            self._refresh_market()

        def failed(message: str) -> None:
            self._market_busy(False, f"安装失败：{_market_failure_hint(message)}")
            self.market_status.setStyleSheet("color:#ff8fa8;")

        self._workers.start(work, on_result=done, on_error=failed)

    def _refresh_installed_after_install(self, installed: InstalledBundle) -> None:
        self.market_status.setStyleSheet("color:#a6e3a1;")
        self.market_status.setText(f"「{installed.name}」已安装到本地。")
        self._reload_installed_list()
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"「{installed.name}」安装完成。\n是否立即切换到这个模型与动作套装？",
        )
        if answer == QMessageBox.StandardButton.Yes:
            if self.app.switch_to_installed_bundle(installed):
                self.config = copy.deepcopy(self.app.config)
                self._model_path = self.config.model.pmx_path
                self.model_path_edit.setText(self._model_path)
                self.action_model_edit.setText(self.config.model.actions_model_id)
                self.actions = self.app.actions
                self._reload_action_list()
                self._refresh_model_summary()
                self.tabs.setCurrentIndex(0)
            else:
                QMessageBox.warning(self, APP_NAME, "切换失败，请查看日志。")

    # ------------------------------------------------------------------ plugins
    def _build_plugin_tab(self) -> QWidget:
        tab, layout = _scroll_tab()
        intro = QLabel(
            "插件是本地 Python 代码，拥有你授予的权限级别。只安装你信任的来源。"
            "市场插件在安装后默认不启用。"
        )
        intro.setObjectName("Hint")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        plugin_group = QGroupBox("已安装插件")
        plugin_layout = QVBoxLayout(plugin_group)
        plugin_layout.setContentsMargins(12, 18, 12, 12)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.plugin_list = QListWidget()
        self.plugin_list.currentItemChanged.connect(self._show_plugin_details)
        splitter.addWidget(self.plugin_list)
        self.plugin_details = QTextBrowser()
        splitter.addWidget(self.plugin_details)
        splitter.setSizes([360, 420])
        plugin_layout.addWidget(splitter, 1)
        buttons = QHBoxLayout()
        open_plugins = QPushButton("打开插件目录")
        open_plugins.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.app.paths.plugins)))
        )
        install_local = QPushButton("从 ZIP 安装…")
        install_local.clicked.connect(self._install_local_plugin)
        self.update_plugin_button = QPushButton("从市场检查更新")
        self.update_plugin_button.clicked.connect(self._update_selected_plugin)
        self.uninstall_plugin_button = QPushButton("卸载选中插件")
        self.uninstall_plugin_button.clicked.connect(self._uninstall_selected_plugin)
        buttons.addWidget(open_plugins)
        buttons.addWidget(install_local)
        buttons.addWidget(self.update_plugin_button)
        buttons.addWidget(self.uninstall_plugin_button)
        buttons.addStretch(1)
        plugin_layout.addLayout(buttons)
        layout.addWidget(plugin_group, 1)
        self._reload_plugins_list()
        return tab

    def _reload_plugins_list(self) -> None:
        if not self.app.plugin_manager:
            return
        self.plugin_list.clear()
        for status in self.app.plugin_manager.status():
            enabled = status["id"] in self._plugin_enabled
            item = QListWidgetItem(
                f"{status['name']}   v{status['version']}\n"
                f"{'已启用' if enabled else '已停用'}"
                + (f"  ·  加载失败：{status['error']}" if status.get("error") else "")
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, status)
            self.plugin_list.addItem(item)
        self.plugin_list.itemChanged.connect(self._plugin_item_changed)
        if self.plugin_list.count():
            self.plugin_list.setCurrentRow(0)
        else:
            placeholder = QListWidgetItem("还没有插件。可以从市场安装，或放入插件目录。")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.plugin_list.addItem(placeholder)
            self.plugin_details.setHtml("<p style='color:#a9a3c2'>插件可以为桌宠添加动作、托盘命令和事件反应。</p>")

    def _plugin_item_changed(self, item: QListWidgetItem) -> None:
        status = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(status, dict):
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._plugin_enabled.add(status["id"])
        else:
            self._plugin_enabled.discard(status["id"])

    def _show_plugin_details(self, current: QListWidgetItem | None, previous=None) -> None:
        if current is None:
            return
        status = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(status, dict):
            return
        permissions = "".join(
            f"<li><code>{permission}</code></li>" for permission in status.get("permissions", [])
        )
        self.plugin_details.setHtml(
            f"<h2>{status.get('name')}</h2>"
            f"<p style='color:#a9a3c2'>{status.get('id')} · v{status.get('version')} · "
            f"{status.get('author', '')}</p>"
            f"<p>{status.get('description', '')}</p>"
            f"<p><b>权限</b></p><ul>{permissions or '<li>无</li>'}</ul>"
            f"<p style='color:#a9a3c2'>路径：{status.get('path', '')}</p>"
            + (
                f"<p style='color:#ff8fa8'>加载错误：{status.get('error')}</p>"
                if status.get("error")
                else ""
            )
        )

    def _install_local_plugin(self) -> None:
        archive, _ = QFileDialog.getOpenFileName(self, "选择插件 ZIP", "", "ZIP (*.zip)")
        if not archive:
            return
        try:
            manifest = self.app.installer.install_plugin(Path(archive))
        except (InstallError, Exception) as exc:
            QMessageBox.warning(self, APP_NAME, f"插件安装失败：\n{exc}")
            return
        self._clear_plugin_tombstone(manifest.id)
        QMessageBox.information(
            self,
            APP_NAME,
            f"插件「{manifest.name}」已安装。保存设置后生效；请在插件列表勾选启用。",
        )
        self.app.reload_plugins()
        self._reload_plugins_list()

    def _clear_plugin_tombstone(self, plugin_id: str) -> None:
        for plugins in (self.config.plugins, self.app.config.plugins):
            while plugin_id in plugins.uninstalled:
                plugins.uninstalled.remove(plugin_id)

    def _selected_plugin_status(self) -> dict[str, Any] | None:
        item = self.plugin_list.currentItem()
        if item is None:
            return None
        status = item.data(Qt.ItemDataRole.UserRole)
        return status if isinstance(status, dict) else None

    def _uninstall_selected_plugin(self) -> None:
        status = self._selected_plugin_status()
        if not status:
            return
        plugin_id = str(status.get("id", ""))
        path = Path(str(status.get("path", "")))
        if QMessageBox.question(
            self, APP_NAME, f"确定卸载插件「{status.get('name', plugin_id)}」吗？"
        ) != QMessageBox.StandardButton.Yes:
            return

        # Market plugins can be removed from disk. Bundled/source plugins are
        # kept on disk but tombstoned so they are not discovered or loaded.
        if path.is_dir():
            try:
                path.resolve().relative_to(self.app.paths.market_plugins.resolve())
                self.app.installer.uninstall_plugin(plugin_id)
            except (OSError, ValueError):
                logger.info("Tombstoning bundled/source plugin %s", plugin_id)

        self._plugin_enabled.discard(plugin_id)
        for plugins in (self.config.plugins, self.app.config.plugins):
            for values in (plugins.enabled, plugins.disabled):
                while plugin_id in values:
                    values.remove(plugin_id)
            if plugin_id not in plugins.uninstalled:
                plugins.uninstalled.append(plugin_id)
        try:
            self.app.store.save(self.app.config)
        except Exception:
            logger.exception("Could not persist plugin uninstall")
        self.app.reload_plugins()
        self._reload_plugins_list()
        QMessageBox.information(self, APP_NAME, "插件已卸载，不会再加载。")

    def _update_selected_plugin(self) -> None:
        status = self._selected_plugin_status()
        if not status:
            return
        plugin_id = str(status.get("id", ""))
        current = str(status.get("version", "0"))
        client = MarketClient(self._market_base(), self._market_session)
        self.update_plugin_button.setEnabled(False)

        def done(items) -> None:
            self.update_plugin_button.setEnabled(True)
            match = next(
                (item for item in items if str(item.get("plugin_id", "")) == plugin_id),
                None,
            )
            if not match:
                QMessageBox.information(self, APP_NAME, "市场中没有这个插件的可更新版本。")
                return
            latest = str(match.get("version", "0"))
            if _version_key(latest) <= _version_key(current):
                QMessageBox.information(self, APP_NAME, f"已是最新版本：v{current}")
                return
            answer = QMessageBox.question(
                self,
                APP_NAME,
                f"发现新版本 v{latest}（当前 v{current}）。\n是否下载并安装？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

            def work():
                archive = client.download("plugin", int(match["id"]))
                return self.app.installer.install_plugin(archive)

            def installed(result) -> None:
                self._clear_plugin_tombstone(result.id)
                self.app.reload_plugins()
                self._reload_plugins_list()
                QMessageBox.information(
                    self, APP_NAME, f"插件「{result.name}」已更新到 v{result.version}。"
                )

            def failed(message: str) -> None:
                QMessageBox.warning(self, APP_NAME, f"插件更新失败：{_market_failure_hint(message)}")

            self._workers.start(work, on_result=installed, on_error=failed)

        def failed(message: str) -> None:
            self.update_plugin_button.setEnabled(True)
            QMessageBox.warning(self, APP_NAME, f"检查更新失败：{_market_failure_hint(message)}")

        self._workers.start(client.plugins, on_result=done, on_error=failed)

    # ------------------------------------------------------------------ about
    def _build_about_tab(self) -> QWidget:
        tab, layout = _scroll_tab()
        appearance_group, appearance_form = _group("气泡与启动")
        self.bubble_seconds = QSpinBox()
        self.bubble_seconds.setRange(3, 60)
        self.bubble_seconds.setSuffix(" 秒")
        self.bubble_seconds.setValue(int(self.config.ui.bubble_seconds))
        appearance_form.addRow("气泡停留时间", self.bubble_seconds)
        self.bubble_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.bubble_opacity_slider.setRange(50, 100)
        self.bubble_opacity_slider.setValue(int(self.config.ui.bubble_opacity * 100))
        appearance_form.addRow("气泡不透明度", self.bubble_opacity_slider)
        self.tray_notifications = QCheckBox("显示托盘通知")
        self.tray_notifications.setChecked(self.config.ui.tray_notifications)
        self.autostart_check = QCheckBox("登录 Windows 时自动启动")
        self.autostart_check.setChecked(self.config.ui.autostart)
        appearance_form.addRow(self.tray_notifications)
        appearance_form.addRow(self.autostart_check)
        logs = QPushButton("打开日志目录")
        logs.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.app.paths.logs)))
        )
        appearance_form.addRow(logs)
        layout.addWidget(appearance_group)

        about_group = QGroupBox("关于我们")
        about_layout = QVBoxLayout(about_group)
        about_layout.setContentsMargins(14, 18, 14, 14)
        about = QLabel(
            "<p>感谢使用 AIDeskPal-SICK。</p>"
            "<p><b>交流群：</b>QQ 群 1057604000</p>"
            "<p><b>开发者 URL / 创作者中心：</b>"
            "<a href='http://sickcc.online/cwwlc/'>http://sickcc.online/cwwlc/</a></p>"
            "<p style='color:#a9a3c2'>使用问题、插件与资源交流欢迎加入。</p>"
        )
        about.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        about.setOpenExternalLinks(True)
        about.setWordWrap(True)
        about_layout.addWidget(about)
        layout.addWidget(about_group)
        layout.addStretch(1)
        return tab

    # ------------------------------------------------------------------ save
    def _collect_config(self) -> AppConfig | None:
        config = copy.deepcopy(self.config)
        model_path = self.model_path_edit.text().strip()
        action_model = self.action_model_edit.text().strip()
        if not action_model:
            QMessageBox.warning(self, APP_NAME, "请填写动作包模型 ID。")
            return None
        installed_character = None
        if self._pending_character is not None:
            try:
                installed_character = self.app.import_character_assets(
                    self._pending_character, action_model
                )
            except CharacterError as exc:
                QMessageBox.warning(self, APP_NAME, f"添加角色失败：{exc}")
                return None
            self._pending_character = None
            self._model_path = str(installed_character.pmx_path)
            model_path = str(installed_character.pmx_path)
            action_model = installed_character.model_id
            self.action_model_edit.setText(action_model)
            self.model_path_edit.setText(model_path)
            self.model_summary.setText(
                f"<b>{installed_character.name}</b><br>"
                "<span style='color:#a9a3c2'>已导入角色目录</span>"
            )
        if not Path(model_path).is_file():
            QMessageBox.warning(self, APP_NAME, "PMX 模型文件不存在，请重新选择。")
            return None
        if Path(model_path).suffix.lower() != ".pmx":
            QMessageBox.warning(self, APP_NAME, "模型必须是 .pmx 文件。")
            return None
        config.model.pmx_path = model_path
        if installed_character is not None:
            config.model.name = installed_character.name
        config.model.actions_model_id = action_model
        config.model.id = action_model
        config.window.width = self.width_spin.value()
        config.window.height = self.height_spin.value()
        config.window.pet_scale = self.pet_scale_slider.value() / 100.0
        config.window.opacity = self.opacity_slider.value() / 100.0
        config.window.always_on_top = self.always_on_top.isChecked()
        config.window.click_through_transparent = self.click_through.isChecked()
        config.window.hide_when_fullscreen = self.hide_fullscreen.isChecked()
        config.window.edge_behaviors = self.edge_behaviors.isChecked()
        hide_trigger = self.hide_trigger.currentData() or HIDE_TRIGGER_OFF
        hide_hotkey = self.hide_hotkey_edit.text().strip() or DEFAULT_HIDE_HOTKEY
        if hide_trigger == HIDE_TRIGGER_HOTKEY and parse_sequence(hide_hotkey) is None:
            QMessageBox.warning(
                self,
                APP_NAME,
                "快捷键格式无法识别，请使用带修饰键的组合，例如 Ctrl+Alt+H 或 Ctrl+Shift+F9。",
            )
            return None
        config.window.hide_trigger = str(hide_trigger)
        config.window.hide_hotkey = hide_hotkey

        config.ai.enabled = self.ai_enabled.isChecked()
        config.ai.base_url = self.base_url_edit.text().strip()
        if not (config.ai.base_url.startswith("http://") or config.ai.base_url.startswith("https://")):
            QMessageBox.warning(self, APP_NAME, "AI Base URL 必须以 http:// 或 https:// 开头。")
            return None
        config.ai.planner_model = self.planner_model_edit.text().strip() or "deepseek-chat"
        config.ai.replier_model = self.replier_model_edit.text().strip() or config.ai.planner_model
        config.ai.actor_model = self.actor_model_edit.text().strip() or config.ai.planner_model
        # Keep the legacy default meaningful for old configs and integrations.
        config.ai.model = config.ai.planner_model
        config.ai.api_key = self.api_key_edit.text().strip()
        config.ai.speech_enabled = self.speech_enabled.isChecked()
        config.ai.proactive = self.proactive_enabled.isChecked()
        config.ai.offline_fallback = self.offline_fallback_enabled.isChecked()
        config.ai.autonomy = self.autonomy_slider.value() / 100.0
        config.ai.temperature = self.temperature_slider.value() / 100.0
        config.ai.tick_seconds = self.tick_spin.value()
        config.ai.idle_tick_seconds = self.idle_tick_spin.value()
        config.ai.max_actions_per_hour = self.max_actions_spin.value()
        config.ai.min_action_gap_seconds = self.min_gap_spin.value()
        config.ai.use_character_profile = True
        config.ai.personality = self.personality_edit.toPlainText().strip()
        config.ai.instructions = self.instructions_edit.toPlainText().strip()
        if self.all_actions_check.isChecked():
            config.ai.allowed_actions = []
        else:
            selected = []
            for index in range(self.allowed_list.count()):
                item = self.allowed_list.item(index)
                if item.checkState() == Qt.CheckState.Checked:
                    action_id = item.data(Qt.ItemDataRole.UserRole)
                    if action_id:
                        selected.append(str(action_id))
            if not selected:
                QMessageBox.warning(
                    self,
                    APP_NAME,
                    "至少选择一个可用动作；如果想让 AI 自由选择，请勾选「全部允许」。",
                )
                return None
            config.ai.allowed_actions = selected
        config.ai.dnd_enabled = self.dnd_enabled.isChecked()
        config.ai.dnd_start = self.dnd_start.time().toString("HH:mm")
        config.ai.dnd_end = self.dnd_end.time().toString("HH:mm")

        config.perception.keyboard_enabled = self.keyboard_enabled.isChecked()
        config.perception.raw_keys_enabled = self.raw_keys_enabled.isChecked()
        config.perception.foreground_enabled = self.foreground_enabled.isChecked()
        config.perception.share_window_titles = self.share_titles.isChecked()
        config.perception.idle_enabled = self.idle_enabled.isChecked()
        config.perception.idle_threshold_seconds = self.idle_threshold_spin.value()
        config.perception.poll_seconds = self.poll_spin.value()
        config.perception.excluded_apps = [
            line.strip()
            for line in self.excluded_apps.toPlainText().splitlines()
            if line.strip()
        ]
        config.perception.excluded_title_keywords = [
            line.strip()
            for line in self.excluded_titles.toPlainText().splitlines()
            if line.strip()
        ]

        config.market.session_cookie = self._market_session

        config.plugins.enabled = sorted(self._plugin_enabled)
        config.plugins.disabled = []

        config.memory.enabled = self.long_memory_enabled.isChecked()
        config.memory.embedding_base_url = self.long_embedding_base.text().strip()
        config.memory.embedding_model = self.long_embedding_model.text().strip() or "text-embedding-3-small"
        config.memory.api_key = self.long_embedding_key.text().strip()
        config.memory.top_k = self.long_top_spin.value()

        config.ui.bubble_seconds = self.bubble_seconds.value()
        config.ui.bubble_opacity = self.bubble_opacity_slider.value() / 100.0
        config.ui.tray_notifications = self.tray_notifications.isChecked()
        config.ui.autostart = self.autostart_check.isChecked()
        return config

    def _save(self) -> None:
        config = self._collect_config()
        if config is None:
            return
        try:
            self.saved.emit(config)
        except Exception as exc:
            logger.exception("Could not apply settings")
            QMessageBox.critical(self, APP_NAME, f"应用设置失败：\n{exc}")
            return
        self._saved = True
        self.accept()

    def reject(self) -> None:  # noqa: D401
        if self._preview_timer:
            self._preview_timer.stop()
        self.app.preview_pet_scale(self._original_scale)
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._preview_timer:
            self._preview_timer.stop()
        if not self._saved:
            self.app.preview_pet_scale(self._original_scale)
        self._workers.stop()
        super().closeEvent(event)
