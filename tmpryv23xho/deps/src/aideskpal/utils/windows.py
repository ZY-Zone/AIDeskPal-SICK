"""Small Windows integration helpers (foreground window, idle time, startup)."""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
else:  # pragma: no cover - development on non-Windows
    _user32 = None
    _kernel32 = None


@dataclass(slots=True)
class WindowInfo:
    title: str = ""
    process_name: str = ""
    pid: int = 0


def foreground_window() -> WindowInfo:
    if not _user32:
        return WindowInfo()
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return WindowInfo()
    length = _user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(max(1, length + 1))
    _user32.GetWindowTextW(hwnd, buffer, len(buffer))
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return WindowInfo(title=buffer.value, pid=int(pid.value))


def idle_seconds() -> float:
    if not _user32:
        return 0.0

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    # GetLastInputInfo uses a 32-bit tick count; do modular subtraction to handle
    # the ~49 day wrap instead of subtracting it from the 64-bit uptime.
    tick = int(_kernel32.GetTickCount()) & 0xFFFFFFFF
    elapsed = (tick - int(info.dwTime)) & 0xFFFFFFFF
    return min(float(elapsed) / 1000.0, 7 * 86400.0)


def set_autostart(app_name: str, executable: str, enabled: bool) -> bool:
    """Register a per-user Run entry.  Returns True on success."""
    if not _user32 or sys.platform != "win32":
        return False
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, executable)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def autostart_enabled(app_name: str) -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, app_name)
            return bool(value)
    except OSError:
        return False


def process_name(pid: int) -> str:
    if not _kernel32 or sys.platform != "win32" or pid <= 0:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return Path(buffer.value).name
    except Exception:
        pass
    finally:
        _kernel32.CloseHandle(handle)
    return ""


APP_CATEGORIES: dict[str, tuple[str, ...]] = {
    "code": (
        "code.exe",
        "cursor.exe",
        "devenv.exe",
        "pycharm64.exe",
        "idea64.exe",
        "webstorm64.exe",
        "rider64.exe",
        "sublime_text.exe",
        "notepad++.exe",
        "windowsterminal.exe",
        "powershell.exe",
        "pwsh.exe",
        "cmd.exe",
        "wt.exe",
        "git-bash.exe",
        "wsl.exe",
        "vim.exe",
        "nvim.exe",
    ),
    "browser": (
        "chrome.exe",
        "msedge.exe",
        "firefox.exe",
        "brave.exe",
        "opera.exe",
        "vivaldi.exe",
        "arc.exe",
    ),
    "game": (
        "steam.exe",
        "steamwebhelper.exe",
        "genshinimpact.exe",
        "yuanshen.exe",
        "starrail.exe",
        "osu!.exe",
        "league of legends.exe",
        "valorant.exe",
        "minecraft.exe",
        "javaw.exe",
    ),
    "office": (
        "winword.exe",
        "excel.exe",
        "powerpnt.exe",
        "onenote.exe",
        "notion.exe",
        "obsidian.exe",
        "typora.exe",
        "wps.exe",
        "et.exe",
        "acrobat.exe",
        "sumatrapdf.exe",
    ),
    "media": (
        "vlc.exe",
        "mpv.exe",
        "potplayermini64.exe",
        "spotify.exe",
        "cloudmusic.exe",
        "qqmusic.exe",
        "bilibili.exe",
    ),
    "chat": (
        "wechat.exe",
        "weixin.exe",
        "qq.exe",
        "telegram.exe",
        "discord.exe",
        "slack.exe",
        "teams.exe",
        "dingtalk.exe",
    ),
    "design": (
        "photoshop.exe",
        "illustrator.exe",
        "blender.exe",
        "3dsmax.exe",
        "maya.exe",
        "krita.exe",
        "clipstudiopaint.exe",
        "figma.exe",
    ),
}


def app_category(process: str, title: str = "") -> str:
    lower = process.casefold()
    for category, names in APP_CATEGORIES.items():
        if lower in names:
            return category
    title_lower = title.casefold()
    if any(word in title_lower for word in ("visual studio", "code", "powershell", "终端")):
        return "code"
    if any(word in title_lower for word in ("游戏", "game", "原神", "崩坏")):
        return "game"
    return "other"


def is_fullscreen_foreground() -> bool:
    """Best-effort detection used to hide a topmost pet during games/videos."""
    if not _user32:
        return False
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return False
    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    screen_w = _user32.GetSystemMetrics(0)
    screen_h = _user32.GetSystemMetrics(1)
    return (rect.right - rect.left) >= screen_w - 2 and (rect.bottom - rect.top) >= screen_h - 2


def reveal_in_explorer(path: Path) -> None:
    if sys.platform == "win32" and path.exists():
        os.startfile(path)  # type: ignore[attr-defined]
