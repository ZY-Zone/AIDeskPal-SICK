"""Typed, versioned application configuration.

User-facing defaults live in ``config/main-config.json`` inside this package.
Per-user changes are still written to the writable application data directory
(``user_data/settings.json`` for the portable build), while API keys and market
session cookies are stored separately with Windows DPAPI.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from aideskpal.paths import AppPaths

CONFIG_VERSION = 3
CONFIG_FILE_NAME = "main-config.json"


def _character_roots(root: Path) -> list[Path]:
    return [
        root / "src" / "aideskpal" / "character",
        root / "aideskpal" / "character",
    ]


def default_pmx_path(root: Path) -> str:
    env = os.environ.get("AIDESKPAL_MODEL")
    if env:
        return str(Path(env).expanduser())
    # Self-contained character folders are preferred over external path refs.
    for character_root in _character_roots(root):
        if not character_root.is_dir():
            continue
        for character_dir in sorted(character_root.iterdir()):
            if not character_dir.is_dir():
                continue
            for candidate in (
                character_dir / "model.pmx",
                character_dir / "model" / "model.pmx",
            ):
                if candidate.is_file():
                    return str(candidate)
    sample = root / "sample_content" / "starling" / "model.pmx"
    if sample.is_file():
        return str(sample)
    return ""


@dataclass(slots=True)
class ModelConfig:
    id: str = ""
    name: str = ""
    pmx_path: str = ""
    actions_model_id: str = ""
    show_shadow: bool = True


@dataclass(slots=True)
class WindowConfig:
    width: int = 420
    height: int = 700
    x: int | None = None
    y: int | None = None
    pet_scale: float = 1.0
    opacity: float = 0.98
    always_on_top: bool = True
    click_through_transparent: bool = True
    hide_when_fullscreen: bool = True
    always_visible_on_top: bool = True
    edge_behaviors: bool = True
    edge_fall_chance: float = 0.4
    # How the pet is tucked away into the tray.  One of ``double_click_body``,
    # ``double_right_click``, ``hotkey`` or ``off``.  The default keeps the
    # original behaviour of double-clicking anywhere but the head.
    hide_trigger: str = "double_click_body"
    hide_hotkey: str = "Ctrl+Alt+H"


DEFAULT_PERSONALITY = (
    "你是用户的桌面伙伴。说话简洁、自然，先观察再回应，尊重用户此刻的专注与安静。"
    "你有自己的性格，但绝不假装自己能做到程序能力之外的事情。"
)
DEFAULT_INSTRUCTIONS = (
    "优先安静陪伴；不要连续说话；用户专注时降低打扰频率。"
    "用户明确要求安静、勿扰或关闭时立即遵守。"
)


@dataclass(slots=True)
class AIConfig:
    enabled: bool = True
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    # Empty role overrides inherit ``model`` for backwards compatibility.  The
    # three agents deliberately use separate clients even when the names match:
    # their prompts, temperatures and future provider settings must not leak.
    planner_model: str = ""
    replier_model: str = ""
    actor_model: str = ""
    api_key: str = field(default="", repr=False)
    temperature: float = 0.85
    max_tokens: int = 900
    timeout_seconds: int = 45
    proactive: bool = True
    speech_enabled: bool = True
    tick_seconds: int = 120
    idle_tick_seconds: int = 300
    autonomy: float = 0.7
    max_actions_per_hour: int = 24
    min_action_gap_seconds: int = 18
    use_character_profile: bool = True
    personality: str = DEFAULT_PERSONALITY
    instructions: str = DEFAULT_INSTRUCTIONS
    language: str = "zh-CN"
    allowed_actions: list[str] = field(default_factory=list)
    blocked_actions: list[str] = field(default_factory=list)
    dnd_enabled: bool = False
    dnd_start: str = "23:30"
    dnd_end: str = "07:30"
    memory_enabled: bool = True
    offline_fallback: bool = True
    show_reasoning_in_log: bool = False

    def model_for(self, role: str) -> str:
        """Resolve a role's model without mutating the shared configuration."""
        if role not in {"planner", "replier", "actor"}:
            raise ValueError(f"unknown AI role: {role}")
        override = str(getattr(self, f"{role}_model", "")).strip()
        return override or self.model.strip() or "deepseek-chat"

    def for_role(self, role: str) -> "AIConfig":
        """Return an independent client configuration for one agent."""
        return replace(self, model=self.model_for(role))


@dataclass(slots=True)
class MemoryConfig:
    enabled: bool = True
    embedding_base_url: str = ""
    embedding_model: str = "text-embedding-3-small"
    api_key: str = field(default="", repr=False)
    top_k: int = 5
    max_records: int = 4000
    profile_extraction: bool = True


@dataclass(slots=True)
class PerceptionConfig:
    keyboard_enabled: bool = True
    raw_keys_enabled: bool = False
    foreground_enabled: bool = True
    idle_enabled: bool = True
    idle_threshold_seconds: int = 180
    poll_seconds: int = 10
    share_window_titles: bool = True
    excluded_apps: list[str] = field(
        default_factory=lambda: [
            "keepass",
            "bitwarden",
            "1password",
            "keychain",
            "authenticator",
        ]
    )
    excluded_title_keywords: list[str] = field(
        default_factory=lambda: ["密码", "password", "登录验证", "private"]
    )


@dataclass(slots=True)
class MarketConfig:
    base_url: str = "http://sickcc.online/cwusr"
    username: str = ""
    session_cookie: str = field(default="", repr=False)
    auto_check: bool = True
    allow_untrusted_plugins: bool = False


