"""Screen-edge idle behavior and the fall-to-bottom sequence.

The controller only moves the existing transparent pet window and tells the
renderer to roll/zoom the model.  It never rotates the OS window or changes the
model, so click-through and DPI handling stay in one place.
"""

from __future__ import annotations

import logging
import random
from types import SimpleNamespace

import numpy as np

from PySide6.QtCore import QEasingCurve, QObject, QPoint, QRect, QTimer, QVariantAnimation
from PySide6.QtGui import QGuiApplication

from aideskpal.config import AppConfig
from aideskpal.ui.pet_window import PetWindow

logger = logging.getLogger(__name__)

EDGE_ACTIONS = (
    "edge_side_hang",
    "edge_side_hang_right",
    "edge_top_grip",
    "edge_bottom_sit",
    "edge_fall",
    "edge_land_sit",
)

MODE_ACTION = {
    "side_left": "edge_side_hang",
    "side_right": "edge_side_hang_right",
    "top": "edge_top_grip",
    "bottom_sit": "edge_bottom_sit",
    "fall": "edge_fall",
    "land": "edge_land_sit",
}


def projected_bounds(
    points: np.ndarray, matrix: np.ndarray, width: int, height: int
) -> tuple[float, float, float, float]:
    """Return left, top, right and bottom in logical window pixels."""
    clip = np.c_[points, np.ones(len(points))] @ matrix.T
    valid = np.abs(clip[:, 3]) > 1e-8
    if not valid.any():
        raise ValueError("support geometry has no projectable vertices")
    ndc = clip[valid, :2] / clip[valid, 3:4]
    x = (1.0 + ndc[:, 0]) * width * 0.5
    y = (1.0 - ndc[:, 1]) * height * 0.5
    return float(x.min()), float(y.min()), float(x.max()), float(y.max())


def projected_support(points: np.ndarray, matrix: np.ndarray, width: int, height: int) -> tuple[float, float]:
    """Backward-compatible top/bottom projection helper."""
    _, top, _, bottom = projected_bounds(points, matrix, width, height)
    return top, bottom


