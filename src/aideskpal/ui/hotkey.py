"""System-wide hotkey registration for hiding the pet.

The desktop pet is usually unfocused when the user wants it gone, so a
window-local ``QShortcut`` would never fire.  On Windows this module therefore
registers a real global hotkey through ``RegisterHotKey`` and receives the
resulting ``WM_HOTKEY`` messages with a Qt native event filter, mirroring how the
tray menu hotkey already works.

The user-visible sequence is a plain string such as ``"Ctrl+Alt+H"``; see
:func:`parse_sequence` for the accepted key names.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

# A distinct id from the tray menu hotkey so both can be registered at once.
_HOTKEY_ID = 0xA1D6
_WM_HOTKEY = 0x0312
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008
_MOD_NOREPEAT = 0x4000

_MODIFIERS = {
    "CTRL": _MOD_CONTROL,
    "CONTROL": _MOD_CONTROL,
    "ALT": _MOD_ALT,
    "SHIFT": _MOD_SHIFT,
    "WIN": _MOD_WIN,
    "META": _MOD_WIN,
    "SUPER": _MOD_WIN,
}

_NAMED_KEYS = {
    "SPACE": 0x20,
    "TAB": 0x09,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "ENTER": 0x0D,
    "RETURN": 0x0D,
    "BACKSPACE": 0x08,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
}

DEFAULT_SEQUENCE = "Ctrl+Alt+H"


def parse_sequence(sequence: str) -> tuple[int, int] | None:
    """Translate ``"Ctrl+Alt+H"`` into ``(modifier_mask, virtual_key)``.

    Returns ``None`` when the text is not a usable hotkey, so callers can fall
    back to a default instead of registering a broken combination.  A bare key
    with no modifier is rejected: a global hotkey that swallows plain letters
    would make the desktop unusable.
    """
    if not sequence:
        return None
    parts = [part.strip().upper() for part in sequence.replace(" ", "").split("+") if part.strip()]
    if not parts:
        return None
    key = parts[-1]
    modifiers = 0
    for part in parts[:-1]:
        bit = _MODIFIERS.get(part)
        if bit is None:
            return None
        modifiers |= bit
    if modifiers == 0:
        return None
    if key in _NAMED_KEYS:
        virtual_key = _NAMED_KEYS[key]
    elif len(key) == 1 and (key.isalpha() or key.isdigit()):
        virtual_key = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        virtual_key = 0x70 + int(key[1:]) - 1
    else:
        return None
    return modifiers, virtual_key


def describe(virtual_key: int, modifiers: int) -> str:
    """Rebuild a readable label from a parsed combination."""
    names = []
    if modifiers & _MOD_CONTROL:
        names.append("Ctrl")
    if modifiers & _MOD_ALT:
        names.append("Alt")
    if modifiers & _MOD_SHIFT:
        names.append("Shift")
    if modifiers & _MOD_WIN:
        names.append("Win")
    if 0x70 <= virtual_key <= 0x87:
        names.append(f"F{virtual_key - 0x70 + 1}")
    elif 0x41 <= virtual_key <= 0x5A or 0x30 <= virtual_key <= 0x39:
        names.append(chr(virtual_key))
    else:
        for name, code in _NAMED_KEYS.items():
            if code == virtual_key:
                names.append(name.title())
                break
    return "+".join(names)


class _HotkeyFilter(QAbstractNativeEventFilter):
    """Deliver ``WM_HOTKEY`` for our id to the registered callback."""

    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # type: ignore[override]
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                    self._callback()
                    return True, 0
        except (TypeError, ValueError, OSError):
            pass
        return False, 0


class GlobalHotkey:
    """Own at most one registered global hotkey at a time."""

    def __init__(self) -> None:
        self._filter: _HotkeyFilter | None = None
        self._registered = False
        self.sequence = ""

    @property
    def active(self) -> bool:
        return self._registered

    def register(self, sequence: str, callback: Callable[[], None]) -> bool:
        """Register *sequence*; returns False when it could not be claimed."""
        self.unregister()
        if sys.platform != "win32":
            logger.info("Global hotkeys are only supported on Windows")
            return False
        parsed = parse_sequence(sequence)
        if parsed is None:
            logger.warning("Cannot parse hide hotkey %r", sequence)
            return False
        modifiers, virtual_key = parsed
        try:
            if not ctypes.windll.user32.RegisterHotKey(
                None, _HOTKEY_ID, modifiers | _MOD_NOREPEAT, virtual_key
            ):
                logger.warning("Hotkey %r is already taken by another application", sequence)
                return False
            app = QApplication.instance()
            if app is None:
                ctypes.windll.user32.UnregisterHotKey(None, _HOTKEY_ID)
                return False
            self._filter = _HotkeyFilter(callback)
            app.installNativeEventFilter(self._filter)
            self._registered = True
            self.sequence = describe(virtual_key, modifiers)
            logger.info("Hide hotkey registered: %s", self.sequence)
            return True
        except (AttributeError, OSError):
            logger.exception("Could not register the hide hotkey")
            return False

    def unregister(self) -> None:
        if self._registered and sys.platform == "win32":
            try:
                ctypes.windll.user32.UnregisterHotKey(None, _HOTKEY_ID)
            except (AttributeError, OSError):
                logger.exception("Could not unregister the hide hotkey")
        self._registered = False
        if self._filter is not None:
            app = QApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self._filter)
            self._filter = None
