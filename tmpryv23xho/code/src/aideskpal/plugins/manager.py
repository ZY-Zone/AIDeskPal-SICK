"""Discover, load, unload and track local plugins."""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aideskpal.config import PluginConfig
from aideskpal.paths import AppPaths
from aideskpal.plugins.api import PluginAPI, PluginHost
from aideskpal.plugins.manifest import PluginError, PluginManifest

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LoadedPlugin:
    manifest: PluginManifest
    enabled: bool
    loaded: bool = False
    error: str = ""
    api: PluginAPI | None = field(default=None, repr=False)
    module: Any = field(default=None, repr=False)
    instance: Any = field(default=None, repr=False)


class PluginManager:
    def __init__(self, host: PluginHost, paths: AppPaths, config: PluginConfig) -> None:
        self.host = host
        self.paths = paths
        self.config = config
        self.plugins: dict[str, LoadedPlugin] = {}
        self.plugin_actions: list[dict[str, Any]] = []
        self._modules: dict[str, Any] = {}

    def discover(self) -> list[PluginManifest]:
        candidates: dict[str, PluginManifest] = {}
        roots = [self.paths.plugins, self.paths.market_plugins, self.paths.bundled_plugins]
        for root in roots:
            if not root.is_dir():
                continue
            for directory in sorted(root.iterdir()):
                if not directory.is_dir():
                    continue
                try:
                    manifest = PluginManifest.load(directory)
                except PluginError as exc:
                    logger.warning("Ignoring plugin at %s: %s", directory, exc)
                    continue
                if manifest.id in self.config.uninstalled:
                    logger.info("Skipping uninstalled plugin %s", manifest.id)
                    continue
                # Later roots (user data) intentionally override bundled plugins.
                candidates[manifest.id] = manifest
        return list(candidates.values())

    def load_all(self) -> None:
        self.unload_all()
        for manifest in self.discover():
            enabled = manifest.id in self.config.enabled and manifest.id not in self.config.disabled
            entry = LoadedPlugin(manifest=manifest, enabled=enabled)
            self.plugins[manifest.id] = entry
            if not enabled:
                continue
            self._load(entry)
        self._load_plugin_actions()

    def _load(self, entry: LoadedPlugin) -> None:
        manifest = entry.manifest
        api = PluginAPI(manifest, self.host, self.paths)
        entry.api = api
        try:
            module_name = "aideskpal_plugin_" + manifest.id.replace(".", "_").replace("-", "_")
            spec = importlib.util.spec_from_file_location(module_name, (manifest.path / manifest.entry))
            if spec is None or spec.loader is None:
                raise PluginError("cannot create import spec")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            setup = getattr(module, "setup", None)
            if not callable(setup):
                raise PluginError("plugin.py must define setup(api)")
            instance = setup(api)
            entry.module = module
            entry.instance = instance
            entry.loaded = True
            entry.error = ""
            logger.info("Loaded plugin %s %s", manifest.id, manifest.version)
        except Exception as exc:
            entry.error = str(exc)
            entry.loaded = False
            logger.exception("Could not load plugin %s", manifest.id)
            try:
                api.shutdown()
            except Exception:
                pass

    def unload_plugin(self, plugin_id: str) -> None:
        entry = self.plugins.get(plugin_id)
        if not entry or not entry.loaded:
            return
        try:
            instance = entry.instance
            teardown = getattr(instance, "teardown", None) if instance is not None else None
            if callable(teardown):
                teardown()
        except Exception:
            logger.exception("Plugin teardown failed: %s", plugin_id)
        try:
            if entry.api:
                entry.api.shutdown()
        except Exception:
            logger.exception("Plugin API shutdown failed: %s", plugin_id)
        entry.loaded = False
        entry.api = None
        entry.instance = None

    def unload_all(self) -> None:
        for plugin_id in list(self.plugins):
            self.unload_plugin(plugin_id)
        self.plugins.clear()
        self.plugin_actions.clear()

    def enable(self, plugin_id: str) -> None:
        if plugin_id not in self.config.enabled:
            self.config.enabled.append(plugin_id)
        if plugin_id in self.config.disabled:
            self.config.disabled.remove(plugin_id)
        entry = self.plugins.get(plugin_id)
        if entry and not entry.loaded:
            entry.enabled = True
            self._load(entry)

    def disable(self, plugin_id: str) -> None:
        if plugin_id not in self.config.disabled:
            self.config.disabled.append(plugin_id)
        if plugin_id in self.config.enabled:
            self.config.enabled.remove(plugin_id)
        self.unload_plugin(plugin_id)
        if plugin_id in self.plugins:
            self.plugins[plugin_id].enabled = False

    def _load_plugin_actions(self) -> None:
        actions_file = self.host_settings_path("plugin_actions")
        self.plugin_actions = []
        if actions_file.is_file():
            try:
                data = json.loads(actions_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.plugin_actions = [item for item in data if isinstance(item, dict)]
            except (OSError, json.JSONDecodeError):
                self.plugin_actions = []

    def host_settings_path(self, name: str) -> Path:
        return self.paths.data / "plugin_data" / f"_{name}.json"

    def status(self) -> list[dict[str, Any]]:
        result = []
        for entry in sorted(self.plugins.values(), key=lambda item: item.manifest.name):
            result.append(
                {
                    "id": entry.manifest.id,
                    "name": entry.manifest.name,
                    "version": entry.manifest.version,
                    "description": entry.manifest.description,
                    "author": entry.manifest.author,
                    "permissions": list(entry.manifest.permissions),
                    "enabled": entry.enabled,
                    "loaded": entry.loaded,
                    "error": entry.error,
                    "path": str(entry.manifest.path or ""),
                }
            )
        return result

    def add_plugin_action(self, plugin_id: str, raw_action: dict[str, Any]) -> None:
        raw_action = dict(raw_action)
        raw_action.setdefault("author", plugin_id)
        self.plugin_actions.append(raw_action)
        path = self.host_settings_path("plugin_actions")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.plugin_actions, ensure_ascii=False, indent=2), encoding="utf-8")
