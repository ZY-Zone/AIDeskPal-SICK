"""Transparent, draggable OpenGL desktop pet window."""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEasingCurve, QPoint, QRect, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QGuiApplication, QMouseEvent
from PySide6.QtOpenGL import QOpenGLWindow
from aideskpal.animation.action import ActionClip
from aideskpal.animation.player import ActionPlayer
from aideskpal.config import AppConfig
from aideskpal.pmx.model import PmxModel
from aideskpal.pmx.skeleton import Pose, quat_from_euler_xyz
from aideskpal.render.renderer import PmxRenderer

logger = logging.getLogger(__name__)

FRAME_INTERVAL_MS = 16
MASK_REFRESH_SECONDS = 0.45
WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1

# How the user asks the pet to tuck itself into the tray.
HIDE_TRIGGER_DOUBLE_CLICK = "double_click_body"
HIDE_TRIGGER_RIGHT_DOUBLE_CLICK = "double_right_click"
HIDE_TRIGGER_HOTKEY = "hotkey"
HIDE_TRIGGER_OFF = "off"
HIDE_TRIGGERS = (
    HIDE_TRIGGER_DOUBLE_CLICK,
    HIDE_TRIGGER_RIGHT_DOUBLE_CLICK,
    HIDE_TRIGGER_HOTKEY,
    HIDE_TRIGGER_OFF,
)


