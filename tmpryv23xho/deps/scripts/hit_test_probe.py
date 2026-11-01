"""Verify transparent-window click-through on Windows using WindowFromPoint."""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

os.environ.setdefault("AIDESKPAL_MODEL", str(Path("sample_content/starling/model.pmx").resolve()))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from aideskpal.app import DesktopPetApp, configure_surface_format
from aideskpal.config import SettingsStore
from aideskpal.logging_setup import setup_logging
from aideskpal.paths import get_paths


def main() -> int:
    configure_surface_format()
    qapp = QApplication(sys.argv[:1])
    qapp.setQuitOnLastWindowClosed(False)
    paths = get_paths().ensure()
    setup_logging(paths.logs_file, console=False)
    store = SettingsStore(paths)
    store.load()
    store.config.window.click_through_transparent = True
    app = DesktopPetApp(qapp, paths, store, no_single_instance=True)
    user32 = ctypes.windll.user32

    def probe() -> None:
        pet = app.pet
        mask = pet._alpha_mask
        if mask is None:
            print("NO_MASK")
            app.quit()
            return
        h, w = mask.shape
        dpr = pet.devicePixelRatio() or 1.0
        true_points = [(x, y) for y in range(0, h, 7) for x in range(0, w, 7) if mask[y, x]]
        all_points = [(x, y) for y in range(0, h, 7) for x in range(0, w, 7)]
        false_points = [(x, y) for x, y in all_points if not mask[y, x]]
        GA_ROOT = 2
        hwnd = int(user32.GetAncestor(int(pet.winId()), GA_ROOT))
        print("HWND", hwnd, "MASK", h, w, "true", len(true_points), "false", len(false_points))

        def window_at(px: int, py: int) -> int:
            # Win32 screen coordinates are physical pixels; Qt positions are logical.
            screen_x = int(pet.x() * dpr + px)
            screen_y = int(pet.y() * dpr + (h - 1 - py))
            user32.SetCursorPos(screen_x, screen_y)
            qapp.processEvents()
            time.sleep(0.2)
            qapp.processEvents()
            point = wintypes.POINT(screen_x, screen_y)
            return int(user32.GetAncestor(user32.WindowFromPoint(point), GA_ROOT))

        if true_points:
            tx, ty = true_points[len(true_points) // 2]
            print("CHARACTER_POINT", tx, ty, "window", window_at(tx, ty), "is_pet", window_at(tx, ty) == hwnd)
        if false_points:
            fx, fy = false_points[len(false_points) // 2]
            print("TRANSPARENT_POINT", fx, fy, "window", window_at(fx, fy), "is_pet", window_at(fx, fy) == hwnd)
        app.quit()

    QTimer.singleShot(2800, probe)
    QTimer.singleShot(9000, app.quit)
    return qapp.exec()


if __name__ == "__main__":
    raise SystemExit(main())
