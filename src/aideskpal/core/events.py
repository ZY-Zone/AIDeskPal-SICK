"""A tiny thread-safe event bus used by plugins and UI components."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

Callback = Callable[..., Any]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[tuple[object, Callback]]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, event: str, callback: Callback, owner: object | None = None) -> None:
        with self._lock:
            self._subscribers[event].append((owner or callback, callback))

    def unsubscribe(self, event: str, owner: object) -> None:
        with self._lock:
            self._subscribers[event] = [
                (item_owner, callback)
                for item_owner, callback in self._subscribers.get(event, [])
                if item_owner is not owner
            ]

    def unsubscribe_owner(self, owner: object) -> None:
        with self._lock:
            for event in list(self._subscribers):
                self._subscribers[event] = [
                    (item_owner, callback)
                    for item_owner, callback in self._subscribers[event]
                    if item_owner is not owner
                ]

    def emit(self, event: str, **payload: Any) -> None:
        with self._lock:
            callbacks = list(self._subscribers.get(event, []))
        for _owner, callback in callbacks:
            try:
                callback(**payload)
            except Exception:
                logger.exception("Plugin event handler failed for %s", event)