class PetWindow(QOpenGLWindow):
    interaction = Signal(str, int, int)  # trigger, x, y (relative to window)
    position_changed = Signal(int, int)
    action_changed = Signal(str)
    action_finished = Signal(str)
    animation_advanced = Signal(str, float)
    request_chat = Signal()
    request_hide = Signal()
    drag_state_changed = Signal(bool)

    def __init__(
        self,
        model: PmxModel,
        actions: dict[str, ActionClip],
        config: AppConfig,
    ) -> None:
        super().__init__()
        self.model = model
        self.config = config
        self.actions = actions
        self.renderer = PmxRenderer(model, opacity=config.window.opacity)
        self.renderer_ready = False
        self._idle_id = self._choose_idle_id(config.last_action_id)
        self.player = ActionPlayer(actions, idle_id=self._idle_id)
        self._current_action = ""
        self._last_tick = time.monotonic()
        self._finish_at: float | None = None
        self._alpha_mask: np.ndarray | None = None
        self._last_mask_at = 0.0
        self._drag_enabled = True
        self._pressed = False
        self._dragging = False
        self._press_global = QPoint()
        self._window_origin = QPoint()
        self._last_mouse = QPoint()
        self._last_move_at = 0.0
        self._drag_vx = 0.0
        self._drag_vy = 0.0
        self._overlay_until = 0.0
        self._closed = False
        self._scale = float(np.clip(config.window.pet_scale, 0.5, 1.5))
        self._edge_mode: str | None = None
        self._edge_hold_finished = False
        self._stage_animation: QVariantAnimation | None = None
        self._hide_trigger = str(getattr(config.window, "hide_trigger", HIDE_TRIGGER_DOUBLE_CLICK))

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        if config.window.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setFlags(flags)
        self.setTitle("AIDeskPal-SICK")
        self.setOpacity(float(np.clip(config.window.opacity, 0.2, 1.0)))
        self.setMinimumSize(QSize(140, 220))
        self.resize(self._scaled_size())
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._frame_timer = QTimer(self)
        self._frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._frame_timer.setInterval(FRAME_INTERVAL_MS)
        self._frame_timer.timeout.connect(self._tick)
        self._frame_timer.start()

        if self._idle_id:
            self.player.play(self._idle_id, fade=0.0)
            self._current_action = self._idle_id
            self.renderer.update_pose(self.player.pose())

    # ------------------------------------------------------------------ setup
    @property
    def idle_id(self) -> str | None:
        return self._idle_id

    @property
    def current_action_id(self) -> str:
        return self._current_action

    @property
    def dragging(self) -> bool:
        return self._dragging

    @property
    def edge_mode(self) -> str | None:
        return self._edge_mode

    @property
    def drag_velocity(self) -> tuple[float, float]:
        return self._drag_vx, self._drag_vy

    def character_rect(self) -> QRect:
        """Approximate the rendered character rect in logical window coords."""
        mask = self._alpha_mask
        if mask is None or mask.size == 0 or not bool(mask.any()):
            return QRect(
                int(self.width() * 0.10),
                int(self.height() * 0.08),
                max(1, int(self.width() * 0.80)),
                max(1, int(self.height() * 0.84)),
            )
        dpr = float(self.devicePixelRatio() or 1.0)
        rows = np.flatnonzero(mask.any(axis=1))
        cols = np.flatnonzero(mask.any(axis=0))
        if rows.size == 0 or cols.size == 0:
            return self.rect()
        left = int(round(float(cols[0]) / dpr))
        right = int(round(float(cols[-1] + 1) / dpr))
        # glReadPixels rows start at the bottom of the window.
        top = int(round(self.height() - float(rows[-1] + 1) / dpr))
        bottom = int(round(self.height() - float(rows[0]) / dpr))
        return QRect(left, top, max(1, right - left), max(1, bottom - top))

    def character_screen_rect(self) -> QRect:
        local = self.character_rect()
        return QRect(self.x() + local.x(), self.y() + local.y(), local.width(), local.height())

    def is_on_head(self, point: QPoint) -> bool:
        """True when a window-local point lands on the head.

        The head estimate uses the rendered silhouette, not the window box: the
        alpha mask gives the real character top, and the head occupies the top
        slice of that silhouette.  Without a mask fall back to the same box
        proportions ``character_rect`` assumes, so the gesture still works before
        the first frame has been measured.
        """
        rect = self.character_rect()
        if rect.height() <= 0:
            return False
        # The head is the upper fifth of the visible silhouette; the shoulder line
        # in the character art sits just below that.
        head_band = max(1, int(rect.height() * 0.22))
        return rect.top() <= point.y() <= rect.top() + head_band and (
            rect.left() <= point.x() <= rect.right()
        )

    def set_hide_trigger(self, trigger: str) -> None:
        """Choose which gesture tucks the pet into the tray."""
        self._hide_trigger = trigger if trigger in HIDE_TRIGGERS else HIDE_TRIGGER_OFF

    def visible_character_fraction(self) -> float:
        rect = self.character_screen_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return 0.0
        screen = QGuiApplication.screenAt(rect.center())
        if screen is None:
            screen = QGuiApplication.screenAt(self.geometry().center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return 1.0
        area = screen.availableGeometry()
        visible = rect.intersected(area)
        return max(0.0, float(visible.width() * visible.height()) / float(rect.width() * rect.height()))

    def nearest_screen_edge(self) -> str | None:
        rect = self.character_screen_rect()
        screen = QGuiApplication.screenAt(rect.center())
        if screen is None:
            screen = QGuiApplication.screenAt(self.geometry().center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None
        area = screen.availableGeometry()
        outside = {
            "side_left": max(0, area.left() - rect.left()),
            "side_right": max(0, rect.right() - area.right()),
            "top": max(0, area.top() - rect.top()),
            "bottom": max(0, rect.bottom() - area.bottom()),
        }
        edge, amount = max(outside.items(), key=lambda item: item[1])
        return edge if amount > 0 else None

    def set_edge_mode(self, mode: str | None) -> None:
        self._edge_mode = mode

    def set_edge_stage(
        self,
        roll: float,
        scale: float = 1.0,
        *,
        yaw: float = 0.0,
        contact_shadow: bool = True,
        animate: bool = True,
        duration_ms: int = 520,
    ) -> None:
        """Animate orientation, zoom and transparent-window shape together."""
        if self._stage_animation is not None:
            self._stage_animation.stop()
            self._stage_animation = None
        self.renderer.contact_shadow_enabled = bool(contact_shadow)
        start = (
            float(self.renderer.stage_roll_degrees),
            float(self.renderer.stage_yaw_degrees),
            float(self.renderer.stage_scale),
            self.width(), self.height(),
        )
        target_size = self._scaled_size()
        target = (
            float(roll), float(yaw), float(np.clip(scale, 0.45, 1.25)),
            target_size.width(), target_size.height(),
        )

        def apply(progress: float) -> None:
            progress = float(np.clip(progress, 0.0, 1.0))
            values = [a + (b - a) * progress for a, b in zip(start, target)]
            self.renderer.stage_roll_degrees = values[0]
            self.renderer.stage_yaw_degrees = values[1]
            self.renderer.stage_scale = values[2]
            size = QSize(
                max(self.minimumWidth(), int(round(values[3]))),
                max(self.minimumHeight(), int(round(values[4]))),
            )
            if size != self.size():
                self.resize(size)
            self._alpha_mask = None
            self.update()

        if not animate or duration_ms <= 0:
            apply(1.0)
            return
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(duration_ms)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.valueChanged.connect(apply)
        animation.finished.connect(lambda: apply(1.0))
        animation.finished.connect(lambda: setattr(self, "_stage_animation", None))
        self._stage_animation = animation
        animation.start()

    def _set_stage_roll(self, value: float) -> None:
        self.renderer.stage_roll_degrees = float(value)
        self.update()

    def clear_edge_pose(self, *, reset_stage: bool = True, duration_ms: int = 420) -> None:
        self._edge_mode = None
        self._edge_hold_finished = False
        if reset_stage:
            self.set_edge_stage(
                0.0, 1.0, yaw=0.0, contact_shadow=True,
                duration_ms=duration_ms,
            )

    def play_edge_action(
        self, action_id: str, *, hold_finished: bool = False, fade: float = 0.25
    ) -> bool:
        if action_id not in self.actions:
            logger.warning("Edge action not found: %s", action_id)
            return False
        self._edge_hold_finished = bool(hold_finished)
        self._finish_at = None
        if not self.player.play(action_id, fade=fade, restart=True):
            return False
        self._current_action = action_id
        self.action_changed.emit(action_id)
        return True

    def _choose_idle_id(self, preferred: str) -> str | None:
        if preferred in self.actions and self.actions[preferred].loop:
            return preferred
        for clip in self.actions.values():
            if clip.category == "idle" and clip.loop:
                return clip.id
        return next(iter(self.actions), None)

    def set_actions(self, actions: dict[str, ActionClip]) -> None:
        self.actions = actions
        self._idle_id = self._choose_idle_id(self.config.last_action_id)
        self.player.set_clips(actions, idle_id=self._idle_id)
        if self.player.current_id not in actions:
            if self._idle_id:
                self.player.play(self._idle_id, fade=0.2)
                self._current_action = self._idle_id

    def set_idle_action(self, action_id: str) -> None:
        if action_id in self.actions and self.actions[action_id].loop:
            self._idle_id = action_id
            self.player.idle_id = action_id
            self.player.play(action_id, fade=0.5)

    def play_action(self, action_id: str, *, fade: float | None = None) -> bool:
        if action_id not in self.actions:
            logger.warning("Action not found: %s", action_id)
            return False
        if self._dragging and action_id not in {"drag_dangle", "drag_land"}:
            return False
        if self._edge_mode and not action_id.startswith("edge_") and action_id not in {
            "drag_dangle",
            "drag_land",
        }:
            return False
        ok = self.player.play(action_id, fade=fade)
        if ok:
            self._current_action = action_id
            self._finish_at = None
            self.action_changed.emit(action_id)
        return ok

    def return_to_idle(self, *, fade: float = 0.45) -> None:
        if self._edge_mode:
            return
        if self._idle_id and not self._dragging:
            self.player.play(self._idle_id, fade=fade)
            self._current_action = self._idle_id
            self._finish_at = None
            self.action_changed.emit(self._current_action)

    def apply_config(self, config: AppConfig) -> None:
        self.config = config
        visible = self.isVisible()
        flags = self.flags()
        if config.window.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        if flags != self.flags():
            self.setFlags(flags)
            if visible:
                self.show()
        self.setOpacity(float(np.clip(config.window.opacity, 0.2, 1.0)))
        self.renderer.opacity = float(np.clip(config.window.opacity, 0.2, 1.0))
        self.clear_edge_pose()
        self._scale = float(np.clip(config.window.pet_scale, 0.5, 1.5))
        self._resize_keep_bottom(self._scaled_size())
        self._drag_enabled = True

    def _scaled_size(self) -> QSize:
        base_width = max(260, int(self.config.window.width))
        base_height = max(420, int(self.config.window.height))
        width = max(140, int(round(base_width * self._scale)))
        height = max(220, int(round(base_height * self._scale)))
        screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            width = min(width, max(140, area.width() - 20))
            height = min(height, max(220, area.height() - 20))
        return QSize(width, height)

    def _resize_keep_bottom(self, size: QSize) -> None:
        if size.width() <= 0 or size.height() <= 0:
            return
        if self.size() == size:
            return
        old = self.geometry()
        bottom = old.bottom()
        center_x = old.center().x()
        self.resize(size)
        if self.isVisible():
            target = QPoint(
                center_x - size.width() // 2,
                bottom - size.height() + 1,
            )
            self.setPosition(self._clamp_position(target))

    def set_scale(self, scale: float) -> None:
        """Live-preview a scale ratio without touching saved config."""
        value = float(np.clip(scale, 0.5, 1.5))
        if abs(value - self._scale) < 1e-4:
            return
        self._scale = value
        self.clear_edge_pose()
        self._resize_keep_bottom(self._scaled_size())
        self._alpha_mask = None
        self._last_mask_at = 0.0
        self.update()

    def place_on_screen(self, x: int | None = None, y: int | None = None) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width = min(self.width(), area.width() - 20)
        height = min(self.height(), area.height() - 20)
        if (width, height) != (self.width(), self.height()):
            self.resize(width, height)
        if x is None or y is None:
            x = area.right() - self.width() - 36
            y = area.bottom() - self.height()
        position = QPoint(int(x), int(y))
        # Keep a safe part of the window visible on the nearest screen.
        target_screen = QGuiApplication.screenAt(position + QPoint(self.width() // 2, self.height() // 2))
        if target_screen is None:
            target_screen = screen
        target = target_screen.availableGeometry()
        position.setX(max(target.left() - self.width() // 3, min(position.x(), target.right() - self.width() // 2)))
        position.setY(max(target.top() - self.height() // 4, min(position.y(), target.bottom() - self.height() // 3)))
        self.setPosition(position)

    # ------------------------------------------------------------------ render
    def initializeGL(self) -> None:  # noqa: N802
        try:
            self.renderer.initialize()
            self.renderer_ready = True
            logger.info("Pet OpenGL initialized")
        except Exception:
            logger.exception("Could not initialize pet renderer")

    def paintGL(self) -> None:  # noqa: N802
        if not self.renderer_ready:
            return
        dpr = float(self.devicePixelRatio() or 1.0)
        try:
            self.renderer.render(self.width(), self.height(), dpr)
            now = time.monotonic()
            if self.config.window.click_through_transparent and now - self._last_mask_at > MASK_REFRESH_SECONDS:
                self._last_mask_at = now
                try:
                    # The contact shadow is intentionally semi-transparent;
                    # require a substantial opacity so it never becomes a
                    # large invisible click target around the feet.
                    self._alpha_mask = self.renderer.read_alpha_mask(
                        max(1, int(self.width() * dpr)),
                        max(1, int(self.height() * dpr)),
                        0.50,
                    )
                except Exception:
                    logger.debug("Alpha mask read failed", exc_info=True)
        except Exception:
            logger.exception("Pet render failed")

    def _tick(self) -> None:
        if self._closed or not self.isVisible():
            return
        now = time.monotonic()
        dt = min(0.12, max(0.0, now - self._last_tick))
        self._last_tick = now
        pose = self.player.update(dt)
        self.renderer.update_pose(pose)
        self.animation_advanced.emit(self.player.current_id or "", self.player.time)
        if self.player.is_finished:
            if self._finish_at is None:
                self._finish_at = now + 0.45
                self.action_finished.emit(self._current_action)
            elif now >= self._finish_at:
                self._finish_at = None
                if not self._edge_mode:
                    self.return_to_idle()
        if self._dragging and now > self._overlay_until:
            self._drag_vx *= 0.82
            self._drag_vy *= 0.82
            self._apply_drag_overlay()
        self.update()

    # ------------------------------------------------------------------ drag
    def _begin_drag(self) -> None:
        self._dragging = True
        self.clear_edge_pose()
        self.drag_state_changed.emit(True)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.player.clear_overlays()
        if "drag_dangle" in self.actions:
            self.player.play("drag_dangle", fade=0.12, restart=True)
            self._current_action = "drag_dangle"
            self.action_changed.emit("drag_dangle")

    def _apply_drag_overlay(self) -> None:
        root = self.model.bone_index("全ての親", "root", "Root", "センター")
        if root < 0:
            for bone in self.model.bones:
                if bone.parent_index < 0:
                    root = bone.index
                    break
        if root < 0:
            return
        pose = Pose.empty()
        sway = max(-13.0, min(13.0, -self._drag_vx * 0.55))
        lean = max(-9.0, min(9.0, self._drag_vy * 0.35))
        pose.rotations[root] = quat_from_euler_xyz((lean * 0.5, 0.0, sway))
        left_leg = self.model.bone_index("左足", "leg_L", "LeftLeg")
        right_leg = self.model.bone_index("右足", "leg_R", "RightLeg")
        if left_leg >= 0:
            pose.rotations[left_leg] = quat_from_euler_xyz((0.0, 0.0, max(-8.0, min(8.0, sway * 0.55))))
        if right_leg >= 0:
            pose.rotations[right_leg] = quat_from_euler_xyz((0.0, 0.0, max(-8.0, min(8.0, -sway * 0.55))))
        self.player.add_overlay(pose, weight=0.55)
        self._overlay_until = time.monotonic() + 0.12

    def _end_drag(self) -> None:
        self._dragging = False
        self.drag_state_changed.emit(False)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.player.clear_overlays()
        if "drag_land" in self.actions:
            self.player.play("drag_land", fade=0.1, restart=True)
            self._current_action = "drag_land"
            self.action_changed.emit("drag_land")
        else:
            self.return_to_idle(fade=0.3)
        self.position_changed.emit(self.x(), self.y())

    def _clamp_position(self, position: QPoint) -> QPoint:
        screen = QGuiApplication.screenAt(position + QPoint(self.width() // 2, self.height() // 4))
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return position
        area = screen.availableGeometry()
        margin = 36
        x = max(area.left() - self.width() + margin, min(position.x(), area.right() - margin))
        y = max(area.top() - self.height() + margin, min(position.y(), area.bottom() - margin))
        return QPoint(x, y)

    # ------------------------------------------------------------------ input
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            # The context menu intentionally lives on the notification-area
            # icon, not on the transparent pet window.
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._dragging = False
            self._press_global = event.globalPosition().toPoint()
            self._last_mouse = self._press_global
            self._window_origin = self.position()
            self._last_move_at = time.monotonic()
            self._drag_vx = 0.0
            self._drag_vy = 0.0
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._pressed:
            super().mouseMoveEvent(event)
            return
        current = event.globalPosition().toPoint()
        delta = current - self._press_global
        if not self._dragging and delta.manhattanLength() >= 5:
            self._begin_drag()
        if self._dragging:
            target = self._clamp_position(self._window_origin + delta)
            self.setPosition(target)
            now = time.monotonic()
            elapsed = max(0.008, now - self._last_move_at)
            self._drag_vx = (current.x() - self._last_mouse.x()) / elapsed
            self._drag_vy = (current.y() - self._last_mouse.y()) / elapsed
            self._last_mouse = current
            self._last_move_at = now
            self._apply_drag_overlay()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            if self._dragging:
                self._end_drag()
            else:
                point = event.position().toPoint()
                trigger = "headpat" if point.y() < self.height() * 0.30 else "poke"
                self.interaction.emit(trigger, point.x(), point.y())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        button = event.button()
        if button == Qt.MouseButton.LeftButton:
            point = event.position().toPoint()
            # The head always opens the chat input; that stays reachable whatever
            # the hide trigger is, so hiding can never strand the user.
            if self.is_on_head(point):
                self.request_chat.emit()
            elif self._hide_trigger == HIDE_TRIGGER_DOUBLE_CLICK:
                self.request_hide.emit()
            event.accept()
            return
        if button == Qt.MouseButton.RightButton:
            # The context menu lives on the notification-area icon, so a right
            # double-click has no other meaning on the pet itself.
            if self._hide_trigger == HIDE_TRIGGER_RIGHT_DOUBLE_CLICK:
                self.request_hide.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------ transparency
    def nativeEvent(self, event_type, message):  # noqa: N802
        if (
            sys.platform == "win32"
            and self.config.window.click_through_transparent
            and self._alpha_mask is not None
            and bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG")
        ):
            try:
                from ctypes import wintypes

                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_NCHITTEST:
                    screen_x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    screen_y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    dpr = float(self.devicePixelRatio() or 1.0)
                    # WM_NCHITTEST carries physical pixels; Qt global coordinates are
                    # device-independent, so convert before mapping.
                    logical_x = int(round(screen_x / dpr))
                    logical_y = int(round(screen_y / dpr))
                    local = self.mapFromGlobal(QPoint(logical_x, logical_y))
                    if 0 <= local.x() < self.width() and 0 <= local.y() < self.height():
                        px = int(local.x() * dpr)
                        py = int((self.height() - 1 - local.y()) * dpr)
                        mask = self._alpha_mask
                        if 0 <= py < mask.shape[0] and 0 <= px < mask.shape[1]:
                            if not bool(mask[py, px]):
                                return True, HTTRANSPARENT
            except Exception:
                logger.debug("nativeEvent hit test failed", exc_info=True)
        return super().nativeEvent(event_type, message)

    # ------------------------------------------------------------------ lifecycle
    def closeEvent(self, event) -> None:  # noqa: N802
        self._closed = True
        self._frame_timer.stop()
        try:
            self.renderer.release()
        except Exception:
            logger.debug("Renderer release failed", exc_info=True)
        super().closeEvent(event)

    def capture(self, path: Path) -> bool:
        try:
            image = self.grabFramebuffer()
            path.parent.mkdir(parents=True, exist_ok=True)
            return bool(image.save(str(path)))
        except Exception:
            logger.exception("Screenshot failed")
            return False
