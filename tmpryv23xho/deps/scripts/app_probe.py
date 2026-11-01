"""End-to-end desktop probe: transparency mask, bubble, drag, offline chat, settings save."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
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
    setup_logging(paths.logs_file, console=True)
    store = SettingsStore(paths)
    store.load()
    app = DesktopPetApp(qapp, paths, store, no_single_instance=True)
    results: dict[str, object] = {}

    def step_one() -> None:
        pet = app.pet
        mask = pet._alpha_mask if pet else None
        results["mask"] = None if mask is None else (mask.shape, int(mask.sum()))
        results["snapshot"] = app.perception.snapshot()
        print("MASK", results["mask"])
        print("IDLE", app.perception.snapshot().idle_seconds, "MODEL", app.config.model.id, "ACTIONS", len(app.actions))
        print("ACTION_NOW", pet.current_action_id if pet else None)
        app.speak("这是气泡测试：星星已经就位。", style="star")
        app.pet.capture(Path("probes/app_probe_pet.png"))
        screen = QApplication.primaryScreen()
        if screen:
            screen.grabWindow(0).save("probes/app_probe_desktop.png")
        QTimer.singleShot(400, step_two)

    def step_two() -> None:
        pet = app.pet
        assert pet is not None
        before = pet.current_action_id
        pet._window_origin = pet.position()
        pet._begin_drag()
        pet._drag_vx = 240.0
        pet._drag_vy = -80.0
        pet._apply_drag_overlay()
        print("DRAG_ACTION", pet.current_action_id, "overlay", len(pet.player._overlays))
        pet._end_drag()
        print("END_DRAG_ACTION", pet.current_action_id, "was", before)
        app.open_chat()
        QTimer.singleShot(300, step_three)

    def step_three() -> None:
        assert app.chat is not None
        app.chat._input.setText("你好，今天有点累。")
        app.chat._submit()
        QTimer.singleShot(2500, step_four)

    def step_four() -> None:
        print("CHAT_BUBBLE", app.bubble.isVisible() if app.bubble else None)
        print("LAST_RESULT", app.brain.last_result.source if app.brain.last_result else None,
              app.brain.last_result.action_id if app.brain.last_result else None,
              app.brain.last_result.speech if app.brain.last_result else None)
        screen = QApplication.primaryScreen()
        if screen:
            screen.grabWindow(0).save("probes/app_probe_chat.png")
        app.open_settings()
        QTimer.singleShot(800, step_five)

    def step_five() -> None:
        dialog = app.settings_dialog
        if dialog is None:
            print("SETTINGS missing")
            app.quit()
            return
        dialog.bubble_seconds.setValue(9)
        old = app.config.ui.bubble_seconds
        dialog._save()
        print("SETTINGS_SAVED", old, "->", app.config.ui.bubble_seconds, "dialog", app.settings_dialog)
        QTimer.singleShot(500, app.quit)

    QTimer.singleShot(2600, step_one)
    QTimer.singleShot(16000, app.quit)
    return qapp.exec()


if __name__ == "__main__":
    raise SystemExit(main())
