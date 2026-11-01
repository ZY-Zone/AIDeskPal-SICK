"""Filesystem locations used by the application and plugin API.

The packaged Windows build is portable: it keeps user data in a ``user_data``
folder next to the executable.  This avoids environments where Windows security
policies or an application-control layer deny writing to ``%LOCALAPPDATA%``.
Source checkouts prefer ``%LOCALAPPDATA%`` but fall back to the project's
``user_data`` folder, then the system temp directory.  A directory is only chosen
after an actual write probe, so logging/settings cannot fail later with a raw
PermissionError.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _resource_root() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller unpack directory.
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[2]


def _executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _data_candidates() -> list[Path]:
    override = os.environ.get("AIDESKPAL_DATA_DIR")
    if override:
        return [Path(override).expanduser().resolve()]

    candidates: list[Path] = []
    local_base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    local = Path(local_base) / "AIDeskPal-SICK" if local_base else Path.home() / ".aideskpal-sick"
    if getattr(sys, "frozen", False):
        # Portable first for packaged builds.
        candidates.append(_executable_dir() / "user_data")
        candidates.append(local)
    else:
        candidates.append(local)
        candidates.append(_resource_root() / "user_data")
    candidates.append(Path(tempfile.gettempdir()) / "AIDeskPal-SICK")
    # Remove duplicates while preserving order.
    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key not in seen:
            result.append(candidate)
            seen.add(key)
    return result


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    data: Path
    characters: Path | None = None

    @property
    def character_root(self) -> Path:
        """Self-contained character packages.

        Source checkouts use the requested ``src/aideskpal/character`` folder;
        packaged builds cannot rely on the source tree, so they use the
        writable user-data character directory instead.
        """
        if self.characters is not None:
            return Path(self.characters)
        if getattr(sys, "frozen", False):
            return self.data / "character"
        return self.root / "src" / "aideskpal" / "character"

    @property
    def settings(self) -> Path:
        return self.data / "settings.json"

    @property
    def secrets(self) -> Path:
        return self.data / "secrets.dat"

    @property
    def logs(self) -> Path:
        return self.data / "logs"

    @property
    def plugins(self) -> Path:
        return self.data / "plugins"

    @property
    def bundled_plugins(self) -> Path:
        return self.root / "plugins"

    @property
    def actions(self) -> Path:
        return self.data / "actions"

    @property
    def bundled_actions(self) -> Path:
        return self.root / "actions"

    @property
    def models(self) -> Path:
        return self.data / "models"

    @property
    def bundled_models(self) -> Path:
        return self.root / "models"

    @property
    def market_cache(self) -> Path:
        return self.data / "market" / "cache"

    @property
    def market_bundles(self) -> Path:
        return self.data / "market" / "bundles"

    @property
    def market_plugins(self) -> Path:
        return self.data / "market" / "plugins"

    @property
    def logs_file(self) -> Path:
        return self.logs / "aideskpal.log"

    def ensure(self) -> "AppPaths":
        for path in (
            self.data,
            self.logs,
            self.plugins,
            self.actions,
            self.models,
            self.market_cache,
            self.market_bundles,
            self.market_plugins,
            self.character_root,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self


def _probe_write(directory: Path) -> None:
    probe = directory / ".write_probe"
    with probe.open("w", encoding="utf-8") as handle:
        handle.write("ok")
    probe.unlink(missing_ok=True)


def get_paths() -> AppPaths:
    root = _resource_root()
    last_error: OSError | None = None
    for data_root in _data_candidates():
        try:
            paths = AppPaths(root=root, data=data_root).ensure()
            _probe_write(data_root)
            return paths
        except OSError as exc:
            last_error = exc
            continue
    # This should be nearly impossible (the temp candidate normally works), but
    # never emit a raw traceback to a user just because a data folder is blocked.
    raise OSError(
        "没有可写的数据目录。请把程序放到可写位置，或设置 AIDESKPAL_DATA_DIR 环境变量。"
    ) from last_error
