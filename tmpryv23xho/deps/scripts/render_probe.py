"""Render a PMX still frame to a PNG for visual regression probes.

Usage: python scripts/render_probe.py --model <pmx> --out <png> [--pose rest|idle]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGL import QOpenGLWindow
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aideskpal.pmx.model import load_pmx
from aideskpal.pmx.skeleton import Pose, quat_from_euler_xyz
from aideskpal.render.renderer import PmxRenderer
from aideskpal.animation.action import ActionLibrary


class ProbeWindow(QOpenGLWindow):
    def __init__(
        self,
        model_path: Path,
        out: Path,
        pose: str,
        size: tuple[int, int],
        action: str = "",
        time: float = 0.0,
        roll: float = 0.0,
        scale: float = 1.0,
        yaw: float = 0.0,
    ) -> None:
        super().__init__()
        self.setFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setTitle("AIDeskPal render probe")
        self.resize(*size)
        self.model = load_pmx(model_path)
        self.model.to_render_space()
        self.out = out
        self.renderer = PmxRenderer(self.model)
        self.renderer.stage_roll_degrees = roll
        self.renderer.stage_yaw_degrees = yaw
        self.renderer.stage_scale = scale
        self.renderer.contact_shadow_enabled = abs(roll) < 1.0
        self.pose = Pose.empty()
        self.action_label = action
        if action:
            lib = ActionLibrary([Path(__file__).resolve().parents[1] / "actions"])
            lib.load(self.model)
            model_id = "starling" if self.model.name.startswith("星灵") else "citlali_summer"
            clip = lib.get(action, model_id)
            if clip is None:
                raise SystemExit(f"unknown action {action}")
            self.pose = clip.sample(time)
            self.action_label = f"{clip.name} @ {time:.2f}s"
        elif pose == "idle":
            self.pose = self._idle_pose()
        self.frames = 0

    def _idle_pose(self) -> Pose:
        model = self.model
        pose = Pose.empty()
        for name, angles in {
            "左腕": (0, -50, -40),
            "右腕": (0, 50, 40),
            "左ひじ": (0, 0, 0),
            "右ひじ": (0, 0, 0),
            "頭": (1, 0, 2),
            "上半身2": (1, 0, 0),
        }.items():
            index = model.bone_index(name)
            if index >= 0:
                pose.rotations[index] = quat_from_euler_xyz(angles)
        blink = model.morph_by_name.get("まばたき")
        if blink is not None:
            pose.morphs[blink] = 0.0
        return pose

    def initializeGL(self) -> None:
        self.renderer.initialize()
        print(
            "shadow", self.renderer._shadow_enabled,
            "light_matrix", self.renderer._light_view_proj.tolist(),
        )

    def paintGL(self) -> None:
        dpr = self.devicePixelRatio() or 1.0
        self.renderer.update_pose(self.pose)
        self.renderer.render(self.width(), self.height(), dpr)
        self.frames += 1

    def keyPressEvent(self, event) -> None:  # pragma: no cover
        if event.key() == Qt.Key_Escape:
            self.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--pose", default="idle", choices=["rest", "idle"])
    parser.add_argument("--action", default="")
    parser.add_argument("--time", type=float, default=0.0)
    parser.add_argument("--width", type=int, default=420)
    parser.add_argument("--height", type=int, default=700)
    parser.add_argument("--roll", type=float, default=0.0)
    parser.add_argument("--yaw", type=float, default=0.0)
    parser.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args()

    fmt = QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.OpenGL)
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setAlphaBufferSize(8)
    fmt.setSamples(4)
    fmt.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication([])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    window = ProbeWindow(
        Path(args.model),
        out,
        args.pose,
        (args.width, args.height),
        args.action,
        args.time,
        args.roll,
        args.scale,
        args.yaw,
    )
    window.show()

    def capture() -> None:
        image = window.grabFramebuffer()
        image.save(str(out))
        r = window.renderer
        import numpy as np
        from OpenGL.GL import GL_VIEWPORT, glGetIntegerv
        vp = [0, 0, 0, 0]
        glGetIntegerv(GL_VIEWPORT, vp)
        print("viewport", vp, "window", window.width(), window.height(), "dpr", window.devicePixelRatio())
        print("viewproj\n", np.array2string(r._view_proj, precision=3))
        print("model bbox", window.model.bbox_min, window.model.bbox_max)
        p = r._positions[::500]
        clip = (r._view_proj @ np.hstack([p, np.ones((len(p), 1))]).T).T
        ndc = clip[:, :3] / clip[:, 3:4]
        print("ndc y range", ndc[:, 1].min(), ndc[:, 1].max(), "x", ndc[:, 0].min(), ndc[:, 0].max())
        print(f"saved {out} size={image.width()}x{image.height()} alpha={image.hasAlphaChannel()} pose={window.action_label}")
        window.close()
        app.quit()

    QTimer.singleShot(1200, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
