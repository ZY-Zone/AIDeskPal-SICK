"""Action playback with cross-fades and non-destructive overlays."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from aideskpal.animation.action import ActionClip
from aideskpal.pmx.skeleton import Pose, slerp

IDENTITY = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
_ANY_BONE = -1


def blend_poses(a: Pose, b: Pose, weight: float) -> Pose:
    """Blend all channels of two poses.  Missing channels use rest values."""
    weight = float(np.clip(weight, 0.0, 1.0))
    out = Pose.empty()
    for bone in set(a.rotations) | set(b.rotations):
        qa = a.rotations.get(bone, IDENTITY)
        qb = b.rotations.get(bone, IDENTITY)
        if np.allclose(qa, qb):
            out.rotations[bone] = qa.copy()
        else:
            out.rotations[bone] = slerp(qa, qb, weight)
    for bone in set(a.translations) | set(b.translations):
        va = a.translations.get(bone, np.zeros(3, dtype=np.float32))
        vb = b.translations.get(bone, np.zeros(3, dtype=np.float32))
        out.translations[bone] = (va * (1.0 - weight) + vb * weight).astype(np.float32)
    for morph in set(a.morphs) | set(b.morphs):
        va = a.morphs.get(morph, 0.0)
        vb = b.morphs.get(morph, 0.0)
        out.morphs[morph] = va * (1.0 - weight) + vb * weight
    return out


@dataclass(slots=True)
class PlaybackState:
    action_id: str | None = None
    time: float = 0.0
    loop: bool = False
    finished: bool = False


class ActionPlayer:
    """Deterministic action player used by the renderer and unit tests.

    The player deliberately contains no Qt code.  The UI drives it with a timer.
    """

    def __init__(self, clips: dict[str, ActionClip] | None = None, idle_id: str | None = None) -> None:
        self.clips = clips or {}
        self.idle_id = idle_id
        self._clip: ActionClip | None = None
        self._previous: ActionClip | None = None
        self._previous_pose: Pose | None = None
        self._time = 0.0
        self._previous_time = 0.0
        self._fade_duration = 0.0
        self._fade_elapsed = 0.0
        self._finished = False
        self._advanced_after_finish = 0.0
        self.on_finished: Callable[[str], None] | None = None
        self._last_pose = Pose.empty()
        self._overlays: list[tuple[Pose, float]] = []

    # ------------------------------------------------------------------ state
    @property
    def current(self) -> ActionClip | None:
        return self._clip

    @property
    def current_id(self) -> str | None:
        return self._clip.id if self._clip else None

    @property
    def time(self) -> float:
        """Current clip-local time used by contact-constraint projection."""
        return self._time

    @property
    def progress(self) -> float:
        if not self._clip or self._clip.duration <= 0:
            return 0.0
        return (self._time % self._clip.duration) / self._clip.duration

    @property
    def is_finished(self) -> bool:
        return self._finished

    def set_clips(self, clips: dict[str, ActionClip], idle_id: str | None = None) -> None:
        self.clips = clips
        if idle_id is not None:
            self.idle_id = idle_id
        if self._clip and self._clip.id not in clips:
            self._clip = None

    # ------------------------------------------------------------------ control
    def play(
        self,
        action_id: str,
        *,
        fade: float | None = None,
        restart: bool = False,
        overlay_weight: float = 1.0,
    ) -> bool:
        clip = self.clips.get(action_id)
        if clip is None:
            return False
        if self._clip and self._clip.id == action_id and not restart and not self._finished:
            return True
        outgoing = self._clip
        # An interrupted fade must start at the composite currently on screen,
        # not at the (only partially visible) incoming clip. Keep overlays out
        # of this snapshot: they are applied separately and cleared below.
        interrupted = self._previous is not None or self._previous_pose is not None
        self._previous_pose = self._base_pose() if interrupted else None
        self._previous = None if interrupted else outgoing
        self._previous_time = self._time
        self._clip = clip
        self._time = 0.0
        self._finished = False
        self._advanced_after_finish = 0.0
        # With no explicit override, allow both clips their requested settling
        # time. Explicit fade=0 still provides an immediate cut.
        default_fade = max(clip.fade_in, outgoing.fade_out if outgoing else 0.0)
        self._fade_duration = max(0.0, default_fade if fade is None else float(fade))
        self._fade_elapsed = 0.0
        if self._fade_duration <= 0.0:
            self._previous = None
            self._previous_pose = None
        self._overlays.clear()
        return True

    def play_idle(self, *, fade: float | None = None, force: bool = False) -> bool:
        if not self.idle_id:
            return False
        if not force and self._clip and self._clip.id == self.idle_id:
            return True
        return self.play(self.idle_id, fade=fade)

    def add_overlay(self, pose: Pose, weight: float = 1.0) -> None:
        self._overlays = [(pose, float(np.clip(weight, 0.0, 1.0)))]

    def clear_overlays(self) -> None:
        self._overlays.clear()

    def stop(self) -> None:
        self._clip = None
        self._previous = None
        self._previous_pose = None
        self._time = 0.0
        self._finished = False
        self._overlays.clear()

    # ------------------------------------------------------------------ update
    def update(self, dt: float) -> Pose:
        dt = max(0.0, min(float(dt), 0.25))
        if self._clip is None:
            if self.idle_id and self.idle_id in self.clips:
                self.play(self.idle_id, fade=0.0)
            else:
                return Pose.empty()

        assert self._clip is not None
        # Transition clocks must keep running even after a short clip finishes.
        if self._fade_elapsed < self._fade_duration:
            self._fade_elapsed = min(self._fade_duration, self._fade_elapsed + dt)
        if not self._finished:
            self._time += dt
            if not self._clip.loop and self._time >= self._clip.duration:
                self._finished = True
                self._time = self._clip.duration
                if self.on_finished:
                    self.on_finished(self._clip.id)
        else:
            self._advanced_after_finish += dt

        # Keep the outgoing clip moving during the cross-fade.  Freezing it at
        # the transition time made short actions look like they paused before
        # the new motion started.
        if self._previous is not None and self._fade_duration > 0:
            self._previous_time += dt
            previous_duration = max(0.0, self._previous.duration)
            if previous_duration > 0:
                if self._previous.loop:
                    self._previous_time %= previous_duration
                else:
                    self._previous_time = min(self._previous_time, previous_duration)

        pose = self.pose()
        if self._fade_elapsed >= self._fade_duration:
            self._previous = None
            self._previous_pose = None
        self._last_pose = pose
        return pose

    def seek(self, time: float) -> None:
        self._time = max(0.0, float(time))
        self._finished = False

    def _base_pose(self) -> Pose:
        """Evaluate the current transition without advancing or adding overlays."""
        if self._clip is None:
            return Pose.empty()
        pose = self._clip.sample(self._time)
        previous_pose = self._previous_pose
        if self._previous is not None:
            previous_pose = self._previous.sample(self._previous_time)
        if previous_pose is not None and self._fade_duration > 0:
            raw_alpha = min(1.0, self._fade_elapsed / self._fade_duration)
            if raw_alpha >= 1.0:
                return pose
            alpha = raw_alpha * raw_alpha * (3.0 - 2.0 * raw_alpha)
            pose = blend_poses(previous_pose, pose, alpha)
        return pose

    def pose(self) -> Pose:
        """Evaluate the same blended pose as update(), without advancing time."""
        if self._clip is None:
            return Pose.empty()
        pose = self._base_pose()
        for overlay, weight in self._overlays:
            pose.blend_into(overlay, weight)
        return pose
