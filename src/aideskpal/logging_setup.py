"""Application logging: console + rotating file, with secrets never logged.

File logging is best-effort.  A read-only install folder or a Windows policy that
denies writes must never prevent the desktop pet from starting; in that case we
fall back to the system temp folder, then to a no-op handler.
"""

from __future__ import annotations

import logging
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _file_handler(path: Path, level: int, formatter: logging.Formatter):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=2 * 1024 * 1024, backupCount=4, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        handler.setLevel(level)
        return handler
    except OSError:
        return None


def setup_logging(
    log_path: Path, level: int = logging.INFO, console: bool | None = None
) -> Path | None:
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        try:
            handler.close()
        except Exception:
            pass
        root.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    chosen_path: Path | None = None
    handler = _file_handler(log_path, level, formatter)
    if handler is not None:
        root.addHandler(handler)
        chosen_path = log_path
    else:
        fallback = Path(tempfile.gettempdir()) / "AIDeskPal-SICK" / "aideskpal.log"
        handler = _file_handler(fallback, level, formatter)
        if handler is not None:
            root.addHandler(handler)
            chosen_path = fallback

    if console if console is not None else sys.stderr is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        stream.setLevel(level)
        root.addHandler(stream)

    if not root.handlers:
        root.addHandler(logging.NullHandler())

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    if chosen_path:
        logging.getLogger(__name__).info("Log file: %s", chosen_path)
    return chosen_path
