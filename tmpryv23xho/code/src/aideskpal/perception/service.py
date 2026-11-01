"""Background perception service combining foreground, idle and keyboard signals."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

from aideskpal.config import PerceptionConfig
from aideskpal.perception.keyboard import KeyboardWatcher
from aideskpal.perception.snapshot import PerceptionSnapshot
from aideskpal.utils.windows import (
    WindowInfo,
    app_category,
    foreground_window,
    idle_seconds,
    process_name,
)

logger = logging.getLogger(__name__)


class PerceptionService:
    def __init__(self, config: PerceptionConfig) -> None:
        self._config = config
        self._lock = threading.RLock()
        self._keyboard = KeyboardWatcher(raw_keys=config.raw_keys_enabled)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._snapshot = PerceptionSnapshot()
        self._session_started = time.time()
        self._switches: deque[float] = deque(maxlen=200)
        self._last_process = ""
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def update_config(self, config: PerceptionConfig) -> None:
        with self._lock:
            self._config = config
        self._keyboard.set_raw_keys(config.raw_keys_enabled)
        if config.keyboard_enabled and not self._keyboard.running:
            self._keyboard.start()
        elif not config.keyboard_enabled and self._keyboard.running:
            self._keyboard.stop()

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        if self._config.keyboard_enabled:
            self._keyboard.start()
        self._thread = threading.Thread(target=self._run, name="perception", daemon=True)
        self._thread.start()
        self._refresh()
        logger.info("Perception service started (keyboard=%s)", self._keyboard.running)

    def stop(self) -> None:
        self._started = False
        self._stop.set()
        self._keyboard.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._refresh()
            except Exception:
                logger.exception("Perception refresh failed")
            poll = max(1.0, float(self._config.poll_seconds))
            self._stop.wait(poll)

    def _window_details(self, info: WindowInfo) -> tuple[str, str, bool]:
        process = info.process_name or process_name(info.pid)
        title = info.title
        combined_process = process.casefold()
        combined_title = title.casefold()
        excluded_apps = [str(item).casefold() for item in self._config.excluded_apps if item]
        excluded_titles = [
            str(item).casefold() for item in self._config.excluded_title_keywords if item
        ]
        private = any(item in combined_process for item in excluded_apps) or any(
            item in combined_title for item in excluded_titles
        )
        if not self._config.share_window_titles:
            title = ""
        return ("" if private else process, "" if private else title, private)

    def _refresh(self) -> None:
        if self._config.foreground_enabled:
            info = foreground_window()
            if not info.process_name:
                info.process_name = process_name(info.pid)
            process, title, private = self._window_details(info)
            category = "private" if private else app_category(process, title)
        else:
            process, title, private, category = "", "", False, "unavailable"
        idle = idle_seconds() if self._config.idle_enabled else 0.0
        rate, typed_recently, recent_keys = self._keyboard.stats()
        now = time.monotonic()
        with self._lock:
            if process and process != self._last_process:
                if self._last_process:
                    self._switches.append(now)
                self._last_process = process
            while self._switches and now - self._switches[0] > 600:
                self._switches.popleft()
            self._snapshot = PerceptionSnapshot(
                process_name=process,
                window_title=title,
                app_category=category,
                is_private=private,
                idle_seconds=idle,
                typing_rate=rate,
                typed_recently=typed_recently,
                recent_keys=recent_keys,
                app_switch_count=len(self._switches),
                session_minutes=int((time.time() - self._session_started) / 60),
            )

    def snapshot(self) -> PerceptionSnapshot:
        with self._lock:
            return self._snapshot

    def inject_keystroke(self, label: str = "letter") -> None:
        """Test / preview helper."""
        self._keyboard.feed(label)
        self._refresh()

    @property
    def keyboard_running(self) -> bool:
        return self._keyboard.running

    @property
    def keyboard_error(self) -> str:
        return self._keyboard.last_error
