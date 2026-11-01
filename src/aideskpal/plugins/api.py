"""The only API surface handed to plugins.

Plugins are trusted local Python code; permissions are an audit/consent mechanism,
not a sandbox.  The market UI warns before installing plugins and the settings
panel shows every declared permission.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Protocol

from aideskpal.core.events import EventBus
from aideskpal.plugins.manifest import PluginManifest

logger = logging.getLogger(__name__)

ALLOWED_EVENTS = {
    "tick",
    "action_started",
    "action_finished",
    "interaction",
    "speech",
    "config_changed",
    "foreground_changed",
}


class PluginHost(Protocol):
    event_bus: EventBus

    def speak(self, text: str, *, emotion: str = "calm", style: str = "soft") -> None: ...
    def play_action(self, action_id: str) -> bool: ...
    def register_tray_action(self, plugin_id: str, label: str, callback: Callable[[], None]) -> None: ...
    def remove_tray_actions(self, plugin_id: str) -> None: ...
    def register_plugin_action(self, plugin_id: str, raw_action: dict[str, Any]) -> bool: ...
    def plugin_context(self) -> dict[str, Any]: ...
    def plugin_settings(self, plugin_id: str) -> dict[str, Any]: ...
    def save_plugin_settings(self, plugin_id: str, data: dict[str, Any]) -> None: ...


class PluginAPI:
    def __init__(self, manifest: PluginManifest, host: PluginHost, paths) -> None:
        self.manifest = manifest
        self._host = host
        self._permissions = set(manifest.permissions)
        self._paths = paths
        self._settings_cache: dict[str, Any] | None = None
        self._registered_events: list[str] = []

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def data_dir(self) -> Path:
        path = self._paths.data / "plugin_data" / self.manifest.id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _require(self, permission: str) -> None:
        if permission not in self._permissions:
            raise PermissionError(
                f"插件 {self.manifest.id} 未声明权限 {permission}；已拒绝调用"
            )

    def log(self, message: str) -> None:
        logger.info("[plugin:%s] %s", self.manifest.id, message)

    def speak(self, text: str, *, emotion: str = "calm", style: str = "soft") -> None:
        self._require("speech")
        self._host.speak(str(text)[:220], emotion=emotion, style=style)

    def play_action(self, action_id: str) -> bool:
        self._require("actions.play")
        return self._host.play_action(str(action_id))

    def register_tray_action(self, label: str, callback: Callable[[], None]) -> None:
        self._require("ui.tray")
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._host.register_tray_action(self.manifest.id, str(label)[:60], callback)

    def register_action(self, action: dict[str, Any]) -> bool:
        self._require("actions.register")
        if not isinstance(action, dict):
            raise TypeError("action must be a JSON object")
        return self._host.register_plugin_action(self.manifest.id, action)

    def current_context(self) -> dict[str, Any]:
        self._require("context.read")
        return self._host.plugin_context()

    def on(self, event: str, callback: Callable[..., None]) -> None:
        self._require("events")
        if event not in ALLOWED_EVENTS:
            raise ValueError(f"unsupported event {event!r}")
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._host.event_bus.subscribe(event, callback, owner=self.manifest.id)
        self._registered_events.append(event)

    def emit(self, event: str, **payload: Any) -> None:
        self._require("events")
        if event not in ALLOWED_EVENTS:
            raise ValueError(f"unsupported event {event!r}")
        self._host.event_bus.emit(event, **payload)

    @property
    def settings(self) -> dict[str, Any]:
        self._require("settings.read")
        if self._settings_cache is None:
            self._settings_cache = self._host.plugin_settings(self.manifest.id)
        return dict(self._settings_cache)

    def update_settings(self, values: dict[str, Any]) -> None:
        self._require("settings.write")
        current = dict(self.settings)
        current.update(values)
        self._settings_cache = current
        self._host.save_plugin_settings(self.manifest.id, current)

    def shutdown(self) -> None:
        for event in self._registered_events:
            self._host.event_bus.unsubscribe(event, self.manifest.id)
        self._registered_events.clear()
        self._host.remove_tray_actions(self.manifest.id)
