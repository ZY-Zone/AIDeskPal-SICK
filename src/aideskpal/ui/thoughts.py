"""Read-only visualization of the three agents' structured decisions."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from aideskpal.ai.types import AgentTrace, BrainResult
from aideskpal.ui.theme import app_icon, settings_stylesheet


ROLE_LABELS = {
    "planner": "Planner · 亲身体验与主控",
    "replier": "Replier · 最终表达",
    "actor": "Actor · 最终动作",
}


class ThoughtDialog(QDialog):
    """Inspect recent turns without exposing prompts or hidden model reasoning."""

    def __init__(self, results: list[BrainResult] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("三代理思维过程")
        self.setWindowIcon(app_icon(128))
        self.setStyleSheet(settings_stylesheet())
        self.setMinimumSize(760, 680)
        self.resize(860, 780)
        self._results: list[BrainResult] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        title = QLabel("三代理思维过程")
        title.setObjectName("Title")
        layout.addWidget(title)
        hint = QLabel(
            "展示模型主动返回的简短决策摘要、信息交接、记忆意图和耗时；"
            "不展示系统提示、密钥或模型隐藏推理。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.turns = QComboBox()
        self.turns.currentIndexChanged.connect(self._show_current)
        layout.addWidget(self.turns)
        self.meta = QLabel("暂无思维记录。与桌宠对话或等待一次主动互动后，这里会出现内容。")
        self.meta.setWordWrap(True)
        self.meta.setObjectName("Hint")
        layout.addWidget(self.meta)

        self.cards: dict[str, QTextBrowser] = {}
        for role in ("planner", "replier", "actor"):
            group = QGroupBox(ROLE_LABELS[role])
            card_layout = QVBoxLayout(group)
            browser = QTextBrowser()
            browser.setReadOnly(True)
            browser.setOpenExternalLinks(False)
            browser.setMinimumHeight(125 if role == "planner" else 90)
            card_layout.addWidget(browser)
            layout.addWidget(group, 1 if role == "planner" else 0)
            self.cards[role] = browser

        buttons = QHBoxLayout()
        copy = QPushButton("复制本轮摘要")
        copy.clicked.connect(self._copy_current)
        close = QPushButton("关闭")
        close.clicked.connect(self.close)
        buttons.addWidget(copy)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.set_results(results or [])

    def set_results(self, results: list[BrainResult]) -> None:
        selected_time = None
        if self._results and 0 <= self.turns.currentIndex() < len(self._results):
            selected_time = self._results[self.turns.currentIndex()].created_at
        self._results = list(reversed(results[-30:]))
        self.turns.blockSignals(True)
        self.turns.clear()
        selected_index = 0
        for index, result in enumerate(self._results):
            stamp = datetime.fromtimestamp(result.created_at).strftime("%m-%d %H:%M:%S")
            label = f"{stamp} · {result.trigger} · {result.source}"
            if result.speech:
                label += f" · {result.speech[:18]}"
            self.turns.addItem(label)
            if selected_time is not None and result.created_at == selected_time:
                selected_index = index
        self.turns.blockSignals(False)
        if self._results:
            self.turns.setCurrentIndex(selected_index)
        self._show_current()

    def refresh(self, results: list[BrainResult]) -> None:
        self.set_results(results)

    def _show_current(self) -> None:
        index = self.turns.currentIndex()
        if index < 0 or index >= len(self._results):
            self.meta.setText("暂无思维记录。与桌宠对话或等待一次主动互动后，这里会出现内容。")
            for card in self.cards.values():
                card.setPlainText("尚未执行")
            return
        result = self._results[index]
        self.meta.setText(
            f"来源：{result.source}　触发：{result.trigger}　总耗时：{result.duration_ms} ms\n"
            f"最终动作：{result.action_id or '保持现状'}　最终台词：{result.speech or '保持安静'}"
        )
        for role, card in self.cards.items():
            traces = [trace for trace in result.trace if trace.role == role]
            card.setPlainText(self._format_traces(role, traces, result))

    @staticmethod
    def _format_traces(
        role: str, traces: list[AgentTrace], result: BrainResult
    ) -> str:
        if not traces:
            if role == "planner" and result.plan is not None:
                return result.plan.reason or result.plan.intent
            return "本轮未执行"
        blocks = []
        for index, trace in enumerate(traces, 1):
            heading = f"第 {index} 次判断 · {trace.model or '未知模型'} · {trace.status} · {trace.duration_ms} ms"
            body = trace.summary or "无摘要"
            if trace.detail:
                body += "\n\n" + trace.detail
            blocks.append(heading + "\n" + body)
        return "\n\n────────────────\n\n".join(blocks)

    def _copy_current(self) -> None:
        index = self.turns.currentIndex()
        if index < 0 or index >= len(self._results):
            return
        result = self._results[index]
        sections = [self.meta.text()]
        for role in ("planner", "replier", "actor"):
            traces = [trace for trace in result.trace if trace.role == role]
            sections.append(ROLE_LABELS[role] + "\n" + self._format_traces(role, traces, result))
        QGuiApplication.clipboard().setText("\n\n".join(sections))
