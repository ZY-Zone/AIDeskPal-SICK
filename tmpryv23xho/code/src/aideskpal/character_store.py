"""Self-contained character package storage.

A character owns its PMX, action JSON and character prompt under
``<character_root>/<display name>/``.  The rest of the app only sees the paths
returned by this module; no model/action/prompt path is persisted separately.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aideskpal.ai.character import CharacterError, CharacterProfile, load_character_file
from aideskpal.paths import AppPaths

logger = logging.getLogger(__name__)

_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(slots=True)
class CharacterInstall:
    name: str
    directory: Path
    pmx_path: Path
    actions_dir: Path
    character_path: Path
    model_id: str
    raw: dict[str, Any] | None = None


def safe_character_name(value: str, fallback: str = "character") -> str:
    name = _INVALID_NAME.sub("_", (value or "").strip()).strip(" .")
    name = re.sub(r"\s+", " ", name)[:60].strip(" .")
    return name or fallback


class CharacterStore:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.root = paths.character_root
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[CharacterInstall]:
        found: list[CharacterInstall] = []
        if not self.root.is_dir():
            return found
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            install = self._from_directory(directory)
            if install is not None:
                found.append(install)
        return found

    def find_by_model_id(self, model_id: str) -> CharacterInstall | None:
        for install in self.list():
            if install.model_id == model_id:
                return install
        return None

    def _from_directory(self, directory: Path) -> CharacterInstall | None:
        character_path = directory / "character.json"
        if not character_path.is_file():
            return None
        try:
            profile = load_character_file(character_path)
        except CharacterError:
            logger.warning("Ignoring invalid character package: %s", directory, exc_info=True)
            return None
        pmx_path = next(
            (
                candidate
                for candidate in (
                    directory / "model.pmx",
                    directory / "model" / "model.pmx",
                )
                if candidate.is_file()
            ),
            None,
        )
        if pmx_path is None:
            logger.warning("Character package has no PMX: %s", directory)
            return None
        actions_dir = directory / "actions"
        if not actions_dir.is_dir():
            actions_dir = directory
        return CharacterInstall(
            name=profile.name or directory.name,
            directory=directory,
            pmx_path=pmx_path,
            actions_dir=actions_dir,
            character_path=character_path,
            model_id=profile.model,
        )

    def _target(self, name: str, model_id: str) -> Path:
        candidate = self.root / safe_character_name(name, model_id)
        if candidate.is_dir() and candidate.exists():
            existing = self._from_directory(candidate)
            if existing is not None and existing.model_id != model_id:
                candidate = self.root / safe_character_name(f"{name} ({model_id})", model_id)
        return candidate

    def _commit(self, staging: Path, target: Path) -> None:
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(target)

    def install_local(
        self,
        pmx_path: Path,
        actions_source: Path,
        *,
        character_path: Path | None = None,
        display_name: str | None = None,
    ) -> CharacterInstall:
        """Copy a local PMX + action pack + prompt into one self-contained folder."""
        pmx_path = Path(pmx_path)
        actions_source = Path(actions_source)
        if not pmx_path.is_file():
            raise CharacterError("PMX 文件不存在")
        if not actions_source.is_dir():
            raise CharacterError("找不到与该模型配套的动作目录")
        character_path = Path(character_path) if character_path else actions_source / "character.json"
        if not character_path.is_file():
            character_path = actions_source.parent / "character.json"
        if not character_path.is_file():
            raise CharacterError("找不到与该模型配套的 character.json")
        profile = load_character_file(character_path)
        name = display_name or profile.name or pmx_path.stem
        target = self._target(name, profile.model)
        staging = self.root / f".{target.name}.installing"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        try:
            shutil.copy2(pmx_path, staging / "model.pmx")
            # PMX materials usually reference textures/SPA/toon files relative
            # to the PMX directory. Copy the whole model asset set, not just
            # the .pmx file, or the model renders white.
            pmx_parent = pmx_path.parent
            for asset in pmx_parent.rglob("*"):
                if not asset.is_file():
                    continue
                relative = asset.relative_to(pmx_parent)
                if relative.as_posix() == "model.pmx":
                    continue
                if relative.parts and relative.parts[0] in {"actions", ".git"}:
                    continue
                if asset.name in {"character.json", "pack.json", "bundle.json"}:
                    continue
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(asset, destination)
            (staging / "actions").mkdir()
            for source in actions_source.rglob("*.json"):
                relative = source.relative_to(actions_source)
                if source.name in {"character.json", "pack.json"}:
                    continue
                destination = staging / "actions" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            pack = actions_source / "pack.json"
            if pack.is_file():
                shutil.copy2(pack, staging / "pack.json")
            shutil.copy2(character_path, staging / "character.json")
            self._commit(staging, target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        install = self._from_directory(target)
        if install is None:
            raise CharacterError("角色复制后无法读取")
        logger.info("Installed local character %s -> %s", install.name, target)
        return install

    def install_bundle(
        self,
        bundle_dir: Path,
        *,
        pmx_relative: str,
        display_name: str | None = None,
        model_id: str,
    ) -> CharacterInstall:
        """Copy a validated market bundle tree into a character folder."""
        bundle_dir = Path(bundle_dir)
        character_path = bundle_dir / "character.json"
        if not character_path.is_file():
            raise CharacterError("套装缺少 character.json")
        profile = load_character_file(character_path)
        name = display_name or profile.name or model_id
        target = self._target(name, model_id)
        staging = self.root / f".{target.name}.installing"
        if staging.exists():
            shutil.rmtree(staging)
        try:
            shutil.copytree(bundle_dir, staging)
            self._commit(staging, target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        install = self._from_directory(target)
        if install is None:
            raise CharacterError("套装复制后无法读取")
        # Keep the manifest's PMX location available for callers.
        if not (target / pmx_relative).is_file():
            raise CharacterError("套装复制后找不到 PMX")
        logger.info("Installed character bundle %s -> %s", install.name, target)
        return install
