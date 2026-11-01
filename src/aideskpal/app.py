"""Application entry point and runtime glue."""

from __future__ import annotations

import argparse
import copy
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QLockFile, QObject, QRect, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QSurfaceFormat
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from aideskpal import APP_NAME, __version__
from aideskpal.ai.character import CharacterError, CharacterProfile, find_character
from aideskpal.ai.long_memory import LongTermMemory
from aideskpal.ai.memory import AgentMemory
from aideskpal.ai.orchestrator import AIOrchestrator
from aideskpal.ai.types import BrainResult
from aideskpal.animation.action import ActionClip, ActionError, ActionLibrary, parse_action
from aideskpal.character_store import CharacterInstall, CharacterStore
from aideskpal.config import AppConfig, SettingsStore
from aideskpal.core.events import EventBus
from aideskpal.logging_setup import setup_logging
from aideskpal.market.installer import BundleInstaller, InstallError, InstalledBundle
from aideskpal.paths import AppPaths, get_paths
from aideskpal.perception.service import PerceptionService
from aideskpal.perception.snapshot import PerceptionSnapshot
from aideskpal.plugins.manager import PluginManager
from aideskpal.pmx.model import PmxError, load_pmx
from aideskpal.ui.bubble import SpeechBubble
from aideskpal.ui.chatbox import ChatBox
from aideskpal.ui.edge import EdgeController
from aideskpal.ui.hotkey import DEFAULT_SEQUENCE as DEFAULT_HIDE_HOTKEY
from aideskpal.ui.hotkey import GlobalHotkey
from aideskpal.ui.pet_window import (
    HIDE_TRIGGER_HOTKEY,
    HIDE_TRIGGER_OFF,
    HIDE_TRIGGERS,
    PetWindow,
)
from aideskpal.ui.theme import app_icon
from aideskpal.ui.tray import TrayController
from aideskpal.ui.workers import FunctionWorker
from aideskpal.utils.windows import autostart_enabled, is_fullscreen_foreground, set_autostart

logger = logging.getLogger(__name__)


