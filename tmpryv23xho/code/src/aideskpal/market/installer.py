"""Safe installation of market ZIPs (bundles and plugins)."""

from __future__ import annotations

import json
import logging

import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from aideskpal.ai.character import CharacterError, load_character_file
from aideskpal.character_store import CharacterStore
from aideskpal.paths import AppPaths
from aideskpal.plugins.manifest import PluginError, PluginManifest

logger = logging.getLogger(__name__)

MAX_ZIP_BYTES = 512 * 1024 * 1024
MAX_UNCOMPRESSED = 1024 * 1024 * 1024
MAX_FILES = 6000
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


class InstallError(RuntimeError):
    pass


@dataclass(slots=True)
class InstalledBundle:
    id: str
    name: str
    version: str
    path: Path
    pmx_path: Path
    actions_dir: Path
    model_id: str
    cover_path: Path | None = None
    description: str = ""
    installed_at: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class BundleInstaller:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.character_store = CharacterStore(paths)

    # ------------------------------------------------------------------ paths
    @property
    def registry_path(self) -> Path:
        return self.paths.market_bundles / "installed.json"

    def list_installed(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if self.registry_path.is_file():
            try:
                data = json.loads(self.registry_path.read_text(encoding="utf-8"))
                items = list(data.get("bundles", [])) if isinstance(data, dict) else []
            except (OSError, json.JSONDecodeError):
                items = []
        known_paths = {str(Path(str(item.get("path", "")))) for item in items}
        for install in self.character_store.list():
            path = str(install.directory)
            if path in known_paths:
                continue
            items.append(
                {
                    "id": install.model_id,
                    "name": install.name,
                    "version": "1.0.0",
                    "model_id": install.model_id,
                    "path": path,
                    "pmx_path": str(install.pmx_path),
                    "actions_dir": str(install.actions_dir),
                    "description": "",
                    "installed_at": 0.0,
                    "source": "character",
                }
            )
        return items

    def _save_registry(self, items: list[dict[str, Any]]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.registry_path.with_suffix(".tmp")
        temp.write_text(json.dumps({"bundles": items}, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.registry_path)

    # ------------------------------------------------------------------ install
    def install_bundle(self, archive: Path, *, expected_id: int | None = None) -> InstalledBundle:
        archive = Path(archive)
        if not archive.is_file():
            raise InstallError("下载文件不存在")
        if archive.stat().st_size > MAX_ZIP_BYTES:
            raise InstallError("资源包过大")
        with tempfile.TemporaryDirectory(prefix="aideskpal-bundle-") as temp_dir:
            root = Path(temp_dir) / "extract"
            self._safe_extract(archive, root)
            base = self._find_bundle_root(root)
            manifest = self._read_manifest(base)
            if manifest.get("kind") not in (None, "model_action_bundle"):
                raise InstallError("资源包类型不是 model_action_bundle")
            model_id = str(manifest.get("model_id") or manifest.get("id") or "").strip()
            if not SAFE_ID.match(model_id):
                raise InstallError("bundle.json 缺少合法的 model id")
            model_info = manifest.get("model") or {}
            pmx_rel = str(model_info.get("pmx") or manifest.get("pmx") or "model/model.pmx")
            pmx_path = self._safe_child(base, pmx_rel)
            if not pmx_path.is_file():
                raise InstallError(f"找不到 PMX 文件：{pmx_rel}")
            if pmx_path.read_bytes()[:4] != b"PMX ":
                raise InstallError("模型文件不是有效的 PMX")
            action_files = self._action_files(base, manifest)
            for action_file in action_files:
                try:
                    action = json.loads(action_file.read_text(encoding="utf-8-sig"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise InstallError(f"动作文件无效：{action_file.name}") from exc
                if not isinstance(action, dict):
                    raise InstallError("动作文件必须是 JSON 对象")
                if str(action.get("model", "")) != model_id:
                    raise InstallError(
                        f"动作 {action_file.name} 的 model 与 bundle 的模型 id 不一致"
                    )
                for field in ("id", "description", "content"):
                    if field not in action:
                        raise InstallError(f"动作 {action_file.name} 缺少字段 {field}")
            character_rel = str(manifest.get("character") or "character.json")
            character_path = self._safe_child(base, character_rel)
            if not character_path.is_file():
                raise InstallError("资源包缺少角色设定 character.json")
            try:
                profile = load_character_file(character_path)
            except CharacterError as exc:
                raise InstallError(f"角色设定无效：{exc}") from exc
            if profile.model != model_id:
                raise InstallError("character.json 的 model 与 bundle 的模型 id 不一致")
            version = str(manifest.get("version", "1.0.0"))
            profile_install = self.character_store.install_bundle(
                base,
                pmx_relative=pmx_rel,
                display_name=str(manifest.get("name") or "").strip() or None,
                model_id=model_id,
            )
            target = profile_install.directory
            installed = InstalledBundle(
                id=str(manifest.get("id", model_id)),
                name=str(manifest.get("name", model_id))[:120],
                version=version,
                path=target,
                pmx_path=profile_install.pmx_path,
                actions_dir=profile_install.actions_dir,
                model_id=model_id,
                cover_path=(
                    target / str(manifest["cover"])
                    if manifest.get("cover") and (target / str(manifest["cover"])).is_file()
                    else None
                ),
                description=str(manifest.get("description", ""))[:1000],
                installed_at=__import__("time").time(),
                raw=manifest,
            )
            items = [
                item for item in self.list_installed() if item.get("model_id") != model_id
            ]
            items.append(
                {
                    "id": installed.id,
                    "name": installed.name,
                    "version": installed.version,
                    "model_id": model_id,
                    "path": str(target),
                    "pmx_path": str(installed.pmx_path),
                    "actions_dir": str(installed.actions_dir),
                    "description": installed.description,
                    "installed_at": installed.installed_at,
                    "source": "market",
                }
            )
            self._save_registry(items)
            logger.info("Installed bundle %s %s", installed.name, version)
            return installed

    def install_plugin(self, archive: Path) -> PluginManifest:
        archive = Path(archive)
        if not archive.is_file():
            raise InstallError("下载文件不存在")
        if archive.stat().st_size > MAX_ZIP_BYTES:
            raise InstallError("插件包过大")
        with tempfile.TemporaryDirectory(prefix="aideskpal-plugin-") as temp_dir:
            root = Path(temp_dir) / "extract"
            self._safe_extract(archive, root)
            base = self._find_plugin_root(root)
            try:
                manifest = PluginManifest.load(base)
            except PluginError as exc:
                raise InstallError(str(exc)) from exc
            target = self.paths.market_plugins / manifest.id
            if target.exists():
                shutil.rmtree(target)
            self.paths.market_plugins.mkdir(parents=True, exist_ok=True)
            shutil.copytree(base, target)
            logger.info("Installed plugin %s %s", manifest.id, manifest.version)
            return PluginManifest.load(target)

    def uninstall_bundle(self, model_id: str) -> None:
        items = [item for item in self.list_installed() if item.get("model_id") != model_id]
        for item in self.list_installed():
            if item.get("model_id") == model_id:
                path = Path(str(item.get("path", "")))
                try:
                    roots = (self.paths.market_bundles.resolve(), self.paths.character_root.resolve())
                    if path.is_dir() and any(root in path.resolve().parents for root in roots):
                        shutil.rmtree(path)
                except OSError:
                    logger.exception("Could not remove bundle directory %s", path)
        self._save_registry(items)

    def uninstall_plugin(self, plugin_id: str) -> bool:
        target = self.paths.market_plugins / plugin_id
        if not target.is_dir():
            return False
        parent = target.resolve().parent
        if parent != self.paths.market_plugins.resolve():
            return False
        shutil.rmtree(target)
        return True

    # ------------------------------------------------------------------ helpers
    def _safe_extract(self, archive: Path, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        total = 0
        try:
            with zipfile.ZipFile(archive) as zf:
                members = zf.infolist()
                if len(members) > MAX_FILES:
                    raise InstallError("ZIP 文件数量异常")
                for info in members:
                    name = info.filename
                    if not name or name.endswith("/"):
                        continue
                    posix = PurePosixPath(name.replace("\\", "/"))
                    if posix.is_absolute() or any(part == ".." for part in posix.parts):
                        raise InstallError("ZIP 包含不安全路径")
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise InstallError("ZIP 不允许包含符号链接")
                    total += info.file_size
                    if total > MAX_UNCOMPRESSED:
                        raise InstallError("ZIP 解压后体积超过上限")
                    destination = (target / Path(*posix.parts)).resolve()
                    if target.resolve() not in destination.parents:
                        raise InstallError("ZIP 路径逃逸")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as source, destination.open("wb") as handle:
                        shutil.copyfileobj(source, handle, length=1024 * 1024)
        except zipfile.BadZipFile as exc:
            raise InstallError("资源包不是有效的 ZIP") from exc

    @staticmethod
    def _read_manifest(base: Path) -> dict[str, Any]:
        path = base / "bundle.json"
        if not path.is_file():
            raise InstallError("bundle.json 不存在")
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InstallError("bundle.json 无法解析") from exc
        if not isinstance(data, dict):
            raise InstallError("bundle.json 必须是对象")
        return data

    @staticmethod
    def _find_bundle_root(root: Path) -> Path:
        if (root / "bundle.json").is_file():
            return root
        candidates = [item for item in root.iterdir() if item.is_dir() and (item / "bundle.json").is_file()]
        if len(candidates) == 1:
            return candidates[0]
        raise InstallError("资源包内找不到 bundle.json")

    @staticmethod
    def _find_plugin_root(root: Path) -> Path:
        if (root / "plugin.json").is_file():
            return root
        candidates = [item for item in root.iterdir() if item.is_dir() and (item / "plugin.json").is_file()]
        if len(candidates) == 1:
            return candidates[0]
        raise InstallError("插件包内找不到 plugin.json")

    @staticmethod
    def _safe_child(base: Path, relative: str) -> Path:
        posix = PurePosixPath(relative.replace("\\", "/"))
        if posix.is_absolute() or any(part == ".." for part in posix.parts):
            raise InstallError("manifest 路径不安全")
        return base.joinpath(*posix.parts)

    def _action_files(self, base: Path, manifest: dict[str, Any]) -> list[Path]:
        declared = manifest.get("actions")
        files: list[Path] = []
        if isinstance(declared, list):
            for relative in declared:
                path = self._safe_child(base, str(relative))
                if path.is_dir():
                    files.extend(sorted(path.rglob("*.json")))
                elif path.suffix.lower() == ".json" and path.is_file():
                    files.append(path)
        if not files:
            actions_dir = base / "actions"
            if not actions_dir.is_dir():
                raise InstallError("资源包缺少 actions 目录")
            files = sorted(actions_dir.rglob("*.json"))
        files = [
            path
            for path in files
            if path.name.lower() not in {"pack.json", "manifest.json", "schema.json"}
        ]
        if not files:
            raise InstallError("资源包没有动作文件")
        return files
