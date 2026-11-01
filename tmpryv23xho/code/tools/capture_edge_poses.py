"""Capture real-window frames of edge poses.

Edge poses are judged as pictures, and the renderer needs a live GL context, so
this probe drives the real PetWindow instead of trying to render offscreen.  It
writes one PNG per requested (action, stage) combination into ``probes/edge``.

Run from the repository root:

    $env:PYTHONPATH='src'; .venv/Scripts/python.exe tools/capture_edge_poses.py
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aideskpal.app import DesktopPetApp, configure_surface_format  # noqa: E402
from aideskpal.config import SettingsStore  # noqa: E402
from aideskpal.paths import get_paths  # noqa: E402
from aideskpal.ui.edge import MODE_ACTION  # noqa: E402

OUT = ROOT / "probes/edge"

# (mode, clip time) pairs.  Stage values mirror EdgeController._target so the
# frame matches what the desktop actually shows.
SHOTS = [
    ("top", 0.0),
    ("bottom_sit", 0.0),
    ("side_left", 0.0),
    ("side_right", 0.0),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shots", default="", help="comma separated mode[:time]")
    args = parser.parse_args()

    logging.disable(logging.CRITICAL)
    configure_surface_format()
    qapp = QApplication([])
    qapp.setQuitOnLastWindowClosed(False)
    paths = get_paths().ensure()
    store = SettingsStore(paths)
    config = store.load()
    config.ai.enabled = False
    config.ai.proactive = False
    config.window.edge_behaviors = True

    class Store:
        def __init__(self) -> None:
            self.config = config

        def load(self):
            return config

        def save(self, _config):
            pass

        def get_secret(self, *_args):
            return ""

        def set_secret(self, *_args):
            pass

    app = DesktopPetApp(qapp, paths, Store(), no_single_instance=True)
    edge = app.edge_controller
    pet = app.pet
    OUT.mkdir(parents=True, exist_ok=True)

    shots = SHOTS
    if args.shots:
        shots = []
        for item in args.shots.split(","):
            mode, _, time_text = item.partition(":")
            shots.append((mode.strip(), float(time_text or 0.0)))

    state = {"index": 0, "phase": "enter", "since": time.monotonic()}
    results: list[str] = []

    def advance() -> None:
        state["phase"] = "enter"
        state["since"] = time.monotonic()

    def tick() -> None:
        elapsed = time.monotonic() - state["since"]
        if state["phase"] == "enter":
            if state["index"] >= len(shots):
                app.quit()
                return
            mode, at = shots[state["index"]]
            edge.enter(mode)
            # The player has no seek API; waiting longer samples a later moment
            # of the same loop, which is enough for a still frame.
            state["phase"] = "shot"
            state["since"] = time.monotonic()
            return
        if state["phase"] == "shot" and elapsed > 1.7 + shots[state["index"]][1]:
            image = pet.grabFramebuffer()
            mode, at = shots[state["index"]]
            name = f"{mode}" + (f"_{at:.2f}".replace(".", "_") if at else "") + ".png"
            path = OUT / name
            image.save(str(path))
            results.append(f"{path.name} {image.width()}x{image.height()}")
            state["index"] += 1
            advance()

    timer = QTimer()
    timer.setInterval(120)
    timer.timeout.connect(tick)
    timer.start()
    QTimer.singleShot(40000, app.quit)
    qapp.exec()
    timer.stop()
    print("CAPTURED", results)


if __name__ == "__main__":
    main()