class DesktopPetApp(QObject):
    """Owns the model, windows, scheduler, plugins and AI workers."""

    def __init__(
        self,
        qapp: QApplication,
        paths: AppPaths,
        store: SettingsStore,
        *,
        model_override: str | None = None,
        initial_action: str | None = None,
        no_single_instance: bool = False,
    ) -> None:
        super().__init__()
        self.qapp = qapp
        self.paths = paths
        self.store = store
        self.config: AppConfig = store.config
        if model_override:
            self.config.model.pmx_path = str(Path(model_override).expanduser())
        self.model = None
        self.actions: dict[str, ActionClip] = {}
        self.library = ActionLibrary([])
        self.character: CharacterProfile | None = None
        self.installer = BundleInstaller(paths)
        self.character_store = self.installer.character_store
        self.memory = AgentMemory(paths.data / "memory.json")
        try:
            self.long_memory: LongTermMemory | None = LongTermMemory(
                paths.data / "long_term_memory.sqlite3",
                self.config.memory,
                self.config.ai,
            )
        except Exception:
            logger.exception("Long-term memory unavailable")
            self.long_memory = None
        self.event_bus = EventBus()
        self.brain = AIOrchestrator(
            self.config.ai,
            [],
            self.memory,
            raw_keys_enabled=self.config.perception.raw_keys_enabled,
            long_memory=self.long_memory,
        )
        self.perception = PerceptionService(self.config.perception)
        self.plugin_manager: PluginManager | None = None
        self.pet: PetWindow | None = None
        self.bubble: SpeechBubble | None = None
        self.chat: ChatBox | None = None
        self.tray: TrayController | None = None
        self.edge_controller: EdgeController | None = None
        self.settings_dialog = None
        self.thought_dialog = None
        self._onboarding_dialog = None
        self._ai_workers: set[FunctionWorker] = set()
        self._ai_busy = False
        self._pending_requests: list[tuple[str, str]] = []
        self._last_proactive = 0.0
        self._next_proactive_at = time.monotonic() + 45.0
        self._last_idle_state = False
        self._hidden_by_user = False
        self._hidden_by_fullscreen = False
        self._hide_hotkey = GlobalHotkey()
        self._position_save_timer: QTimer | None = None
        self._shutting_down = False
        self._plugin_tray_actions: dict[str, list[tuple[str, Any]]] = {}
        self._last_snapshot = PerceptionSnapshot()
        self._lock = QLockFile(str(paths.data / "aideskpal.lock")) if not no_single_instance else None
        if self._lock is not None:
            self._lock.setStaleLockTime(30_000)
            if not self._lock.tryLock(100):
                raise RuntimeError("AIDeskPal-SICK is already running.")
        self._build_runtime(initial_action=initial_action)
        self._start_timers()
        self.last_ai_error = ""

    # ------------------------------------------------------------------ startup
    def _ensure_model(self) -> bool:
        path = Path(self.config.model.pmx_path).expanduser() if self.config.model.pmx_path else None
        if path is not None and path.is_file():
            return True
        message = (
            "没有找到默认的 PMX 模型。\n\n"
            "请选择一个 PMX 模型，或先在资源市场安装模型/动作套装。"
        )
        QMessageBox.information(None, APP_NAME, message)
        selected, _ = QFileDialog.getOpenFileName(
            None, "选择 PMX 模型", str(Path.home()), "PMX 模型 (*.pmx)"
        )
        if not selected:
            return False
        self.config.model.pmx_path = selected
        self.store.save(self.config)
        return True

    def _build_runtime(self, *, initial_action: str | None = None) -> None:
        if not self._ensure_model():
            raise RuntimeError("No PMX model selected")
        self._load_model(self.config.model.pmx_path)
        self._load_actions()
        self._create_windows(initial_action)
        self._create_tray()
        self._create_plugins()
        self._restore_plugin_actions()
        self._wire()
        self.perception.start()
        self._last_snapshot = self.perception.snapshot()
        self.brain.set_config(self.config.ai, list(self.actions.values()))
        self._apply_autostart(False)
        self.tray.set_actions(self.actions, self.config.last_action_id if self.pet else "")
        if self.tray:
            QTimer.singleShot(2400, self._welcome_notification)
            QTimer.singleShot(4500, lambda: self._request_ai("startup"))

    def _load_model(self, path: str) -> None:
        model = load_pmx(path)
        model.to_render_space()
        self.model = model
        logger.info(
            "Loaded PMX %s (%s): %d verts, %d triangles, %d bones, %d morphs",
            model.name,
            path,
            model.vertex_count,
            model.triangle_count,
            len(model.bones),
            len(model.morphs),
        )

    def _action_roots(self) -> list[Path]:
        roots = [self.paths.bundled_actions]
        seen = {self.paths.bundled_actions.resolve()}
        for item in self.installer.list_installed():
            actions_dir = Path(str(item.get("actions_dir", "")))
            if actions_dir.is_dir() and actions_dir.resolve() not in seen:
                roots.append(actions_dir)
                seen.add(actions_dir.resolve())
        for character in self.character_store.list():
            actions_dir = character.actions_dir
            if actions_dir.is_dir() and actions_dir.resolve() not in seen:
                roots.append(actions_dir)
                seen.add(actions_dir.resolve())
        # Also support a self-contained folder selected by an absolute model path
        # (useful when the packaged app runs before its portable character copy).
        if self.config.model.pmx_path:
            model_parent = Path(self.config.model.pmx_path).parent
            for candidate in (model_parent / "actions", model_parent):
                if candidate.is_dir() and candidate.resolve() not in seen:
                    roots.append(candidate)
                    seen.add(candidate.resolve())
        roots.append(self.paths.actions)
        return roots

    def _find_action_source(self, model_id: str) -> Path | None:
        """Find an existing action pack to copy into a character folder."""
        candidates = [self.paths.bundled_actions / model_id, self.paths.actions / model_id]
        for item in self.installer.list_installed():
            actions_dir = Path(str(item.get("actions_dir", "")))
            if actions_dir.is_dir():
                candidates.append(actions_dir)
        for candidate in candidates:
            if not candidate.is_dir():
                continue
            if any(
                path.suffix.lower() == ".json"
                and path.name not in {"character.json", "pack.json", "bundle.json"}
                for path in candidate.rglob("*.json")
            ):
                return candidate
        return None

    def import_character_assets(
        self, pmx_path: str | Path, action_model_id: str
    ) -> CharacterInstall:
        """Copy PMX, action JSON and character prompt into a self-contained folder."""
        source = self._find_action_source(action_model_id)
        if source is None:
            raise CharacterError(f"找不到动作包 {action_model_id}，请先安装对应动作")
        character_file = source / "character.json"
        if not character_file.is_file():
            character_file = source.parent / "character.json"
        if not character_file.is_file():
            raise CharacterError(f"动作包 {action_model_id} 没有 character.json")
        return self.character_store.install_local(
            Path(pmx_path),
            source,
            character_path=character_file,
        )

    def _load_actions(self) -> None:
        if self.model is None:
            return
        library = ActionLibrary(self._action_roots())
        library.load(self.model)
        self.library = library
        model_id = self.config.model.actions_model_id or self.config.model.id
        character_model = model_id
        clips = {clip.id: clip for clip in library.for_model(model_id)}
        if not clips:
            # If there is exactly one action pack, do not hide it behind a typo.
            available_models = {clip.model for clips_by_id in library.actions.values() for clip in clips_by_id.values()}
            if len(available_models) == 1:
                only_model = next(iter(available_models))
                clips = {clip.id: clip for clip in library.for_model(only_model)}
                character_model = only_model
                logger.warning(
                    "No actions for model %s; falling back to only pack %s", model_id, only_model
                )
        self.actions = clips
        for error in library.errors:
            logger.warning("Action pack issue in %s: %s", error.get("file"), error.get("error"))
        if not self.actions:
            logger.warning("No actions loaded for model %s", model_id)
        self.character = find_character(character_model, self._action_roots())
        if self.character:
            logger.info(
                "Character profile bound to %s: %s (%s)",
                character_model,
                self.character.name,
                self.character.source,
            )
        else:
            logger.info("No character.json bound to model %s; using global personality", character_model)
        self.brain.set_character(self.character)

    def _create_windows(self, initial_action: str | None) -> None:
        assert self.model is not None
        if self.edge_controller is not None:
            self.edge_controller.stop()
            self.edge_controller.deleteLater()
            self.edge_controller = None
        self.pet = PetWindow(self.model, self.actions, self.config)
        self.pet.position_changed.connect(self._on_position_changed)
        self.pet.interaction.connect(self._on_interaction)
        self.pet.action_changed.connect(self._on_action_changed)
        self.pet.action_finished.connect(
            lambda action_id: self.event_bus.emit("action_finished", action_id=action_id)
        )
        self.pet.request_chat.connect(self.open_chat)
        self.pet.request_hide.connect(self.hide_pet)
        self.pet.drag_state_changed.connect(self._on_drag_state)
        self.pet.show()
        self.pet.place_on_screen(self.config.window.x, self.config.window.y)
        self.pet.raise_()
        self.edge_controller = EdgeController(self.pet, self.config, self)
        self.edge_controller.start()
        self.bubble = SpeechBubble()
        self.chat = ChatBox()
        self.chat.submitted.connect(self.send_chat_message)
        self.apply_hide_trigger()
        if initial_action:
            QTimer.singleShot(600, lambda: self.pet and self.pet.play_action(initial_action))

    def _create_tray(self) -> None:
        self.tray = TrayController(self)
        self.tray.set_character_name(self.character.name if self.character else "桌宠")
        self.tray.open_settings.connect(self.open_settings)
        self.tray.open_onboarding.connect(self.open_onboarding)
        self.tray.open_thoughts.connect(self.open_thoughts)
        self.tray.toggle_visibility.connect(self.toggle_visibility)
        self.tray.quit_requested.connect(self.quit)
        self.tray.show_logs.connect(self.open_logs)
        self.tray.play_action.connect(self.preview_action)
        self.tray.show()

    def _create_plugins(self) -> None:
        self.plugin_manager = PluginManager(self, self.paths, self.config.plugins)
        self.plugin_manager.load_all()

    def _restore_plugin_actions(self) -> None:
        if not self.plugin_manager:
            return
        for raw in self.plugin_manager.plugin_actions:
            self._add_plugin_action_clip(raw, persist=False)
        self._refresh_plugin_tray()

    def _wire(self) -> None:
        self._position_save_timer = QTimer(self)
        self._position_save_timer.setSingleShot(True)
        self._position_save_timer.timeout.connect(self._persist_position)

    def _start_timers(self) -> None:
        self._scheduler_timer = QTimer(self)
        self._scheduler_timer.setInterval(20_000)
        self._scheduler_timer.timeout.connect(self._scheduler_check)
        self._scheduler_timer.start()

        self._context_timer = QTimer(self)
        self._context_timer.setInterval(8_000)
        self._context_timer.timeout.connect(self._context_check)
        self._context_timer.start()

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(60_000)
        self._tick_timer.timeout.connect(self._emit_plugin_tick)
        self._tick_timer.start()

        self._fullscreen_timer = QTimer(self)
        self._fullscreen_timer.setInterval(4_000)
        self._fullscreen_timer.timeout.connect(self._fullscreen_check)
        if self.config.window.hide_when_fullscreen:
            self._fullscreen_timer.start()

    # ------------------------------------------------------------------ settings
    def open_settings(self) -> None:
        from aideskpal.ui.settings_dialog import SettingsDialog

        if self.settings_dialog is not None and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        if self.edge_controller is not None:
            self.edge_controller.leave_to_normal()
        dialog = SettingsDialog(self)
        dialog.saved.connect(self.apply_settings)
        dialog.finished.connect(self._on_settings_closed)
        self.settings_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_settings_closed(self, _result: int) -> None:
        self.settings_dialog = None

    def open_onboarding(self) -> None:
        """Re-run the account/AI setup wizard from the tray."""
        if self._onboarding_dialog is not None:
            self._onboarding_dialog.raise_()
            self._onboarding_dialog.activateWindow()
            return
        if self.settings_dialog is not None:
            self.settings_dialog.close()
        from aideskpal.ui.onboarding import OnboardingDialog

        dialog = OnboardingDialog(copy.deepcopy(self.config), self.paths)
        self._onboarding_dialog = dialog
        try:
            result = dialog.exec()
        finally:
            self._onboarding_dialog = None
        new_config = dialog.config
        new_config.first_run = False
        try:
            self.apply_settings(new_config)
        except Exception:
            logger.exception("Could not apply onboarding settings")
            return
        if self.tray:
            self.tray.notify(
                APP_NAME,
                "初始化设置已保存。" if result == QDialog.DialogCode.Accepted else "已关闭初始化向导。",
            )

    def preview_pet_scale(self, scale: float) -> None:
        """Apply a temporary scale while the settings dialog is open."""
        if self.pet is not None:
            if self.edge_controller is not None:
                self.edge_controller.leave_to_normal()
            self.pet.set_scale(scale)
            if self.bubble is not None and self.bubble.isVisible():
                self.bubble.hide_message()

    def apply_settings(self, new_config: AppConfig) -> None:
        old = self.config
        model_changed = str(Path(old.model.pmx_path)) != str(Path(new_config.model.pmx_path))
        actions_model_changed = old.model.actions_model_id != new_config.model.actions_model_id
        self.config = new_config
        self.store.save(new_config)
        if self.long_memory is not None:
            self.long_memory.reconfigure(new_config.memory, new_config.ai)
        self.brain.set_config(
            new_config.ai,
            [clip for clip in self.actions.values() if clip.ai_visible],
            new_config.memory,
        )
        self.brain.raw_keys_enabled = new_config.perception.raw_keys_enabled
        self.perception.update_config(new_config.perception)
        if self.pet:
            self.pet.config = new_config
            self.pet.apply_config(new_config)
        if self.edge_controller is not None:
            self.edge_controller.apply_config(new_config)
        if self.config.window.hide_when_fullscreen:
            self._fullscreen_timer.start()
        else:
            self._fullscreen_timer.stop()
            if self._hidden_by_fullscreen and self.pet:
                self.pet.show()
                self._hidden_by_fullscreen = False
        if self.plugin_manager:
            self._load_actions()
            self.plugin_manager.config = new_config.plugins
            self.plugin_manager.load_all()
            self._restore_plugin_actions()
            self._refresh_plugin_tray()
        self._apply_autostart()
        if model_changed:
            if not self.reload_model(new_config.model.pmx_path):
                QMessageBox.warning(
                    None,
                    APP_NAME,
                    "新模型加载失败，已保留当前模型。请检查 PMX 路径后重试。",
                )
        else:
            if actions_model_changed:
                self._load_actions()
                self._restore_plugin_actions()
                self.brain.set_config(self.config.ai, list(self.actions.values()))
            if self.pet:
                self.pet.set_actions(self.actions)
                self._refresh_tray_actions()
        self._next_proactive_at = time.monotonic() + 20.0
        # The hide gesture can change without a restart: re-read it (and rebind
        # the global hotkey) after every save.
        self.apply_hide_trigger()
        self.event_bus.emit("config_changed", config=self.config.to_dict())
        if self.tray:
            self.tray.set_status("设置已保存")

    def reload_model(self, path: str) -> bool:
        try:
            old_model = self.model
            self._load_model(path)
        except Exception as exc:
            logger.exception("Could not reload model %s", path)
            return False
        old_pet = self.pet
        old_bubble = self.bubble
        old_chat = self.chat
        if old_pet:
            old_pet._closed = True
            old_pet.close()
            old_pet.deleteLater()
        if old_bubble:
            old_bubble.close()
        if old_chat:
            old_chat.close()
        try:
            self._load_actions()
            self._create_windows(None)
            assert self.pet is not None
            self._restore_plugin_actions()
            self.brain.set_config(self.config.ai, list(self.actions.values()))
            if self.tray:
                self.tray.set_character_name(self.character.name if self.character else "桌宠")
                self.tray.set_actions(self.actions, self.config.last_action_id)
            self.pet.show()
            self.pet.raise_()
            self._apply_autostart()
            return True
        except Exception:
            logger.exception("Could not recreate pet window after model reload")
            self.model = old_model
            return False

    # ------------------------------------------------------------------ AI
    def _request_ai(self, trigger: str, user_text: str = "") -> None:
        if self._ai_busy:
            if trigger in {"user_message", "headpat", "poke"}:
                if len(self._pending_requests) < 3:
                    self._pending_requests.append((trigger, user_text))
            return
        if self.pet is None:
            return
        snapshot = self.perception.snapshot()
        self._last_snapshot = snapshot
        current_action = self.pet.current_action_id if self.pet else None
        self._ai_busy = True
        if self.tray:
            self.tray.set_status("正在思考…")
        worker = FunctionWorker(
            lambda: self.brain.run(
                trigger, snapshot, user_text=user_text, current_action=current_action
            ),
            self,
        )
        self._ai_workers.add(worker)

        def finished(result: Any) -> None:
            self._ai_workers.discard(worker)
            worker.deleteLater()
            self._ai_busy = False
            if isinstance(result, BrainResult):
                self._handle_ai_result(result)
            self._drain_ai_queue()

        def failed(message: str) -> None:
            self._ai_workers.discard(worker)
            worker.deleteLater()
            self._ai_busy = False
            logger.error("AI task crashed: %s", message)
            if self.tray:
                self.tray.set_status("AI 暂时不可用")
            self._drain_ai_queue()

        worker.completed.connect(finished)
        worker.failed.connect(failed)
        worker.start()

    def _drain_ai_queue(self) -> None:
        if not self._pending_requests or self._ai_busy:
            return
        trigger, text = self._pending_requests.pop(0)
        QTimer.singleShot(50, lambda: self._request_ai(trigger, text))

    def _handle_ai_result(self, result: BrainResult) -> None:
        if self._shutting_down:
            return
        if result.skipped_reason:
            logger.info("AI skipped: %s", result.skipped_reason)
            if self.tray:
                self.tray.set_status("静候")
            return
        logger.info(
            "AI result source=%s action=%s speech=%s error=%s",
            result.source,
            result.action_id,
            bool(result.speech),
            result.error,
        )
        if result.error:
            self.last_ai_error = result.error
        if result.action_id and self.pet and not self.pet.dragging:
            ok = self.pet.play_action(result.action_id, fade=0.45)
            if ok:
                self.config.last_action_id = result.action_id
                self.store.save(self.config)
                self.event_bus.emit("action_started", action_id=result.action_id)
        if result.speech and self.bubble and self.pet and self._can_show_bubble():
            self.bubble.show_message(
                result.speech,
                anchor=self.pet.geometry(),
                seconds=self.config.ui.bubble_seconds,
                style=result.bubble_style,
            )
            self.event_bus.emit("speech", text=result.speech, emotion=result.emotion)
        if self.tray:
            if result.error and result.source == "offline":
                self.tray.set_status("离线陪伴中")
            else:
                self.tray.set_status("正在陪伴")
        self._update_scheduler_after_turn()
        self._refresh_tray_actions()
        if self.thought_dialog is not None:
            self.thought_dialog.refresh(self.brain.history)

    def _update_scheduler_after_turn(self) -> None:
        self._last_proactive = time.monotonic()
        base = (
            self.config.ai.idle_tick_seconds
            if self._last_snapshot.idle_seconds >= self.config.perception.idle_threshold_seconds
            else self.config.ai.tick_seconds
        )
        jitter = base * random.uniform(-0.12, 0.18)
        self._next_proactive_at = time.monotonic() + max(20.0, base + jitter)

    def _scheduler_check(self) -> None:
        if self._shutting_down or self._ai_busy or self.pet is None or not self.pet.isVisible():
            return
        if self.pet.dragging:
            return
        if not self.config.ai.enabled or not self.config.ai.proactive:
            return
        if self.bubble and self.bubble.isVisible():
            return
        now = time.monotonic()
        if now < self._next_proactive_at:
            return
        self._next_proactive_at = now + 30.0
        self._request_ai("timer")

    def send_chat_message(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if self.bubble and self.pet and self._can_show_bubble():
            self.bubble.show_message(
                "……", anchor=self.pet.geometry(), seconds=10, style="soft"
            )
        self.memory.record_event("user_message")
        self._request_ai("user_message", user_text=text)

    def preview_action(self, action_id: str) -> None:
        if not self.pet:
            return
        if not self.pet.play_action(action_id, fade=0.35):
            return
        self.config.last_action_id = action_id if self.actions.get(action_id) else self.config.last_action_id
        self.store.save(self.config)
        self._refresh_tray_actions()

    def set_idle_action(self, action_id: str) -> None:
        if self.pet:
            self.pet.set_idle_action(action_id)
            self.config.last_action_id = action_id
            self.store.save(self.config)

    # ------------------------------------------------------------------ interactions
    def _on_interaction(self, trigger: str, x: int, y: int) -> None:
        if not self.config.ai.speech_enabled and not self.config.ai.enabled:
            return
        if self.edge_controller is not None:
            self.edge_controller.leave_for_interaction()
        immediate = "headpat_reaction" if trigger == "headpat" else "poke_reaction"
        if self.pet and immediate in self.actions:
            self.pet.play_action(immediate, fade=0.18)
        self.memory.record_event(trigger)
        self.event_bus.emit("interaction", trigger=trigger, x=x, y=y)
        self._request_ai(trigger)

    def _on_action_changed(self, action_id: str) -> None:
        clip = self.actions.get(action_id)
        if self.tray and clip:
            self.tray.set_status(f"{clip.name} · {clip.category}")
        if self.plugin_manager:
            self.event_bus.emit("action_started", action_id=action_id)

    def _on_drag_state(self, dragging: bool) -> None:
        self.event_bus.emit("interaction", trigger="drag_start" if dragging else "drag_end", x=0, y=0)
        if dragging and self.bubble:
            self.bubble.hide_message()

    def _on_position_changed(self, x: int, y: int) -> None:
        self.config.window.x = x
        self.config.window.y = y
        if self._position_save_timer:
            self._position_save_timer.start(900)

    def _persist_position(self) -> None:
        if self.pet:
            self.config.window.x = self.pet.x()
            self.config.window.y = self.pet.y()
        try:
            self.store.save(self.config)
        except Exception:
            logger.exception("Could not persist window position")

    # ------------------------------------------------------------------ visibility
    def toggle_visibility(self) -> None:
        if self._hidden_by_user:
            self.show_pet()
        else:
            self.hide_pet()

    def hide_pet(self) -> None:
        """Minimise the pet to the notification area.

        This has to behave like a real minimise: every top-level window that can
        outlive the pet (speech bubble, chat input, edge pose) is torn down, the
        AI is stopped from popping a new bubble later, and the foreground is
        handed back so the pet is not left owning focus while invisible.
        """
        self._hidden_by_user = True
        if self.pet:
            self.pet.hide()
        # The Planner has to know the Replier can no longer reach the user;
        # otherwise it keeps planning lines that nothing can display.
        self.brain.set_replier_available(False)
        # Cancel and hide the bubble *and* its pending timer; a queued AI reply
        # would otherwise re-show it minutes after the pet vanished.
        if self.bubble:
            self.bubble.hide_message()
        # The chat box is a separate top-level window, so hiding the pet alone
        # would leave the input stranded over the desktop.
        if self.chat:
            self.chat.hide()
        if self.edge_controller is not None:
            # Stop the cycle outright: the pet is going invisible, so rescheduling
            # would fire edge poses behind a hidden window. Clear the pose first so
            # it does not reappear stuck to a wall.
            self.edge_controller.stop()
            self.edge_controller.mode = None
            self.edge_controller.pet.clear_edge_pose()
        if self.tray:
            self.tray.set_visible(False)
            self.tray.set_status("已隐藏")
        # Give the foreground back: a hidden always-on-top window that still owns
        # activation keeps swallowing keystrokes, which is not what "minimised"
        # means to a user.
        self._release_foreground()

    def _release_foreground(self) -> None:
        # QWidget exposes clearFocus(); the pet is a QOpenGLWindow (a QWindow)
        # and does not, so drop focus only where the API exists.
        for window in (self.chat, self.bubble, self.pet):
            clear = getattr(window, "clearFocus", None) if window is not None else None
            if callable(clear):
                clear()
        try:
            # Hand activation back to whatever the user was doing before the pet
            # came forward.  Failure is harmless (there may be no other window).
            QApplication.setActiveWindow(None)
        except (AttributeError, RuntimeError):
            logger.debug("Could not release the foreground window", exc_info=True)

    def show_pet(self) -> None:
        self._hidden_by_user = False
        self._hidden_by_fullscreen = False
        # Tell the Planner the Replier is back, including anything it wanted to
        # say while the pet was tucked away.
        self.brain.set_replier_available(True)
        if self.pet:
            self.pet.show()
            self.pet.raise_()
        if self.tray:
            self.tray.set_visible(True)
            self.tray.set_status("静候")

    def _fullscreen_check(self) -> None:
        if self.pet is None:
            return
        try:
            fullscreen = is_fullscreen_foreground()
        except Exception:
            fullscreen = False
        if fullscreen and not self._hidden_by_fullscreen and self.config.window.hide_when_fullscreen:
            self._hidden_by_fullscreen = True
            if not self._hidden_by_user:
                self.pet.hide()
                if self.bubble:
                    self.bubble.hide_message()
                # Same consequence as a manual hide: no bubble can be shown.
                self.brain.set_replier_available(False)
        elif not fullscreen and self._hidden_by_fullscreen:
            self._hidden_by_fullscreen = False
            if not self._hidden_by_user:
                self.pet.show()
                self.brain.set_replier_available(True)

    def _context_check(self) -> None:
        snapshot = self.perception.snapshot()
        self._last_snapshot = snapshot
        is_idle = snapshot.idle_seconds >= self.config.perception.idle_threshold_seconds
        if self._last_idle_state and not is_idle:
            self._request_ai("idle_return")
        self._last_idle_state = is_idle
        self.event_bus.emit("foreground_changed", context=self.plugin_context())

    def _emit_plugin_tick(self) -> None:
        self.event_bus.emit(
            "tick",
            context=self.plugin_context(),
            interval_seconds=60,
            snapshot=self._last_snapshot.public_dict(),
        )

    # ------------------------------------------------------------------ chat / menus
    def open_chat(self) -> None:
        if self.chat and self.pet:
            if not self.pet.isVisible():
                self.show_pet()
            if self.edge_controller is not None:
                self.edge_controller.leave_to_normal()
            self.chat.open_at(self.pet.character_screen_rect())

    def apply_hide_trigger(self) -> None:
        """Push the configured hide gesture to the window and the hotkey.

        Called at start-up and whenever settings are saved, so switching the
        trigger never needs a restart.
        """
        trigger = str(self.config.window.hide_trigger or "off")
        if trigger not in HIDE_TRIGGERS:
            trigger = HIDE_TRIGGER_OFF
        if self.pet is not None:
            self.pet.set_hide_trigger(trigger)
        if trigger == HIDE_TRIGGER_HOTKEY:
            sequence = self.config.window.hide_hotkey or DEFAULT_HIDE_HOTKEY
            if not self._hide_hotkey.register(sequence, self.hide_pet):
                # Fall back to the safe default before giving up.
                if sequence != DEFAULT_HIDE_HOTKEY and self._hide_hotkey.register(
                    DEFAULT_HIDE_HOTKEY, self.hide_pet
                ):
                    self.tray and self.tray.set_status(f"隐藏快捷键改为 {DEFAULT_HIDE_HOTKEY}")
                    return
                if self.tray:
                    self.tray.set_status("隐藏快捷键被占用")
        else:
            self._hide_hotkey.unregister()

    def _can_show_bubble(self) -> bool:
        """True only while the pet is actually on screen.

        Guiding rule for the whole hide feature: a hidden pet must be completely
        gone.  Every path that can raise the speech bubble checks this, so a
        reply that arrives after the user tucked the pet away stays silent
        instead of leaving an orphaned text box on the desktop.
        """
        if self._hidden_by_user or self._hidden_by_fullscreen:
            return False
        return self.pet is not None and self.pet.isVisible()

    def open_thoughts(self) -> None:
        from aideskpal.ui.thoughts import ThoughtDialog

        if self.thought_dialog is None:
            self.thought_dialog = ThoughtDialog(self.brain.history)
            self.thought_dialog.finished.connect(self._on_thoughts_closed)
        else:
            self.thought_dialog.refresh(self.brain.history)
        self.thought_dialog.show()
        self.thought_dialog.raise_()
        self.thought_dialog.activateWindow()

    def _on_thoughts_closed(self, _result: int) -> None:
        self.thought_dialog = None

    def open_logs(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.logs)))

    def _welcome_notification(self) -> None:
        if self.tray and self.config.ui.tray_notifications:
            self.tray.notify(
                APP_NAME,
                f"{self.character.name if self.character else '你的伙伴'}已来到桌面。右键托盘图标可以打开设置。",
            )

    # ------------------------------------------------------------------ plugins
    def speak(self, text: str, *, emotion: str = "calm", style: str = "soft") -> None:
        if not self.config.ai.speech_enabled:
            return
        if self.bubble and self.pet and self._can_show_bubble():
            self.bubble.show_message(
                text,
                anchor=self.pet.geometry(),
                seconds=self.config.ui.bubble_seconds,
                style=style,
            )
            self.event_bus.emit("speech", text=text, emotion=emotion)

    def play_action(self, action_id: str) -> bool:
        if not self.pet:
            return False
        if self.edge_controller is not None:
            self.edge_controller.leave_to_normal()
        ok = self.pet.play_action(action_id)
        if ok and self.actions.get(action_id):
            self.config.last_action_id = action_id
        return ok

    def register_tray_action(self, plugin_id: str, label: str, callback: Any) -> None:
        self._plugin_tray_actions.setdefault(plugin_id, []).append((label, callback))
        self._refresh_plugin_tray()

    def remove_tray_actions(self, plugin_id: str) -> None:
        self._plugin_tray_actions.pop(plugin_id, None)
        self._refresh_plugin_tray()

    def _refresh_plugin_tray(self) -> None:
        if not self.tray:
            return
        self.tray.set_plugin_actions(self._plugin_tray_actions)

    def _refresh_tray_actions(self) -> None:
        if self.tray:
            self.tray.set_actions(self.actions, self.pet.current_action_id if self.pet else "")

    def register_plugin_action(self, plugin_id: str, raw_action: dict[str, Any]) -> bool:
        clip = self._add_plugin_action_clip(raw_action, persist=True, plugin_id=plugin_id)
        return clip is not None

    def _add_plugin_action_clip(
        self, raw_action: dict[str, Any], *, persist: bool, plugin_id: str = ""
    ) -> ActionClip | None:
        if self.model is None:
            return None
        try:
            clip = parse_action(raw_action, self.model)
        except ActionError as exc:
            logger.warning("Invalid plugin action from %s: %s", plugin_id, exc)
            return None
        expected = self.config.model.actions_model_id or self.config.model.id
        if clip.model != expected:
            logger.warning(
                "Plugin action %s targets model %s, expected %s", clip.id, clip.model, expected
            )
            return None
        self.actions[clip.id] = clip
        self.brain.set_config(self.config.ai, list(self.actions.values()))
        if self.pet:
            self.pet.set_actions(self.actions)
        self._refresh_tray_actions()
        if persist and self.plugin_manager:
            self.plugin_manager.add_plugin_action(plugin_id, raw_action)
        return clip

    def plugin_context(self) -> dict[str, Any]:
        snapshot = self._last_snapshot
        category = "private" if snapshot.is_private else snapshot.app_category
        return {
            "application": "protected" if snapshot.is_private else snapshot.process_name,
            "category": category,
            "idle_seconds": int(snapshot.idle_seconds),
            "typing_per_minute": int(snapshot.typing_rate),
            "current_action": self.pet.current_action_id if self.pet else "",
            "time": time.strftime("%H:%M"),
            "affinity": self.memory.affinity,
        }

    def plugin_settings(self, plugin_id: str) -> dict[str, Any]:
        import json

        path = self.paths.data / "plugin_data" / f"{plugin_id}.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (OSError, json.JSONDecodeError):
                pass
        return {}

    def save_plugin_settings(self, plugin_id: str, data: dict[str, Any]) -> None:
        import json

        path = self.paths.data / "plugin_data" / f"{plugin_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def reload_plugins(self) -> None:
        if not self.plugin_manager:
            return
        self._plugin_tray_actions.clear()
        self._load_actions()
        self.plugin_manager.config = self.config.plugins
        self.plugin_manager.load_all()
        self._restore_plugin_actions()
        self._refresh_plugin_tray()
        if self.pet:
            self.pet.set_actions(self.actions)
        self._refresh_tray_actions()
        self.brain.set_config(self.config.ai, list(self.actions.values()))

    # ------------------------------------------------------------------ market
    def install_market_bundle(self, archive: Path) -> InstalledBundle:
        installed = self.installer.install_bundle(archive)
        return installed

    def switch_to_installed_bundle(self, installed: InstalledBundle) -> bool:
        self.config.model.pmx_path = str(installed.pmx_path)
        self.config.model.id = installed.model_id
        self.config.model.actions_model_id = installed.model_id
        self.config.model.name = installed.name
        self.config.last_action_id = ""
        self.store.save(self.config)
        if not self.reload_model(str(installed.pmx_path)):
            return False
        if self.tray:
            self.tray.set_status(f"已切换：{installed.name}")
        return True

    # ------------------------------------------------------------------ autostart
    def _autostart_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        exe = pythonw if pythonw.is_file() else Path(sys.executable)
        return f'"{exe}" -m aideskpal'

    def _apply_autostart(self, force: bool = True) -> None:
        want = bool(self.config.ui.autostart)
        if force or want != autostart_enabled(APP_NAME):
            set_autostart(APP_NAME, self._autostart_command(), want)

    # ------------------------------------------------------------------ lifecycle
    def clear_memory(self) -> None:
        self.memory.clear()
        if self.tray:
            self.tray.set_status("短期记忆已清空")

    def quit(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        logger.info("Shutting down")
        self._hide_hotkey.unregister()
        for timer in (
            getattr(self, "_scheduler_timer", None),
            getattr(self, "_context_timer", None),
            getattr(self, "_tick_timer", None),
            getattr(self, "_fullscreen_timer", None),
            self._position_save_timer,
        ):
            if timer:
                timer.stop()
        if self.pet:
            self.config.window.x = self.pet.x()
            self.config.window.y = self.pet.y()
        try:
            self.store.save(self.config)
        except Exception:
            logger.exception("Could not save config on exit")
        for worker in list(self._ai_workers):
            worker.cancel()
            worker.wait(1200)
        self.perception.stop()
        if self.plugin_manager:
            self.plugin_manager.unload_all()
        if self.bubble:
            self.bubble.close()
        if self.chat:
            self.chat.close()
        if self.thought_dialog is not None:
            self.thought_dialog.close()
        if self.pet:
            self.pet.close()
            self.pet.deleteLater()
        if self.tray:
            self.tray.close()
        self.qapp.quit()


def configure_surface_format() -> None:
    fmt = QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setAlphaBufferSize(8)
    fmt.setStencilBufferSize(8)
    fmt.setSamples(4)
    fmt.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(fmt)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="aideskpal", description="AIDeskPal-SICK desktop companion")
    parser.add_argument("--model", help="PMX model path (overrides settings for this session)")
    parser.add_argument("--action", help="Play this action at startup")
    parser.add_argument("--data-dir", help="Override the user data directory")
    parser.add_argument("--no-ai", action="store_true", help="Force offline mode for this session")
    parser.add_argument("--onboarding", action="store_true", help="Force the first-run setup wizard")
    parser.add_argument("--no-onboarding", action="store_true", help="Skip the first-run setup wizard")
    parser.add_argument("--no-single-instance", action="store_true")
    parser.add_argument("--screenshot", help="Capture the pet to this PNG and exit")
    parser.add_argument("--quit-after", type=float, default=0.0, help="Auto-quit after N seconds")
    parser.add_argument("--version", action="version", version=f"AIDeskPal-SICK {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv if argv is not None else sys.argv[1:]))
    if args.data_dir:
        os.environ["AIDESKPAL_DATA_DIR"] = args.data_dir
    paths = get_paths()
    setup_logging(paths.logs_file, console=False)
    logger.info("Starting AIDeskPal-SICK %s", __version__)
    logger.info("Data directory: %s", paths.data)

    configure_surface_format()
    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName(APP_NAME)
    qapp.setApplicationDisplayName(APP_NAME)
    qapp.setApplicationVersion(__version__)
    qapp.setWindowIcon(app_icon(128))
    qapp.setQuitOnLastWindowClosed(False)

    store = SettingsStore(paths)
    config = store.load()

    # Login is a startup gate. Closing the dialog is a valid guest choice.
    should_login = (
        not config.market.session_cookie
        and not args.screenshot
        and not args.quit_after
        and not args.no_ai
    )
    if should_login:
        from aideskpal.ui.login_dialog import LoginDialog

        login = LoginDialog(config.market.username)
        try:
            login.exec()
        except Exception:
            logger.exception("Login dialog failed")
        if login.guest:
            config.market.session_cookie = ""
            config.market.username = ""
        else:
            config.market.session_cookie = login.session
            config.market.username = login.username
        try:
            store.save(config)
        except Exception:
            logger.exception("Could not save login state")

    first_run_before = bool(config.first_run)
    should_onboard = (
        (config.first_run or args.onboarding)
        and not args.no_onboarding
        and not args.no_ai
        and not args.screenshot
        and not args.quit_after
    )
    if should_onboard:
        from aideskpal.ui.onboarding import OnboardingDialog

        wizard = OnboardingDialog(copy.deepcopy(config), paths)
        logger.info("Showing first-run onboarding")
        try:
            wizard.exec()
        except Exception:
            logger.exception("Onboarding wizard failed")
        config = wizard.config
        config.first_run = False
        try:
            store.save(config)
        except Exception:
            logger.exception("Could not save onboarding configuration")

    if args.no_ai:
        config.ai.enabled = False
        config.ai.api_key = ""

    needs_start_market = (
        (first_run_before or not config.model.pmx_path)
        and not args.screenshot
        and not args.quit_after
    )
    if needs_start_market:
        from aideskpal.ui.market_start import MarketStartDialog
        from aideskpal.market.installer import BundleInstaller

        chooser = MarketStartDialog(config, paths, BundleInstaller(paths))
        logger.info("Showing first-run market chooser")
        try:
            chooser.exec()
        except Exception:
            logger.exception("Market chooser failed")
        try:
            store.save(config)
        except Exception:
            logger.exception("Could not save market selection")

    # Show a pointer only if the chooser was skipped and no model exists.
    if not config.model.pmx_path:
        QMessageBox.information(
            None,
            APP_NAME,
            "欢迎使用 AIDeskPal-SICK。\n请选择你的 PMX 模型；也可以先取消，再到设置里配置。",
        )
    try:
        app = DesktopPetApp(
            qapp,
            paths,
            store,
            model_override=args.model,
            initial_action=args.action,
            no_single_instance=args.no_single_instance,
        )
    except RuntimeError as exc:
        if "already running" in str(exc):
            QMessageBox.information(
                None,
                APP_NAME,
                "AIDeskPal-SICK 已经在运行。\n"
                "请查看系统托盘；如果图标被 Windows 11 隐藏，"
                "按 Ctrl+Alt+F12 打开菜单。",
            )
            return 0
        logger.exception("Startup failed")
        QMessageBox.critical(None, APP_NAME, f"启动失败：\n{exc}\n\n日志：{paths.logs_file}")
        return 1
    except (PmxError, OSError) as exc:
        logger.exception("Startup failed")
        QMessageBox.critical(None, APP_NAME, f"无法加载模型或动作：\n{exc}")
        return 1
    except Exception:
        logger.exception("Unexpected startup failure")
        QMessageBox.critical(None, APP_NAME, f"启动失败，详情见日志：\n{paths.logs_file}")
        return 1

    if args.quit_after:
        QTimer.singleShot(int(args.quit_after * 1000), app.quit)
    if args.screenshot:
        out = Path(args.screenshot)

        def capture() -> None:
            if app.pet:
                app.pet.capture(out)
                logger.info("Screenshot saved to %s", out)
            app.quit()

        QTimer.singleShot(2600, capture)
    return qapp.exec()


if __name__ == "__main__":
    raise SystemExit(main())
