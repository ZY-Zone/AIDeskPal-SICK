"""Per-model character prompt bound next to the action pack.

A model package can ship ``character.json`` at the bundle root or inside its
action folder.  The profile is deliberately data-only: it never grants the AI
new capabilities, and the core system boundaries in ``prompts.py`` still win.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_PROMPT_CHARS = 6000


class CharacterError(ValueError):
    """Raised when a character profile is malformed."""


@dataclass(frozen=True, slots=True)
class CharacterProfile:
    model: str
    id: str
    name: str
    prompt: str
    title: str = ""
    speech_style: str = ""
    greeting: str = ""
    boundaries: tuple[str, ...] = ()
    likes: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    version: str = "1.0.0"
    author: str = ""
    source: Path | None = field(default=None, compare=False)

    def summary(self) -> dict[str, Any]:
        """Compact identity data for the agents' JSON context."""
        return {
            "id": self.id,
            "model": self.model,
            "name": self.name,
            "title": self.title,
            "speech_style": self.speech_style,
            "greeting": self.greeting,
            "boundaries": list(self.boundaries),
        }

    @classmethod
    def from_dict(cls, data: Any, *, source: Path | None = None) -> "CharacterProfile":
        if not isinstance(data, dict):
            raise CharacterError("character.json 必须是对象")
        model = str(data.get("model", "")).strip()
        profile_id = str(data.get("id", model)).strip()
        name = str(data.get("name", "")).strip()
        prompt = str(data.get("prompt", "")).strip()
        if not model:
            raise CharacterError("character.json 缺少 model")
        if not profile_id:
            raise CharacterError("character.json 缺少 id")
        if not name:
            raise CharacterError("character.json 缺少 name")
        if not prompt:
            raise CharacterError("character.json 缺少 prompt")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise CharacterError(f"character prompt 超过 {MAX_PROMPT_CHARS} 字符")
        boundaries = data.get("boundaries", [])
        likes = data.get("likes", [])
        examples = data.get("examples", [])
        if not isinstance(boundaries, list) or not isinstance(likes, list) or not isinstance(examples, list):
            raise CharacterError("boundaries/likes/examples 必须是数组")
        return cls(
            model=model,
            id=profile_id,
            name=name,
            prompt=prompt,
            title=str(data.get("title", "")).strip(),
            speech_style=str(data.get("speech_style", "")).strip(),
            greeting=str(data.get("greeting", "")).strip(),
            boundaries=tuple(str(item).strip() for item in boundaries if str(item).strip()),
            likes=tuple(str(item).strip() for item in likes if str(item).strip()),
            examples=tuple(str(item).strip() for item in examples if str(item).strip()),
            version=str(data.get("version", "1.0.0")).strip() or "1.0.0",
            author=str(data.get("author", "")).strip(),
            source=source,
        )


def load_character_file(path: Path) -> CharacterProfile:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CharacterError(f"无法读取角色设定：{path.name}") from exc
    return CharacterProfile.from_dict(data, source=path)


def find_character(model_id: str, roots: list[Path]) -> CharacterProfile | None:
    """Find the character profile bound to *model_id*.

    Later roots win, mirroring action override order.  A bundle root is also
    checked because a market package normally places ``character.json`` next to
    ``bundle.json`` rather than inside ``actions/``.
    """
    candidates: list[Path] = []
    for root in reversed(roots):
        candidates.extend(
            (
                root / model_id / "character.json",
                root / "character.json",
                root.parent / "character.json",
            )
        )
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()).casefold() if path.exists() else str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            continue
        try:
            profile = load_character_file(path)
        except CharacterError:
            logger.warning("Invalid character profile: %s", path, exc_info=True)
            continue
        if profile.model != model_id:
            logger.warning(
                "Character profile %s belongs to %s, not %s",
                path,
                profile.model,
                model_id,
            )
            continue
        logger.info("Loaded character profile %s (%s)", profile.name, path)
        return profile
    return None