class EdgeController(QObject):
    """Automatic but conservative screen-edge cycles."""

    def __init__(self, pet: PetWindow, config: AppConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.pet = pet
        self.config = config
        self.mode: str | None = None
        self._cycle_timer = QTimer(self)
        self._cycle_timer.setSingleShot(True)
        self._cycle_timer.timeout.connect(self.next_pose)
        self._fall_timer = QTimer(self)
        self._fall_timer.setSingleShot(True)
        self._fall_timer.timeout.connect(self._fall)
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._settle_bottom)
        self._snap_timer = QTimer(self)
        self._snap_timer.setSingleShot(True)
        self._snap_timer.timeout.connect(self._snap_after_drag)
        self._contact_timer = QTimer(self)
        self._contact_timer.setInterval(100)
        self._contact_timer.timeout.connect(self._align_contact)
        self._support_cache: dict[tuple, tuple[float, float]] = {}
        self._move_animation: QVariantAnimation | None = None
        self._busy = False
        # Position along the current edge, in logical pixels: the window's y for
        # vertical edges, x for horizontal ones.  ``None`` means "not pinned yet"
        # and the mode's default anchor is used.  The axis is stored alongside so
        # a y-coordinate can never be reused as an x-coordinate after a fall.
        self._free: float | None = None
        self._free_axis: str | None = None
        pet.drag_state_changed.connect(self._on_drag_state)
        advanced = getattr(pet, "animation_advanced", None)
        if advanced is not None:
            advanced.connect(self._on_animation_advanced)

    # ------------------------------------------------------------------ setup
    @property
    def enabled(self) -> bool:
        return bool(self.config.window.edge_behaviors) and all(
            action_id in self.pet.actions for action_id in EDGE_ACTIONS
        )

    def start(self, delay: float = 7.0) -> None:
        if not self.enabled:
            if self.config.window.edge_behaviors:
                logger.info("Edge actions unavailable for the current model; edge behavior disabled")
            return
        self._schedule(max(3.0, delay))

    def stop(self) -> None:
        self._cycle_timer.stop()
        self._fall_timer.stop()
        self._settle_timer.stop()
        self._snap_timer.stop()
        self._contact_timer.stop()
        if self._move_animation is not None:
            self._move_animation.stop()
            self._move_animation = None

    def apply_config(self, config: AppConfig) -> None:
        self.stop()
        self._support_cache.clear()
        self.config = config
        if not config.window.edge_behaviors:
            self.stop()
            self._leave_to_normal()
        else:
            if self.mode is not None:
                self.mode = None
                self._busy = False
                self.pet.clear_edge_pose()
            self._schedule(12.0)

    # ------------------------------------------------------------------ state
    def _screen_area(self) -> QRect:
        screen = QGuiApplication.screenAt(self.pet.geometry().center())
        if screen is None:
            screen = QGuiApplication.screenAt(self.pet.position())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            screen = QGuiApplication.screens()[0] if QGuiApplication.screens() else None
        return screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 800)

    def _bottom_support(self) -> tuple[float, float]:
        """Calibrate seated fit/support once per clip, model and viewport.

        A private model is never required: this uses whichever model is loaded.
        The CPU-only projection proxy avoids mutating the live renderer camera.
        """
        width, height = max(1, self.pet.width()), max(1, self.pet.height())
        model = getattr(self.pet, "model", None)
        actions = getattr(self.pet, "actions", {})
        clip = actions.get("edge_bottom_sit")
        if model is None or clip is None:
            return height * 0.94, 1.0
        cache = getattr(self, "_support_cache", None)
        if cache is None:
            self._support_cache = cache = {}
        key = (id(model), id(clip), width, height)
        if key in cache:
            return cache[key]
        try:
            from aideskpal.pmx.skeleton import Skeleton
            from aideskpal.render.renderer import PmxRenderer

            rig = Skeleton(model)
            pose = clip.sample(0.0)
            points, _ = rig.skin_vertices(rig.skin_matrices(pose), model.positions, model.normals)
            proxy = SimpleNamespace(model=model, stage_scale=1.0,
                                    stage_roll_degrees=0.0, stage_yaw_degrees=0.0)
            matrix = PmxRenderer._compute_view_proj(proxy, width, height)
            top, bottom = projected_support(points, matrix, width, height)
            # Orthographic projection scales displacement about viewport center.
            radius = max(abs(top-height*.5), abs(bottom-height*.5), height*.01)
            scale = float(np.clip(height*.46 / radius, .45, 1.0))
            proxy.stage_scale = scale
            matrix = PmxRenderer._compute_view_proj(proxy, width, height)
            _, bottom = projected_support(points, matrix, width, height)
            cache[key] = (bottom, scale)
            return cache[key]
        except (ValueError, AttributeError, IndexError):
            logger.exception("Unable to calibrate seated support; using conservative viewport fit")
            return height * .94, .75

    def _pose_bounds(
        self, action_id: str, time: float, roll: float, yaw: float, scale: float,
        width: int, height: int,
    ) -> tuple[float, float, float, float]:
        from aideskpal.pmx.skeleton import Skeleton
        from aideskpal.render.renderer import PmxRenderer

        model = self.pet.model
        clip = self.pet.actions[action_id]
        rig = Skeleton(model)
        points, _ = rig.skin_vertices(
            rig.skin_matrices(clip.sample(time)), model.positions, model.normals
        )
        proxy = SimpleNamespace(
            model=model, stage_scale=float(scale), stage_roll_degrees=float(roll),
            stage_yaw_degrees=float(yaw),
        )
        matrix = PmxRenderer._compute_view_proj(proxy, width, height)
        return projected_bounds(points, matrix, width, height)

    def _bone_projection(
        self, action_id: str, bone_names: tuple[str, ...], time: float,
        roll: float, yaw: float, scale: float, width: int, height: int,
    ) -> tuple[float, float] | None:
        from aideskpal.pmx.skeleton import Skeleton
        from aideskpal.render.renderer import PmxRenderer

        model = self.pet.model
        index = model.bone_index(*bone_names)
        if index < 0:
            return None
        rig = Skeleton(model)
        world = rig.world_matrices(self.pet.actions[action_id].sample(time))
        point = world[index][:3, 3].reshape(1, 3)
        proxy = SimpleNamespace(
            model=model, stage_scale=float(scale), stage_roll_degrees=float(roll),
            stage_yaw_degrees=float(yaw),
        )
        matrix = PmxRenderer._compute_view_proj(proxy, width, height)
        clip = np.c_[point, np.ones(1)] @ matrix.T
        if abs(float(clip[0, 3])) < 1e-8:
            return None
        ndc = clip[0, :2] / clip[0, 3]
        return float((1 + ndc[0]) * width * .5), float((1 - ndc[1]) * height * .5)

    # ------------------------------------------------------------- edge anchors
    # Each mode may sit anywhere along its edge.  ``_free`` carries the user's
    # chosen coordinate; when it is unset we fall back to the mode's historic
    # default so automatic cycles still look composed.
    _FREE_AXIS = {
        "side_left": "y",
        "side_right": "y",
        "top": "x",
        "bottom_sit": "x",
        "land": "x",
    }

    def edge_anchor(self, mode: str) -> str | None:
        """Which axis is free along this mode's edge (``None`` for the fall)."""
        return self._FREE_AXIS.get(mode)

    def _default_along(self, mode: str, area: QRect, extent: int) -> float:
        """Historic default position along the edge, used when nothing is pinned."""
        if mode in {"side_left", "side_right"}:
            return float(area.top() + int(extent * .16))
        if mode == "top":
            return float(area.left() + int((area.width() - extent) * .68))
        return float(area.left() + int((area.width() - extent) * .50))

    def _clamp_along(self, mode: str, area: QRect, extent: int, value: float) -> float:
        """Keep the character overlapping the screen while it hugs one edge.

        The window is allowed to hang outside the edge it clutches, but it must
        not drift fully past either end of that edge, otherwise the character
        becomes unreachable by the mouse.
        """
        if mode in {"side_left", "side_right"}:
            low, high = area.top() - extent * .55, area.bottom() - extent * .45
        else:
            low, high = area.left() - extent * .30, area.right() - extent * .70
        if high < low:
            return low
        return float(min(high, max(low, value)))

    def _along(self, mode: str, area: QRect, extent: int) -> float:
        axis = self.edge_anchor(mode)
        pinned = self._free if axis is not None and self._free_axis == axis else None
        if pinned is None:
            return self._default_along(mode, area, extent)
        return self._clamp_along(mode, area, extent, pinned)

    def _remember_position(self, mode: str, position: QPoint) -> None:
        """Capture where the user left the window along this edge."""
        axis = self.edge_anchor(mode)
        if axis is None:
            self._free = None
            self._free_axis = None
            return
        self._free = float(position.y() if axis == "y" else position.x())
        self._free_axis = axis

    def _pin(self, mode: str, value: float) -> None:
        axis = self.edge_anchor(mode)
        if axis is None:
            return
        self._free = float(value)
        self._free_axis = axis

    def _target(
        self, mode: str, area: QRect, time: float = 0.0
    ) -> tuple[QPoint, float, float, bool, float]:
        width = max(1, self.pet.width())
        height = max(1, self.pet.height())
        if mode in {"side_left", "side_right"}:
            left = mode == "side_left"
            roll, yaw = 0.0, 0.0  # face and gaze look directly out of the screen
            x = area.left() - int(width * .34) if left else area.right() - int(width * .66)
            y = int(round(self._along(mode, area, height)))
            if getattr(self.pet, "model", None) is not None:
                try:
                    hands = [
                        self._bone_projection(
                            MODE_ACTION[mode], (side + "手首", side + "腕"),
                            time, roll, yaw, 1.0, width, height,
                        )
                        for side in ("左", "右")
                    ]
                    visible = [point[0] for point in hands if point is not None]
                    if visible:
                        wall = area.left() + 2 if left else area.right() - 2
                        x = round(wall - sum(visible) / len(visible))
                except (ValueError, AttributeError, IndexError, KeyError):
                    logger.exception("Unable to calibrate side wall grips; using conservative position")
            return QPoint(x, y), roll, 1.0, False, yaw
        if mode == "top":
            x = int(round(self._along(mode, area, width)))
            y = area.top() - int(height * .02)
            if getattr(self.pet, "model", None) is not None:
                try:
                    hands = [
                        self._bone_projection(
                            "edge_top_grip", (side + "手首", side + "腕"),
                            time, 0.0, 0.0, 1.0, width, height,
                        ) for side in ("左", "右")
                    ]
                    visible = [point[1] for point in hands if point is not None]
                    if visible:
                        y = round(area.top() + 3 - min(visible))
                except (ValueError, AttributeError, IndexError, KeyError):
                    logger.exception("Unable to calibrate top grip; using conservative position")
            return QPoint(x, y), 0.0, 1.0, False, 0.0
        if mode in {"bottom_sit", "land"}:
            support, scale = self._bottom_support()
            action_id = MODE_ACTION[mode]
            if getattr(self.pet, "model", None) is not None and (
                mode == "land" or time > 0.0
            ):
                try:
                    support = self._pose_bounds(
                        action_id, time, 0.0, 0.0, scale, width, height
                    )[3]
                except (ValueError, AttributeError, IndexError, KeyError):
                    logger.exception("Unable to update bottom support; retaining calibrated fit")
            return (
                QPoint(
                    int(round(self._along(mode, area, width))),
                    round(area.bottom() - support),
                ),
                0.0, scale, True, 0.0,
            )
        return (self.pet.position(), 0.0, 1.0, True, 0.0)

    def _on_animation_advanced(self, action_id: str, _time: float) -> None:
        if action_id and action_id == MODE_ACTION.get(self.mode):
            self._align_contact()

    def _align_contact(self) -> None:
        """Keep the active support/grip on its physical screen edge."""
        if (
            self.mode not in MODE_ACTION
            or self.mode == "fall"
            or self._move_animation is not None
            or self.pet.dragging
            or not self.pet.isVisible()
        ):
            return
        player = getattr(self.pet, "player", None)
        clip = getattr(player, "current", None)
        if clip is None or clip.id != MODE_ACTION[self.mode]:
            return
        try:
            target, roll, scale, _contact, yaw = self._target(
                self.mode, self._screen_area(), min(player.time, clip.duration)
            )
        except (ValueError, AttributeError, IndexError, KeyError):
            return
        current = self.pet.position()
        if abs(target.x() - current.x()) >= 1 or abs(target.y() - current.y()) >= 1:
            self.pet.setPosition(target)

    def _schedule(self, delay: float) -> None:
        if not self.enabled:
            return
        self._cycle_timer.start(max(1000, int(delay * 1000)))

    def _schedule_fall(self) -> None:
        self._fall_timer.stop()
        if self.mode not in {"side_left", "side_right", "top"}:
            return
        if random.random() >= max(0.0, min(1.0, self.config.window.edge_fall_chance)):
            return
        self._fall_timer.start(random.randint(9_000, 23_000))

    # ------------------------------------------------------------------ moves
    def _animate(
        self,
        target: QPoint,
        duration: int,
        *,
        easing: QEasingCurve.Type = QEasingCurve.Type.InOutCubic,
        callback=None,
    ) -> None:
        if self._move_animation is not None:
            self._move_animation.stop()
        animation = QVariantAnimation(self)
        animation.setStartValue(self.pet.position())
        animation.setEndValue(QPoint(int(target.x()), int(target.y())))
        animation.setDuration(max(100, int(duration)))
        animation.setEasingCurve(easing)
        animation.valueChanged.connect(self._set_position)
        def finished() -> None:
            if self._move_animation is not animation:
                return
            self._move_animation = None
            if callback is not None:
                callback()
        animation.finished.connect(finished)
        self._move_animation = animation
        animation.start()

    def _set_position(self, value) -> None:
        if isinstance(value, QPoint):
            self.pet.setPosition(value)

    def _random_along(self, mode: str, area: QRect, extent: int) -> float:
        """A composed-looking but varied spot along an edge for automatic cycles."""
        if mode in {"side_left", "side_right"}:
            low = area.top() + extent * .06
            high = max(low, area.bottom() - extent * .62)
        else:
            low = area.left() + extent * .10
            high = max(low, area.right() - extent * 1.10)
        return float(low + (high - low) * random.random())

    def enter(self, mode: str, *, keep_along: bool = True) -> None:
        if not self.enabled or self.pet.dragging or not self.pet.isVisible():
            return
        if mode not in MODE_ACTION:
            return
        self._fall_timer.stop()
        self._settle_timer.stop()
        self._snap_timer.stop()
        previous_axis = self.edge_anchor(self.mode) if self.mode else None
        self.mode = mode
        axis = self.edge_anchor(mode)
        if axis is None:
            # The fall sequence has no meaningful anchor along an edge.
            self._free = None
            self._free_axis = None
        elif self._free_axis is not None and self._free_axis != axis:
            # A different edge means the remembered coordinate is meaningless.
            self._free = None
            self._free_axis = None
        elif not keep_along and previous_axis not in (None, axis):
            self._free = None
            self._free_axis = None
        # A position the user chose (or a caller pinned) survives mode changes
        # on the same axis, so snapping to an edge honours where it was dropped
        # instead of re-centering every time.
        area = self._screen_area()
        if self._free is None:
            extent = max(1, self.pet.width())
            if axis == "y":
                extent = max(1, self.pet.height())
            self._pin(mode, self._random_along(mode, area, extent))
        target, roll, scale, contact, yaw = self._target(mode, area)
        self.pet.set_edge_mode(mode)
        self.pet.set_edge_stage(
            roll, scale, yaw=yaw, contact_shadow=contact, animate=True,
duration_ms=900,
        )
        self.pet.play_edge_action(MODE_ACTION[mode], fade=0.3)
        self._busy = True
        self._animate(target, 900, callback=self._arrived)
        self._contact_timer.start(100)
        logger.info("Edge behavior -> %s at %s", mode, target)

    def _arrived(self) -> None:
        self._busy = False
        self._schedule_fall()
        if self.mode in {"side_left", "side_right", "top"}:
            self._schedule(random.uniform(32.0, 65.0))
        else:
            self._schedule(random.uniform(65.0, 130.0))

    # Auto-cycled poses.  The bottom edge only ever offers the duck sit now that
    # the lying pose is gone.
    CYCLE_MODES = ("side_left", "side_right", "top", "bottom_sit")

    def next_pose(self) -> None:
        if not self.enabled or self.pet.dragging or not self.pet.isVisible():
            self._schedule(30.0)
            return
        if self.mode in {"fall", "land"}:
            return
        choice = random.choices(
            self.CYCLE_MODES,
            weights=[26, 26, 20, 28],
            k=1,
        )[0]
        if choice == self.mode:
            # Avoid visibly resetting the same pose; choose a neighbor.
            choice = random.choice([m for m in self.CYCLE_MODES if m != choice])
        self.enter(choice)

    def _fall(self) -> None:
        if self.mode not in {"side_left", "side_right", "top"} or self.pet.dragging:
            return
        self._cycle_timer.stop()
        self._busy = True
        area = self._screen_area()
        # Remember the horizontal spot before the mode changes, so the character
        # falls straight down from where it was hanging instead of drifting to
        # the centre of the bottom edge.
        self._pin("bottom_sit", float(self.pet.position().x()))
        self.mode = "fall"
        self.pet.set_edge_mode("fall")
        target, _, scale, _, _ = self._target("land", area)
        self.pet.set_edge_stage(
            0.0, scale, yaw=0.0, contact_shadow=False, animate=True,
duration_ms=520,
        )
        self.pet.play_edge_action("edge_fall", hold_finished=True, fade=0.08)
        duration = int(round(float(self.pet.actions["edge_fall"].duration) * 1000))
        self._animate(target, duration, easing=QEasingCurve.Type.InCubic, callback=self._landed)
        logger.info("Edge fall from %s", self.mode)

    def _landed(self) -> None:
        if self.mode != "fall" or not self.enabled or self.pet.dragging or not self.pet.isVisible():
            return
        self._busy = True
        self.mode = "land"
        self.pet.set_edge_mode("land")
        _, scale = self._bottom_support()
        self.pet.set_edge_stage(
            0.0, scale, yaw=0.0, contact_shadow=True, animate=False
        )
        self.pet.play_edge_action("edge_land_sit", hold_finished=True, fade=0.1)
        self._contact_timer.start(100)
        duration = float(self.pet.actions["edge_land_sit"].duration)
        self._settle_timer.start(max(1, int(np.ceil(duration * 1000))))

    def _settle_bottom(self) -> None:
        if self.mode != "land" or not self.enabled or not self.pet.isVisible():
            return
        if self.pet.dragging:
            self._busy = False
            self.mode = None
            return
        self.mode = None
        self._busy = False
        self.enter("bottom_sit")

    # ------------------------------------------------------------------ input
    def _on_drag_state(self, dragging: bool) -> None:
        if dragging:
            self.stop()
            self.mode = None
            self._busy = False
            self.pet.clear_edge_pose()
            logger.info("Edge behavior paused for drag")
            return
        # 360-style threshold: if the character is more than 20% outside the
        # work area when released, snap into the matching edge pose.
        self._snap_timer.start(80)

    def _snap_after_drag(self) -> None:
        if not self.enabled or self.pet.dragging:
            return
        fraction = self.pet.visible_character_fraction()
        edge = self.pet.nearest_screen_edge()
        if edge is not None and fraction < 0.8:
            # The bottom edge is always the duck sit; the other edges map 1:1.
            mode = "bottom_sit" if edge == "bottom" else edge
            # Keep the exact spot the user dropped it at, so the pose snaps to
            # that position along the edge instead of jumping to its centre.
            self._remember_position(mode, self.pet.position())
            logger.info(
                "Edge threshold reached: %.1f%% character visible, edge=%s -> %s at %s",
                fraction * 100.0,
                edge,
                mode,
                self._free,
            )
            self.enter(mode)
            return
        self._schedule(18.0)

    def leave_for_interaction(self) -> None:
        """Stop the edge cycle but leave the window where the user touched it."""
        self.stop()
        self.mode = None
        self._busy = False
        self.pet.clear_edge_pose()
        self._schedule(18.0)

    def leave_to_normal(self) -> None:
        """Public hook for settings/chat: bring the pet back before a dialog."""
        self._leave_to_normal()

    def _leave_to_normal(self) -> None:
        if self.mode is None:
            return
        self.stop()
        area = self._screen_area()
        target = QPoint(area.right() - self.pet.width() - 36, area.bottom() - self.pet.height())
        self.mode = None
        self._busy = True
        self.pet.clear_edge_pose(duration_ms=650)
        self.pet.return_to_idle(fade=0.25)
        self._animate(target, 650, callback=self._normal_arrived)

    def _normal_arrived(self) -> None:
        self._busy = False
        self._schedule(20.0)
