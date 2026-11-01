"""Action pack format and sampling.

An action is a small JSON document with:
  * ``model``       — model/profile id the action was authored for
  * ``id``          — stable id used by the AI actor
  * ``content``     — detailed bone / morph keyframes
  * ``description`` — natural-language description shown to the AI

See ``docs/action-authoring.md`` for the full schema.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from aideskpal.animation.easing import apply_easing
from aideskpal.animation.curves import (
    hermite, vector_tangent, quaternion_tangent, spherical_cubic,
)
from aideskpal.pmx.model import PmxModel
from aideskpal.pmx.skeleton import Pose, quat_from_euler_xyz, slerp

SCHEMA_VERSION = "1.0"
IDENTITY = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)


class ActionError(ValueError):
    """Raised for an invalid action document."""


@dataclass(slots=True)
class BoneTrack:
    bone_name: str
    bone_index: int
    rotation_times: np.ndarray
    rotations: list[np.ndarray]
    rotation_easings: list[str]
    translation_times: np.ndarray
    translations: list[np.ndarray]
    translation_easings: list[str]


@dataclass(slots=True)
class MorphTrack:
    morph_name: str
    morph_index: int
    times: np.ndarray
    weights: np.ndarray
    easings: list[str]


@dataclass(slots=True)
class ActionClip:
    id: str
    model: str
    name: str
    description: str
    content: dict[str, Any]
    duration: float
    loop: bool
    category: str = "idle"
    tags: tuple[str, ...] = ()
    priority: int = 50
    fade_in: float = 0.35
    fade_out: float = 0.35
    ai_visible: bool = True
    source: Path | None = None
    version: str = "1.0.0"
    author: str = ""
    bone_tracks: list[BoneTrack] = field(default_factory=list, repr=False)
    morph_tracks: list[MorphTrack] = field(default_factory=list, repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def sample(self, time: float) -> Pose:
        if self.duration <= 0:
            t = 0.0
        elif self.loop:
            t = float(time % self.duration)
        else:
            t = float(np.clip(time, 0.0, self.duration))
        pose = Pose.empty()
        for track in self.bone_tracks:
            if len(track.rotation_times):
                pose.rotations[track.bone_index] = _sample_quat_track(
                    track.rotation_times,
                    track.rotations,
                    track.rotation_easings,
                    t,
                    loop=self.loop,
                    duration=self.duration,
                )
            if len(track.translation_times):
                pose.translations[track.bone_index] = _sample_vec_track(
                    track.translation_times,
                    track.translations,
                    track.translation_easings,
                    t,
                    loop=self.loop,
                    duration=self.duration,
                )
        for track in self.morph_tracks:
            if len(track.times):
                pose.morphs[track.morph_index] = _sample_scalar_track(
                    track.times,
                    track.weights,
                    track.easings,
                    t,
                    loop=self.loop,
                    duration=self.duration,
                )
        return pose

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "model": self.model,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tags": list(self.tags),
            "duration": round(self.duration, 3),
            "loop": self.loop,
            "priority": self.priority,
        }


def _as_float(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ActionError(f"{context} must be a number") from exc
    if not math.isfinite(result):
        raise ActionError(f"{context} must be finite")
    return result


def _ease_at(easings: list[str], index: int) -> str:
    if not easings:
        return "smooth"
    return easings[min(index, len(easings) - 1)]


def _find_segment(times: np.ndarray, t: float) -> tuple[int, int, float]:
    if len(times) == 1 or t <= times[0]:
        return 0, 0, 0.0
    if t >= times[-1]:
        return len(times) - 1, len(times) - 1, 0.0
    right = int(np.searchsorted(times, t, side="right"))
    left = max(0, right - 1)
    span = float(times[right] - times[left])
    u = 0.0 if span <= 1e-9 else (t - float(times[left])) / span
    return left, right, u


def _sample_scalar_track(
    times: np.ndarray, values: np.ndarray, easings: list[str], t: float, *, loop: bool, duration: float
) -> float:
    left, right, u = _find_segment(times, t)
    if left == right:
        return float(values[left])
    if _ease_at(easings, left) == "flow":
        span = float(times[right]-times[left])
        return float(hermite(values[left], values[right],
            vector_tangent(times, values, left, loop, duration),
            vector_tangent(times, values, right, loop, duration), u, span))
    eased = apply_easing(_ease_at(easings, left), u)
    return float(values[left] * (1.0 - eased) + values[right] * eased)


def _sample_vec_track(
    times: np.ndarray,
    values: list[np.ndarray],
    easings: list[str],
    t: float,
    *,
    loop: bool,
    duration: float,
) -> np.ndarray:
    left, right, u = _find_segment(times, t)
    if left == right or np.array_equal(values[left], values[right]):
        return values[left].copy()
    if _ease_at(easings, left) == "flow":
        span = float(times[right]-times[left])
        return np.asarray(hermite(values[left], values[right],
            vector_tangent(times, values, left, loop, duration),
            vector_tangent(times, values, right, loop, duration), u, span), dtype=np.float32)
    eased = apply_easing(_ease_at(easings, left), u)
    return values[left] * (1.0 - eased) + values[right] * eased


def _sample_quat_track(
    times: np.ndarray,
    quats: list[np.ndarray],
    easings: list[str],
    t: float,
    *,
    loop: bool,
    duration: float,
) -> np.ndarray:
    left, right, u = _find_segment(times, t)
    if left == right or np.array_equal(quats[left], quats[right]) or np.array_equal(quats[left], -quats[right]):
        return quats[left].copy()
    if _ease_at(easings, left) == "flow":
        span = float(times[right]-times[left])
        return spherical_cubic(quats[left], quats[right],
            quaternion_tangent(times, quats, left, loop, duration),
            quaternion_tangent(times, quats, right, loop, duration), u, span, slerp)
    eased = apply_easing(_ease_at(easings, left), u)
    return slerp(quats[left], quats[right], eased)


def _parse_keys(
    keys: Any, context: str, allowed: set[str]
) -> list[dict[str, Any]]:
    if not isinstance(keys, list) or not keys:
        raise ActionError(f"{context} must be a non-empty list")
    parsed: list[dict[str, Any]] = []
    last_time = -math.inf
    for index, key in enumerate(keys):
        if not isinstance(key, dict):
            raise ActionError(f"{context}[{index}] must be an object")
        if "t" not in key:
            raise ActionError(f"{context}[{index}] is missing 't'")
        t = _as_float(key["t"], f"{context}[{index}].t")
        if t < 0 or not math.isfinite(t):
            raise ActionError(f"{context}[{index}].t must be a finite non-negative value")
        if t <= last_time:
            raise ActionError(f"{context} keys must have strictly increasing times")
        last_time = t
        if not any(field in key for field in allowed):
            raise ActionError(f"{context}[{index}] needs one of {sorted(allowed)}")
        parsed.append(key)
    return parsed


def _resolve_track_bone(model: PmxModel, name: str) -> int:
    index = model.bone_index(name)
    if index < 0:
        # Unknown bones are a soft error: actions can target several model variants.
        return -1
    return index


def _build_bone_track(
    model: PmxModel, bone_name: str, data: Any, context: str
) -> BoneTrack | None:
    if not isinstance(data, dict):
        raise ActionError(f"{context} must be an object")
    bone_index = _resolve_track_bone(model, bone_name)
    rotation_keys = data.get("rotation", data.get("rot", []))
    translation_keys = data.get("translation", data.get("trans", []))
    if not rotation_keys and not translation_keys:
        return None
    rot_times: list[float] = []
    rot_values: list[np.ndarray] = []
    rot_easings: list[str] = []
    parsed_rotations = (
        _parse_keys(rotation_keys, f"{context}.rotation", {"rot", "rotation"})
        if rotation_keys
        else []
    )
    for i, key in enumerate(parsed_rotations):
        t = _as_float(key["t"], f"{context}.rotation[{i}].t")
        raw = key.get("rot", key.get("rotation"))
        if not isinstance(raw, list) or len(raw) != 3:
            raise ActionError(f"{context}.rotation[{i}] must be [x, y, z] in degrees")
        for axis, value in zip("xyz", raw):
            _as_float(value, f"{context}.rotation[{i}].{axis}")
        rot_times.append(t)
        rot_values.append(quat_from_euler_xyz([float(v) for v in raw]))
        rot_easings.append(str(key.get("ease", "smooth")))
    trans_times: list[float] = []
    trans_values: list[np.ndarray] = []
    trans_easings: list[str] = []
    parsed_translations = (
        _parse_keys(translation_keys, f"{context}.translation", {"trans", "translation"})
        if translation_keys
        else []
    )
    for i, key in enumerate(parsed_translations):
        t = _as_float(key["t"], f"{context}.translation[{i}].t")
        raw = key.get("trans", key.get("translation"))
        if not isinstance(raw, list) or len(raw) != 3:
            raise ActionError(f"{context}.translation[{i}] must be [x, y, z]")
        trans_times.append(t)
        trans_values.append(np.asarray([
            _as_float(v, f"{context}.translation[{i}]") for v in raw
        ], dtype=np.float32))
        trans_easings.append(str(key.get("ease", "smooth")))
    if not rot_times and not trans_times:
        return None
    return BoneTrack(
        bone_name=bone_name,
        bone_index=bone_index,
        rotation_times=np.asarray(rot_times, dtype=np.float32),
        rotations=rot_values,
        rotation_easings=rot_easings,
        translation_times=np.asarray(trans_times, dtype=np.float32),
        translations=trans_values,
        translation_easings=trans_easings,
    )


def _build_morph_track(
    model: PmxModel, morph_name: str, keys: Any, context: str
) -> MorphTrack | None:
    morph_index = model.morph_by_name.get(morph_name, -1)
    if morph_index < 0:
        return None
    if not isinstance(keys, list) or not keys:
        return None
    times: list[float] = []
    weights: list[float] = []
    easings: list[str] = []
    for i, key in enumerate(keys):
        if not isinstance(key, dict) or "t" not in key:
            raise ActionError(f"{context}[{i}] must be an object with 't'")
        t = _as_float(key["t"], f"{context}[{i}].t")
        if t < 0 or (times and t <= times[-1]):
            raise ActionError(f"{context} needs nonnegative strictly increasing times")
        w = _as_float(key.get("w", key.get("weight", 0.0)), f"{context}[{i}].w")
        times.append(t)
        weights.append(max(0.0, min(1.0, w)))
        easings.append(str(key.get("ease", "smooth")))
    order = np.argsort(np.asarray(times, dtype=np.float32), kind="stable")
    return MorphTrack(
        morph_name=morph_name,
        morph_index=morph_index,
        times=np.asarray(times, dtype=np.float32)[order],
        weights=np.asarray(weights, dtype=np.float32)[order],
        easings=[easings[i] for i in order],
    )


def parse_action(data: dict[str, Any], model: PmxModel, source: Path | None = None) -> ActionClip:
    if not isinstance(data, dict):
        raise ActionError("action document must be a JSON object")
    missing = [key for key in ("model", "id", "content", "description") if key not in data]
    if missing:
        raise ActionError(f"missing required field(s): {', '.join(missing)}")
    if data.get("schema_version", SCHEMA_VERSION) not in (SCHEMA_VERSION, "1.0.0"):
        raise ActionError(f"unsupported schema_version {data.get('schema_version')!r}")
    action_id = str(data["id"]).strip()
    if not action_id or not all(ch.isalnum() or ch in "_-" for ch in action_id):
        raise ActionError("id may contain only letters, digits, '_' and '-'")
    content = data["content"]
    if not isinstance(content, dict):
        raise ActionError("content must be an object")
    if not content.get("bones") and not content.get("morphs"):
        raise ActionError("content must contain at least one bone or morph track")
    duration = _as_float(content.get("duration", data.get("duration", 0.0)), "duration")
    if duration <= 0:
        # Infer from the largest keyframe time.
        maximum = 0.0
        for track in (content.get("bones") or {}).values():
            if isinstance(track, dict):
                for keys in track.values():
                    if isinstance(keys, list) and keys:
                        maximum = max(maximum, float(keys[-1].get("t", 0)))
        for keys in (content.get("morphs") or {}).values():
            if isinstance(keys, list) and keys:
                maximum = max(maximum, float(keys[-1].get("t", 0)))
        duration = maximum if maximum > 0 else 2.0
    loop = bool(content.get("loop", data.get("loop", False)))
    clip = ActionClip(
        id=action_id,
        model=str(data["model"]).strip(),
        name=str(data.get("name", action_id)),
        description=str(data["description"]).strip(),
        content=content,
        duration=duration,
        loop=loop,
        category=str(data.get("category", "idle")),
        tags=tuple(str(tag) for tag in data.get("tags", [])),
        priority=int(data.get("priority", 50)),
        fade_in=float(content.get("fade_in", data.get("fade_in", 0.35))),
        fade_out=float(content.get("fade_out", data.get("fade_out", 0.35))),
        ai_visible=bool(data.get("ai_visible", True)),
        source=source,
        version=str(data.get("version", "1.0.0")),
        author=str(data.get("author", "")),
        raw=data,
    )
    if not clip.description:
        raise ActionError("description must not be empty (it is the AI-facing contract)")
    for bone_name, track in (content.get("bones") or {}).items():
        built = _build_bone_track(model, str(bone_name), track, f"content.bones.{bone_name}")
        if built is not None and built.bone_index >= 0:
            clip.bone_tracks.append(built)
    for morph_name, keys in (content.get("morphs") or {}).items():
        built_morph = _build_morph_track(
            model, str(morph_name), keys, f"content.morphs.{morph_name}"
        )
        if built_morph is not None:
            clip.morph_tracks.append(built_morph)
    return clip


def load_action(path: str | Path, model: PmxModel) -> ActionClip:
    file_path = Path(path)
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ActionError(f"cannot read {file_path.name}: {exc}") from exc
    return parse_action(raw, model, file_path)


class ActionLibrary:
    """Discovers actions in one or more directories, grouped by model id."""

    def __init__(self, roots: list[Path] | None = None) -> None:
        self._roots = [Path(root) for root in roots or []]
        self._actions: dict[str, dict[str, ActionClip]] = {}
        self.errors: list[dict[str, str]] = []

    @property
    def actions(self) -> dict[str, dict[str, ActionClip]]:
        return self._actions

    def load(self, model: PmxModel) -> int:
        self._actions = {}
        self.errors = []
        files: list[Path] = []
        for root in self._roots:
            if root.is_dir():
                files.extend(sorted(root.rglob("*.json")))
        loaded = 0
        seen: set[tuple[str, str]] = set()
        for path in files:
            if path.name.lower() in {"manifest.json", "pack.json", "schema.json"}:
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as exc:
                self.errors.append({"file": str(path), "error": str(exc)})
                continue
            if not isinstance(raw, dict) or "id" not in raw or "content" not in raw:
                continue
            try:
                clip = parse_action(raw, model, path)
            except ActionError as exc:
                self.errors.append({"file": str(path), "error": str(exc)})
                continue
            key = (clip.model, clip.id)
            if key in seen:
                # Later roots (user actions) deliberately override bundled actions.
                self.errors.append(
                    {"file": str(path), "error": f"duplicate action {clip.id}; overridden"}
                )
            seen.add(key)
            self._actions.setdefault(clip.model, {})[clip.id] = clip
            loaded += 1
        return loaded

    def merge_external(self, clips: list[ActionClip]) -> None:
        for clip in clips:
            self._actions.setdefault(clip.model, {})[clip.id] = clip

    def get(self, action_id: str, model_id: str | None = None) -> ActionClip | None:
        if model_id:
            return self._actions.get(model_id, {}).get(action_id)
        for actions in self._actions.values():
            if action_id in actions:
                return actions[action_id]
        return None

    def for_model(self, model_id: str) -> list[ActionClip]:
        return sorted(
            self._actions.get(model_id, {}).values(), key=lambda clip: (clip.category, clip.id)
        )

    def catalog(self, model_id: str, include_hidden: bool = False) -> list[dict[str, Any]]:
        return [
            clip.summary()
            for clip in self.for_model(model_id)
            if (include_hidden or clip.ai_visible)
        ]
