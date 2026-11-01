"""Small QThread wrapper for network and AI work that must not block the UI."""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)


class FunctionWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, function: Callable[[], Any], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._function = function
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:  # noqa: D401
        try:
            result = self._function()
        except Exception as exc:
            if not self._cancelled:
                logger.exception("Background task failed")
                self.failed.emit(str(exc) or type(exc).__name__)
            return
        if not self._cancelled:
            self.completed.emit(result)


class WorkerPool(QObject):
    """Keeps worker threads alive until they finish."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._workers: set[FunctionWorker] = set()

    def start(
        self,
        function: Callable[[], Any],
        *,
        on_result: Callable[[Any], None],
        on_error: Callable[[str], None] | None = None,
    ) -> FunctionWorker:
        worker = FunctionWorker(function, self)
        self._workers.add(worker)

        def cleanup() -> None:
            self._workers.discard(worker)
            worker.deleteLater()

        worker.completed.connect(on_result)
        if on_error is not None:
            worker.failed.connect(on_error)
        worker.finished.connect(cleanup)
        worker.start()
        return worker

    def stop(self) -> None:
        for worker in list(self._workers):
            worker.cancel()
            worker.wait(1500)
        self._workers.clear()
