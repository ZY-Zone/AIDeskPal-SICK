"""Immutable context snapshot shared by the UI and the AI layer."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class PerceptionSnapshot:
    captured_at: float = field(default_factory=time.time)
    process_name: str = ""
    window_title: str = ""
    app_category: str = "other"
    is_private: bool = False
    idle_seconds: float = 0.0
    typing_rate: float = 0.0
    typed_recently: bool = False
    recent_keys: tuple[str, ...] = ()
    app_switch_count: int = 0
    session_minutes: int = 0

    @property
    def is_idle(self) -> bool:
        return self.idle_seconds >= 180

    @property
    def app_label(self) -> str:
        if self.is_private:
            return "受保护的窗口"
        return self.process_name or "桌面"

    def public_dict(self) -> dict[str, object]:
        if self.is_private:
            return {
                "application": "protected",
                "window_title": "",
                "category": "private",
                "is_private": True,
            }
        return {
            "application": self.process_name,
            "window_title": self.window_title,
            "category": self.app_category,
            "is_private": False,
        }
