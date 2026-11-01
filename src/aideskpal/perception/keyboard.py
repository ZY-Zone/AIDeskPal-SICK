"""Global keyboard activity aggregation on Windows.

Only timing, counts and coarse key categories are kept by default.  Raw key
labels are optional, never persisted, and excluded from the AI prompt unless the
user explicitly enables them.  The hook runs in its own thread with a message
pump, because WH_KEYBOARD_LL requires the installing thread to pump messages.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from collections import Counter, deque
from ctypes import wintypes
from typing import Callable

logger = logging.getLogger(__name__)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


def _configure_user32() -> None:
    """Declare 64-bit hook prototypes.

    Without LPARAM/WPARAM argument types, ctypes defaults to C int.  A real
    64-bit keyboard hook LPARAM can exceed 2^31, producing the
    ``OverflowError: int too long to convert`` spam seen in the console.
    """
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    user32.SetWindowsHookExW.argtypes = (
        ctypes.c_int,
        HOOKPROC,
        wintypes.HINSTANCE,
        wintypes.DWORD,
    )
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.CallNextHookEx.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.CallNextHookEx.restype = LRESULT
    user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = (
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    )
    user32.GetMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
    user32.DispatchMessageW.restype = LRESULT
    user32.PostThreadMessageW.argtypes = (
        wintypes.DWORD,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.PostThreadMessageW.restype = wintypes.BOOL


_configure_user32()


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


_KEY_NAMES = {
    0x08: "Backspace",
    0x09: "Tab",
    0x0D: "Enter",
    0x10: "Shift",
    0x11: "Ctrl",
    0x12: "Alt",
    0x1B: "Esc",
    0x20: "Space",
    0x21: "PageUp",
    0x22: "PageDown",
    0x23: "End",
    0x24: "Home",
    0x25: "Left",
    0x26: "Up",
    0x27: "Right",
    0x28: "Down",
    0x2E: "Delete",
    0x5B: "Win",
}


def _key_label(vk: int) -> str:
    if vk in _KEY_NAMES:
        return _KEY_NAMES[vk]
    if 0x30 <= vk <= 0x39:
        return "digit"
    if 0x41 <= vk <= 0x5A:
        return "letter"
    if 0x70 <= vk <= 0x87:
        return "function"
    if vk == 0x0D or vk == 0x20:
        return _KEY_NAMES.get(vk, "key")
    return "other"


class KeyboardWatcher:
    def __init__(
        self,
        *,
        raw_keys: bool = False,
        on_key: Callable[[str], None] | None = None,
    ) -> None:
        self.raw_keys = raw_keys
        self.on_key = on_key
        self._lock = threading.RLock()
        self._timestamps: deque[float] = deque(maxlen=1024)
        self._recent: deque[str] = deque(maxlen=16)
        self._categories: Counter[str] = Counter()
        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._hook = None
        self._running = False
        self.total_events = 0
        self.last_activity = 0.0
        self.last_error = ""
        self._callback_ref = None

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> bool:
        if self._running:
            return True
        if sys.platform != "win32":
            self.last_error = "keyboard hook is Windows-only"
            return False
        self._running = True
        self._thread = threading.Thread(target=self._thread_main, name="keyboard-hook", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        if self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        self._thread = None
        self._thread_id = 0

    def set_raw_keys(self, enabled: bool) -> None:
        with self._lock:
            self.raw_keys = bool(enabled)
            if not enabled:
                self._recent.clear()

    def feed(self, label: str = "letter") -> None:
        """Record a synthetic key press (used by tests and preview mode)."""
        now = time.monotonic()
        with self._lock:
            self._timestamps.append(now)
            self._categories[label] += 1
            if self.raw_keys:
                self._recent.append(label)
            self.total_events += 1
            self.last_activity = time.time()
        if self.on_key is not None:
            try:
                self.on_key(label)
            except Exception:
                logger.exception("keyboard callback failed")

    def stats(self) -> tuple[float, bool, tuple[str, ...]]:
        now = time.monotonic()
        with self._lock:
            while self._timestamps and now - self._timestamps[0] > 60.0:
                self._timestamps.popleft()
            rate = float(len(self._timestamps))
            typed_recently = bool(self._timestamps) and (now - self._timestamps[-1] < 8.0)
            recent = tuple(item for item in self._recent if item) if self.raw_keys else ()
            return rate, typed_recently, recent

    def category_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._categories)

    def _thread_main(self) -> None:
        try:
            self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
            self._callback_ref = HOOKPROC(self._low_level_handler)
            self._hook = ctypes.windll.user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, self._callback_ref, None, 0
            )
            if not self._hook:
                self.last_error = f"SetWindowsHookExW failed: {ctypes.get_last_error()}"
                logger.warning(self.last_error)
                self._running = False
                return
            logger.info("Global keyboard activity hook installed")
            msg = wintypes.MSG()
            while self._running:
                result = ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result <= 0:
                    break
                ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("Keyboard hook failed")
        finally:
            try:
                if self._hook:
                    ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
            self._hook = None
            self._running = False
            logger.info("Global keyboard hook stopped")

    def _low_level_handler(self, n_code: int, w_param: int, l_param: int) -> int:
        try:
            if n_code >= 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not (info.flags & LLKHF_INJECTED):
                    label = _key_label(int(info.vkCode))
                    self.feed(label)
        except Exception:
            logger.exception("Error in keyboard hook callback")
        return ctypes.windll.user32.CallNextHookEx(None, n_code, w_param, l_param)
