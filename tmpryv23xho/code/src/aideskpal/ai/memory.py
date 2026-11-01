"""Local, inspectable short-term memory. No raw keystrokes are stored here."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


class AgentMemory:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.data: dict[str, Any] = {
            "version": 1,
            "conversations": [],
            "events": [],
            "interaction_count": 0,
            "affinity": 20,
            "action_timestamps": [],
            "notes": [],
        }
        self.load()

    def load(self) -> None:
        with self._lock:
            if not self.path.is_file():
                return
            try:
                data = json.loads(self.path.read_text(encoding="utf-8-sig"))
                if isinstance(data, dict):
                    self.data.update(data)
            except (OSError, json.JSONDecodeError):
                pass
            self.data["conversations"] = list(self.data.get("conversations", []))[-40:]
            self.data["events"] = list(self.data.get("events", []))[-120:]
            self.data["action_timestamps"] = list(self.data.get("action_timestamps", []))[-200:]
            self.data["notes"] = list(self.data.get("notes", []))[-20:]

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            temporary.replace(self.path)

    # ------------------------------------------------------------------ reads
    @property
    def interaction_count(self) -> int:
        return int(self.data.get("interaction_count", 0))

    @property
    def affinity(self) -> int:
        return max(0, min(100, int(self.data.get("affinity", 20))))

    def recent_conversations(self, limit: int = 8) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.data.get("conversations", []))[-limit:]

    def recent_events(self, limit: int = 8) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.data.get("events", []))[-limit:]

    def recent_actions(self, limit: int = 6) -> list[str]:
        with self._lock:
            actions = [
                item
                for item in self.data.get("events", [])
                if isinstance(item, dict) and item.get("kind") == "action"
            ]
            return [str(item.get("detail", "")) for item in actions[-limit:]]

    def actions_last_hour(self) -> int:
        cutoff = time.time() - 3600
        with self._lock:
            stamps = [
                float(value)
                for value in self.data.get("action_timestamps", [])
                if isinstance(value, (int, float)) and value >= cutoff
            ]
            self.data["action_timestamps"] = stamps
            return len(stamps)

    def seconds_since_action(self) -> float | None:
        with self._lock:
            stamps = self.data.get("action_timestamps", [])
            if not stamps:
                return None
            return time.time() - float(stamps[-1])

    # ----------------------------------------------------------------- writes
    def record_exchange(
        self, user_text: str, assistant_text: str, *, action_id: str | None, source: str
    ) -> None:
        now = time.time()
        with self._lock:
            convo = self.data.setdefault("conversations", [])
            if user_text:
                convo.append(
                    {"role": "user", "text": user_text[:500], "ts": now, "source": source}
                )
            if assistant_text:
                convo.append(
                    {
                        "role": "assistant",
                        "text": assistant_text[:500],
                        "ts": now,
                        "source": source,
                        "action_id": action_id,
                    }
                )
            self.data["conversations"] = convo[-40:]
            self.data["interaction_count"] = self.interaction_count + 1
            self._affinity_delta(1 if user_text else 0)
        self.save()

    def record_event(self, kind: str, detail: str = "", *, action_id: str | None = None) -> None:
        now = time.time()
        with self._lock:
            events = self.data.setdefault("events", [])
            events.append({"kind": kind, "detail": detail[:300], "ts": now, "action_id": action_id})
            self.data["events"] = events[-120:]
        self.save()

    def record_action(self, action_id: str) -> None:
        now = time.time()
        with self._lock:
            stamps = self.data.setdefault("action_timestamps", [])
            stamps.append(now)
            self.data["action_timestamps"] = stamps[-200:]
            events = self.data.setdefault("events", [])
            events.append({"kind": "action", "detail": action_id, "ts": now, "action_id": action_id})
            self.data["events"] = events[-120:]
        self.save()

    def add_affinity(self, amount: int) -> None:
        with self._lock:
            self._affinity_delta(amount)
        self.save()

    def _affinity_delta(self, amount: int) -> None:
        self.data["affinity"] = max(0, min(100, int(self.data.get("affinity", 20)) + int(amount)))

    def add_note(self, note: str) -> None:
        note = note.strip()[:300]
        if not note:
            return
        with self._lock:
            notes = self.data.setdefault("notes", [])
            notes.append({"text": note, "ts": time.time()})
            self.data["notes"] = notes[-20:]
        self.save()

    def clear(self) -> None:
        with self._lock:
            self.data = {
                "version": 1,
                "conversations": [],
                "events": [],
                "interaction_count": 0,
                "affinity": 20,
                "action_timestamps": [],
                "notes": list(self.data.get("notes", [])),
            }
        self.save()

    def export_text(self, limit: int = 20) -> str:
        lines = []
        for item in self.recent_conversations(limit):
            role = "用户" if item.get("role") == "user" else "桌宠"
            lines.append(f"{role}: {item.get('text', '')}")
        return "\n".join(lines)
