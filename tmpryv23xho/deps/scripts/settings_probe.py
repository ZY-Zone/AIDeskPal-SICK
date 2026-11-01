"""Open the settings dialog and capture it for UI smoke checks."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
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
    app = DesktopPetApp(qapp, paths, store, no_single_instance=True)
    out = Path("probes/settings.png")

    def open_dialog() -> None:
        app.open_settings()

    def capture() -> None:
        dialog = app.settings_dialog
        if dialog:
            dialog.grab().save(str(out))
            print("captured", out, dialog.size())
            dialog.close()
        app.quit()

    QTimer.singleShot(900, open_dialog)
    QTimer.singleShot(2400, capture)
    QTimer.singleShot(6000, app.quit)
    return qapp.exec()


if __name__ == "__main__":
    raise SystemExit(main())
