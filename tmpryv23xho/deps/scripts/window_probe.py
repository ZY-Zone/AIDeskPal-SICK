"""Launch the actual PetWindow for a few seconds and capture it.

Usage:
  python scripts/window_probe.py --model <pmx> --out probes/window.png
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication, QSurfaceFormat
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aideskpal.animation.action import ActionLibrary
from aideskpal.config import AppConfig
from aideskpal.pmx.model import load_pmx
from aideskpal.ui.pet_window import PetWindow


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seconds", type=float, default=4.0)
    args = parser.parse_args()

    fmt = QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setAlphaBufferSize(8)
    fmt.setSamples(4)
    fmt.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication([])
    config = AppConfig()
    config.window.width = 420
    config.window.height = 700
    config.window.click_through_transparent = False
    model = load_pmx(args.model)
    model.to_render_space()
    library = ActionLibrary([Path("actions")])
    library.load(model)
    actions = {clip.id: clip for clip in library.for_model("citlali_summer")}
    window = PetWindow(model, actions, config)
    window.setFlags(window.flags() | Qt.WindowType.WindowStaysOnTopHint)
    window.show()
    window.place_on_screen()
    window.raise_()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    def capture() -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            shot = screen.grabWindow(0)
            shot.save(str(out.with_name(out.stem + "_desktop.png")))
        window.capture(out)
        print("captured", out)

    QTimer.singleShot(1800, capture)
    QTimer.singleShot(int(args.seconds * 1000), app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