@dataclass(slots=True)
class PluginConfig:
    enabled: list[str] = field(default_factory=lambda: ["com.aideskpal.focus_orbit"])
    disabled: list[str] = field(default_factory=list)
    uninstalled: list[str] = field(default_factory=list)


@dataclass(slots=True)
class UIConfig:
    bubble_seconds: int = 8
    bubble_opacity: float = 0.94
    accent: str = "#b9a7ff"
    tray_notifications: bool = True
    autostart: bool = False
    language: str = "zh-CN"


@dataclass(slots=True)
class AppConfig:
    version: int = CONFIG_VERSION
    model: ModelConfig = field(default_factory=ModelConfig)
    window: WindowConfig = field(default_factory=WindowConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    perception: PerceptionConfig = field(default_factory=PerceptionConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    plugins: PluginConfig = field(default_factory=PluginConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    last_action_id: str = ""
    first_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for config_field in fields(self):
            value = getattr(self, config_field.name)
            if hasattr(value, "__dataclass_fields__"):
                data[config_field.name] = _dataclass_to_dict(value)
            else:
                data[config_field.name] = value
        return data


def _dataclass_to_dict(obj: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for config_field in fields(obj):
        name = config_field.name
        if name in {"api_key", "session_cookie"}:
            continue
        value = getattr(obj, name)
        if hasattr(value, "__dataclass_fields__"):
            out[name] = _dataclass_to_dict(value)
        elif isinstance(value, Path):
            out[name] = str(value)
        else:
            out[name] = value
    return out


def _apply(cls: type, current: Any, payload: Any) -> Any:
    if not isinstance(payload, dict):
        return current
    for config_field in fields(current):
        if config_field.name not in payload:
            continue
        raw = payload[config_field.name]
        existing = getattr(current, config_field.name)
        if hasattr(existing, "__dataclass_fields__"):
            _apply(type(existing), existing, raw)
            continue
        if config_field.name in {"api_key", "session_cookie"}:
            continue
        try:
            if isinstance(existing, bool):
                setattr(current, config_field.name, bool(raw))
            elif isinstance(existing, int) and not isinstance(existing, bool):
                setattr(current, config_field.name, int(raw))
            elif isinstance(existing, float):
                setattr(current, config_field.name, float(raw))
            elif isinstance(existing, list):
                setattr(current, config_field.name, list(raw) if isinstance(raw, list) else existing)
            elif isinstance(existing, str):
                setattr(current, config_field.name, str(raw))
            elif existing is None:
                setattr(current, config_field.name, raw if isinstance(raw, int) else None)
        except (TypeError, ValueError):
            continue
    return current


def default_config_path() -> Path:
    return Path(__file__).with_name(CONFIG_FILE_NAME)


def load_default_config() -> AppConfig:
    """Load user-facing defaults from ``main-config.json``.

    Dataclass defaults remain a fail-safe if the packaged JSON is missing or
    malformed. Secrets and runtime-only fields stay out of this file and are
    defined here in code.
    """
    config = AppConfig()
    path = default_config_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("main-config.json must be a JSON object")
        _apply(AppConfig, config, payload)
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return config


class SettingsStore:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.path = paths.settings
        self._lock = threading.RLock()
        self._config = AppConfig()
        self._secret_store = None
        self._loaded = False

    @property
    def config(self) -> AppConfig:
        with self._lock:
            if not self._loaded:
                self.load()
            return self._config

    def _secrets(self):
        if self._secret_store is None:
            from aideskpal.utils.secrets import SecretStore

            self._secret_store = SecretStore(self.paths.secrets)
        return self._secret_store

    def load(self) -> AppConfig:
        with self._lock:
            config = load_default_config()
            if not config.model.pmx_path:
                config.model.pmx_path = default_pmx_path(self.paths.root)
            if self.path.is_file():
                try:
                    payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
                    _apply(AppConfig, config, payload)
                    config.version = CONFIG_VERSION
                except (OSError, json.JSONDecodeError):
                    # Keep the corrupted file for the user instead of overwriting silently.
                    try:
                        self.path.replace(self.path.with_suffix(".broken.json"))
                    except OSError:
                        pass
            try:
                secrets = self._secrets().all()
                config.ai.api_key = secrets.get("ai_api_key", "")
                config.memory.api_key = secrets.get("memory_embedding_api_key", "")
                config.market.session_cookie = secrets.get("market_session", "")
            except Exception:
                pass
            if not config.model.pmx_path:
                config.model.pmx_path = default_pmx_path(self.paths.root)
            if "sample_content" in Path(config.model.pmx_path).parts:
                config.model.id = "starling"
                config.model.actions_model_id = "starling"
                config.model.name = "星灵·露米"
            try:
                config.window.pet_scale = min(1.5, max(0.5, float(config.window.pet_scale)))
            except (TypeError, ValueError):
                config.window.pet_scale = 1.0
            self._config = config
            self._loaded = True
            return config

    def save(self, config: AppConfig | None = None) -> None:
        with self._lock:
            if config is not None:
                self._config = config
            self.paths.ensure()
            payload = self._config.to_dict()
            payload["version"] = CONFIG_VERSION
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            os.replace(temporary, self.path)
            try:
                self._secrets().update(
                    {
                        "ai_api_key": self._config.ai.api_key,
                        "memory_embedding_api_key": self._config.memory.api_key,
                        "market_session": self._config.market.session_cookie,
                    }
                )
            except Exception:
                # The settings still save; the UI reports the secret-store problem.
                pass

    def set_api_key(self, key: str) -> None:
        self.config.ai.api_key = key.strip()
        self.save()

    def mark_good(self) -> None:
        self.config.first_run = False
        self.save()
