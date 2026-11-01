"""Plugin manifest parsing and validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PLUGIN_API_VERSION = 1
ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,80}$")
KNOWN_PERMISSIONS = {
    "context.read",
    "actions.play",
    "actions.register",
    "speech",
    "ui.tray",
    "events",
    "settings.read",
    "settings.write",
    "network",
}


class PluginError(ValueError):
    pass


@dataclass(slots=True)
class PluginManifest:
    id: str
    name: str
    version: str
    entry: str
    description: str = ""
    author: str = ""
    api_version: int = PLUGIN_API_VERSION
    permissions: tuple[str, ...] = ()
    homepage: str = ""
    path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, path: Path) -> "PluginManifest":
        manifest_path = path / "plugin.json"
        if not manifest_path.is_file():
            raise PluginError("plugin.json not found")
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PluginError(f"invalid plugin.json: {exc}") from exc
        if not isinstance(data, dict):
            raise PluginError("plugin.json must contain an object")
        plugin_id = str(data.get("id", "")).strip()
        if not ID_PATTERN.match(plugin_id):
            raise PluginError("id must be 3-80 chars of letters, digits, '.', '_' or '-'")
        entry = str(data.get("entry", "plugin.py")).strip().replace("\\", "/")
        if not entry or entry.startswith("/") or ".." in Path(entry).parts:
            raise PluginError("entry must be a relative path inside the plugin folder")
        entry_path = (path / entry).resolve()
        try:
            entry_path.relative_to(path.resolve())
        except ValueError as exc:
            raise PluginError("entry escapes the plugin folder") from exc
        if not entry_path.is_file():
            raise PluginError(f"entry file not found: {entry}")
        version = str(data.get("version", "1.0.0"))
        api_version = int(data.get("api_version", PLUGIN_API_VERSION))
        if api_version != PLUGIN_API_VERSION:
            raise PluginError(f"unsupported api_version {api_version}")
        permissions = data.get("permissions", [])
        if not isinstance(permissions, list):
            raise PluginError("permissions must be a list")
        bad = [p for p in permissions if p not in KNOWN_PERMISSIONS]
        if bad:
            raise PluginError(f"unknown permission(s): {', '.join(map(str, bad))}")
        return cls(
            id=plugin_id,
            name=str(data.get("name", plugin_id))[:80],
            version=version,
            entry=entry,
            description=str(data.get("description", ""))[:600],
            author=str(data.get("author", ""))[:120],
            api_version=api_version,
            permissions=tuple(str(p) for p in permissions),
            homepage=str(data.get("homepage", "")),
            path=path,
            raw=data,
        )
