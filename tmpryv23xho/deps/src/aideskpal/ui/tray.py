"""Native notification-area icon backed by pystray.

Qt is still used for the application and for a small keyboard-accessible
fallback menu, but the tray icon itself is created by pystray's Windows
backend.  pystray callbacks run on its own thread, so every callback only
emits a Qt signal; the actual window/action work stays on the Qt main thread.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Callable
from ctypes import wintypes
from io import BytesIO

from PIL import Image
from PySide6.QtCore import QAbstractNativeEventFilter, QBuffer, QIODevice, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import pystray
from pystray import Menu, MenuItem

from aideskpal.animation.action import ActionClip
from aideskpal.ui.theme import app_font, app_icon

logger = logging.getLogger(__name__)


def _install_pystray_windows_compat() -> None:
    """Work around pystray's optional UIPI call failing on some Windows hosts.

    pystray calls ``ChangeWindowMessageFilterEx`` while creating its hidden
    window.  On restricted/elevated shells this can raise WinError 5 even
    though the call is only needed for Explorer-restart notifications.  The
    icon itself does not depend on it, so ignore that one access-denied result.
    """
    try:
        from pystray._util import win32

        original = win32.ChangeWindowMessageFilterEx

        def safe_change(hwnd, message, action, parameter):
            try:
                return original(hwnd, message, action, parameter)
            except (PermissionError, OSError) as exc:
                logger.warning("pystray UI message filter unavailable: %s", exc)
                return True

        if getattr(win32.ChangeWindowMessageFilterEx, "_aideskpal_safe", False) is False:
            safe_change._aideskpal_safe = True  # type: ignore[attr-defined]
            win32.ChangeWindowMessageFilterEx = safe_change
    except (ImportError, AttributeError):
        pass

_WM_HOTKEY = 0x0312
_HOTKEY_ID = 0xA1D5
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_NOREPEAT = 0x4000
_VK_F12 = 0x7B
_HOTKEY_LABEL = "Ctrl+Alt+F12"


class _HotkeyFilter(QAbstractNativeEventFilter):
    """Receive WM_HOTKEY for the keyboard fallback menu."""

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


def _pystray_image() -> Image.Image:
    """Convert the Qt app icon into a PIL image for pystray."""
    pixmap = app_icon(64).pixmap(64, 64)
    payload = QBuffer()
    payload.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(payload, "PNG"):
        raise RuntimeError("Cannot encode tray icon")
    payload.close()
    return Image.open(BytesIO(bytes(payload.data()))).convert("RGBA")


class TrayController(QObject):
    open_settings = Signal()
    open_onboarding = Signal()
    open_thoughts = Signal()
    toggle_visibility = Signal()
    quit_requested = Signal()
    show_logs = Signal()
    play_action = Signal(str)
    plugin_triggered = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._actions: dict[str, ActionClip] = {}
        self._plugin_actions: dict[str, list[tuple[str, Callable[[], None]]]] = {}
        self._plugin_callbacks: dict[int, Callable[[], None]] = {}
        self._visible = True
        self._status = "静候"
        self._character_name = "桌宠"
        self._icon: pystray.Icon | None = None
        self._icon_started = False
        self._shell_add_ok: bool | None = None
        self._fallback: QWidget | None = None
        self._closing = False
        self._hotkey_filter: _HotkeyFilter | None = None
        self._hotkey_registered = False
        self._menu = QMenu()
        self._menu.setFont(app_font(10))
        self._menu.setStyleSheet(
            "QMenu { background: #1a1728; color: #f3efff; border: 1px solid #332d4a;"
            " padding: 6px; border-radius: 8px; }"
            "QMenu::item { padding: 7px 28px 7px 14px; border-radius: 5px; }"
            "QMenu::item:selected { background: #342b52; }"
            "QMenu::item:disabled { color: #8e87a6; }"
            "QMenu::separator { height: 1px; background: #332d4a; margin: 4px 8px; }"
        )
        self.plugin_triggered.connect(self._run_plugin_callback)
        self._install_hotkey()
        self._rebuild_menu()
        QTimer.singleShot(1200, self._ensure_visible)
        QTimer.singleShot(3000, self._ensure_visible)

    @property
    def available(self) -> bool:
        return bool(pystray.Icon.HAS_MENU)

    def show(self) -> None:
        _install_pystray_windows_compat()
        if self._icon_started:
            if self._icon is not None:
                self._icon.visible = True
            return
        self._install_shell_notify_probe()
        try:
            self._icon = pystray.Icon(
                "AIDeskPal-SICK",
                _pystray_image(),
                "AIDeskPal-SICK · 桌宠",
                menu=self._build_pystray_menu(),
            )
            self._icon.run_detached(setup=self._on_icon_ready)
            self._icon_started = True
            logger.info("pystray icon started (menu=%s)", self.available)
        except Exception:
            logger.exception("Could not start pystray tray icon")
            self._show_fallback_control()

    def _install_shell_notify_probe(self) -> None:
        """Record whether Windows actually accepts NIM_ADD.

        pystray sets ``visible=True`` without checking Shell_NotifyIcon's
        return value.  Some restricted shells reject the call with error 0;
        in that case show a normal taskbar control window so the user can
        still open settings and exit.
        """
        try:
            from pystray._util import win32

            original = win32.Shell_NotifyIcon
            if getattr(original, "_aideskpal_probe", False):
                return
            controller = self

            def probe(code, data):
                try:
                    result = original(code, data)
                except Exception:
                    controller._shell_add_ok = False
                    logger.exception("Shell_NotifyIcon raised")
                    return False
                if code == 0:  # NIM_ADD
                    controller._shell_add_ok = bool(result)
                    logger.info("Shell_NotifyIcon NIM_ADD returned %s", bool(result))
                return result

            probe._aideskpal_probe = True  # type: ignore[attr-defined]
            win32.Shell_NotifyIcon = probe
        except (ImportError, AttributeError):
            logger.exception("Could not install Shell_NotifyIcon probe")

    def _on_icon_ready(self, icon: pystray.Icon) -> None:
        icon.visible = True
        logger.info("pystray icon ready: visible=%s", icon.visible)

    def _ensure_visible(self) -> None:
        if self._icon is None:
            self.show()
            return
        try:
            if not self._icon.visible:
                self._icon.visible = True
            logger.info("pystray state: visible=%s", self._icon.visible)
            if self._shell_add_ok is False and self._fallback is None:
                logger.warning(
                    "Windows rejected Shell_NotifyIcon; using taskbar control window"
                )
                self._show_fallback_control()
        except Exception:
            logger.exception("Could not refresh pystray icon")

    def _show_fallback_control(self) -> None:
        if self._fallback is not None:
            self._fallback.show()
            self._fallback.raise_()
            return
        window = QWidget(None)
        window.setWindowTitle("AIDeskPal-SICK · 托盘不可用")
        window.setMinimumWidth(330)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        layout = QVBoxLayout(window)
        layout.setContentsMargins(18, 18, 18, 14)
        message = QLabel(
            "Windows 没有接受系统托盘图标。\n"
            "你仍然可以用下面的按钮控制程序；也可以按 Ctrl+Alt+F12 打开快捷菜单。"
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        row = QHBoxLayout()
        menu_button = QPushButton("快捷菜单")
        menu_button.clicked.connect(self.show_menu)
        settings_button = QPushButton("设置")
        settings_button.clicked.connect(self.open_settings.emit)
        toggle_button = QPushButton("隐藏/显示桌宠")
        toggle_button.clicked.connect(self.toggle_visibility.emit)
        quit_button = QPushButton("退出")
        quit_button.clicked.connect(self.quit_requested.emit)
        for button in (menu_button, settings_button, toggle_button, quit_button):
            row.addWidget(button)
        layout.addLayout(row)
        window.destroyed.connect(self._on_fallback_destroyed)
        self._fallback = window
        window.show()
        window.raise_()
        window.activateWindow()

    def _on_fallback_destroyed(self) -> None:
        self._fallback = None
        if not self._closing:
            self.quit_requested.emit()

    def show_menu(self) -> None:
        """Keyboard-accessible fallback menu; the tray itself is pystray."""
        self._rebuild_menu()
        self._menu.popup(QCursor.pos())

    def _install_hotkey(self) -> None:
        if sys.platform != "win32":
            return
        try:
            if not ctypes.windll.user32.RegisterHotKey(
                None,
                _HOTKEY_ID,
                _MOD_CONTROL | _MOD_ALT | _MOD_NOREPEAT,
                _VK_F12,
            ):
                logger.warning("Could not register tray menu hotkey %s", _HOTKEY_LABEL)
                return
            app = QApplication.instance()
            if app is None:
                ctypes.windll.user32.UnregisterHotKey(None, _HOTKEY_ID)
                return
            self._hotkey_filter = _HotkeyFilter(self.show_menu)
            app.installNativeEventFilter(self._hotkey_filter)
            self._hotkey_registered = True
            logger.info("Tray menu hotkey registered: %s", _HOTKEY_LABEL)
        except (AttributeError, OSError):
            logger.exception("Could not install tray menu hotkey")

    def _uninstall_hotkey(self) -> None:
        if self._hotkey_registered and sys.platform == "win32":
            try:
                ctypes.windll.user32.UnregisterHotKey(None, _HOTKEY_ID)
            except (AttributeError, OSError):
                logger.exception("Could not unregister tray menu hotkey")
        if self._hotkey_filter is not None:
            app = QApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self._hotkey_filter)
            self._hotkey_filter = None
        self._hotkey_registered = False

    def set_actions(self, actions: dict[str, ActionClip], current_id: str = "") -> None:
        self._actions = dict(actions)
        self._current = current_id
        self._rebuild_menu()

    def set_plugin_actions(
        self, plugin_actions: dict[str, list[tuple[str, Callable[[], None]]]]
    ) -> None:
        self._plugin_actions = {
            plugin_id: list(items) for plugin_id, items in plugin_actions.items() if items
        }
        self._rebuild_menu()

    def set_visible(self, visible: bool) -> None:
        self._visible = visible
        self._rebuild_menu()

    def set_status(self, text: str) -> None:
        self._status = text[:80]
        if self._icon is not None:
            try:
                self._icon.title = f"AIDeskPal-SICK · {self._character_name}\n{self._status}"
            except Exception:
                logger.exception("Could not update pystray tooltip")
        self._rebuild_menu()

    def set_character_name(self, name: str) -> None:
        self._character_name = (name or "桌宠").strip()
        if self._icon is not None:
            try:
                self._icon.title = f"AIDeskPal-SICK · {self._character_name}\n{self._status}"
            except Exception:
                logger.exception("Could not update pystray title")
        self._rebuild_menu()

    def notify(self, title: str, message: str) -> None:
        if self._icon is None:
            return
        try:
            self._icon.notify(message, title)
        except Exception:
            logger.exception("Could not show pystray notification")

    # -------------------------------------------------------------- Qt fallback
    def _rebuild_menu(self) -> None:
        menu = self._menu
        menu.clear()
        header = menu.addAction(f"{self._character_name} · 桌宠")
        header.setEnabled(False)
        status = menu.addAction(self._status)
        status.setEnabled(False)
        hint = menu.addAction(f"托盘/快捷菜单：{_HOTKEY_LABEL}")
        hint.setEnabled(False)
        menu.addSeparator()

        thoughts = menu.addAction("三代理思维过程")
        thoughts.triggered.connect(self.open_thoughts.emit)
        toggle = menu.addAction("隐藏桌宠" if self._visible else "显示桌宠")
        toggle.triggered.connect(self.toggle_visibility.emit)

        action_menu = QMenu("换个动作", menu)
        categories = {
            "idle": "待机",
            "greeting": "问候",
            "emotion": "情绪",
            "reaction": "反应",
            "gesture": "手势",
            "affection": "亲近",
            "dance": "表演",
        }
        for category, label in categories.items():
            items = [
                clip
                for clip in self._actions.values()
                if clip.category == category and clip.ai_visible
            ]
            if not items:
                continue
            action_menu.addSection(label)
            for clip in sorted(items, key=lambda item: item.name):
                action = action_menu.addAction(clip.name)
                action.triggered.connect(
                    lambda checked=False, aid=clip.id: self.play_action.emit(aid)
                )
        if not action_menu.isEmpty():
            menu.addMenu(action_menu)

        plugin_menu = QMenu("插件功能", menu)
        for items in self._plugin_actions.values():
            for label, callback in items:
                action = plugin_menu.addAction(label)
                action.triggered.connect(lambda checked=False, cb=callback: cb())
        if not plugin_menu.isEmpty():
            menu.addMenu(plugin_menu)

        menu.addSeparator()
        settings = menu.addAction("设置…")
        settings.triggered.connect(self.open_settings.emit)
        onboarding = menu.addAction("重新运行初始化向导…")
        onboarding.triggered.connect(self.open_onboarding.emit)
        logs = menu.addAction("查看日志")
        logs.triggered.connect(self.show_logs.emit)
        menu.addSeparator()
        quit_action = menu.addAction("退出 AIDeskPal-SICK")
        quit_action.triggered.connect(self.quit_requested.emit)

        if self._icon is not None:
            try:
                self._icon.menu = self._build_pystray_menu()
                self._icon.update_menu()
            except Exception:
                logger.exception("Could not update pystray menu")

    # ----------------------------------------------------------- pystray native
    def _action_handler(self, action_id: str):
        def handler(icon, item) -> None:
            self.play_action.emit(action_id)

        return handler

    def _plugin_handler(self, token: int):
        def handler(icon, item) -> None:
            self.plugin_triggered.emit(token)

        return handler

    def _build_pystray_menu(self) -> Menu:
        items: list[MenuItem] = [
            MenuItem(f"{self._character_name} · 桌宠", None, enabled=False),
            MenuItem(self._status, None, enabled=False),
            MenuItem(f"快捷菜单：{_HOTKEY_LABEL}", None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("三代理思维过程", lambda icon, item: self.open_thoughts.emit()),
            MenuItem(
                "隐藏桌宠" if self._visible else "显示桌宠",
                lambda icon, item: self.toggle_visibility.emit(),
                default=True,
            ),
        ]

        categories = {
            "idle": "待机",
            "greeting": "问候",
            "emotion": "情绪",
            "reaction": "反应",
            "gesture": "手势",
            "affection": "亲近",
            "dance": "表演",
        }
        action_items: list[MenuItem] = []
        for category, label in categories.items():
            clips = [
                clip
                for clip in self._actions.values()
                if clip.category == category and clip.ai_visible
            ]
            if not clips:
                continue
            if action_items:
                action_items.append(Menu.SEPARATOR)
            action_items.append(MenuItem(label, None, enabled=False))
            for clip in sorted(clips, key=lambda item: item.name):
                action_items.append(
                    MenuItem(clip.name, self._action_handler(clip.id))
                )
        if action_items:
            items.append(MenuItem("换个动作", Menu(*action_items)))

        plugin_items: list[MenuItem] = []
        self._plugin_callbacks = {}
        for items_for_plugin in self._plugin_actions.values():
            for label, callback in items_for_plugin:
                token = len(self._plugin_callbacks)
                self._plugin_callbacks[token] = callback
                plugin_items.append(
                    MenuItem(label, self._plugin_handler(token))
                )
        if plugin_items:
            items.append(MenuItem("插件功能", Menu(*plugin_items)))

        items.extend(
            [
                Menu.SEPARATOR,
                MenuItem("设置…", lambda icon, item: self.open_settings.emit()),
                MenuItem(
                    "重新运行初始化向导…",
                    lambda icon, item: self.open_onboarding.emit(),
                ),
                MenuItem("查看日志", lambda icon, item: self.show_logs.emit()),
                Menu.SEPARATOR,
                MenuItem("退出 AIDeskPal-SICK", lambda icon, item: self.quit_requested.emit()),
            ]
        )
        return Menu(*items)

    def _run_plugin_callback(self, token: int) -> None:
        callback = self._plugin_callbacks.get(token)
        if callback is None:
            return
        try:
            callback()
        except Exception:
            logger.exception("Plugin tray callback failed")

    def close(self) -> None:
        self._closing = True
        self._uninstall_hotkey()
        if self._fallback is not None:
            self._fallback.close()
            self._fallback = None
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                logger.exception("Could not stop pystray icon")
            self._icon = None
        self._icon_started = False
        self._menu.close()
