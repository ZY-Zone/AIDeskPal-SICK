"""Structured outputs exchanged between planner, actor and replier."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from aideskpal.ai.character import CharacterProfile
from aideskpal.perception.snapshot import PerceptionSnapshot


EMOTIONS = {
    "calm",
    "happy",
    "excited",
    "shy",
    "sad",
    "angry",
    "curious",
    "sleepy",
    "surprised",
    "affectionate",
    "proud",
    "neutral",
}

BUBBLE_STYLES = {"soft", "star", "warm", "none"}


@dataclass(slots=True)
class AIContext:
    trigger: str
    user_text: str
    snapshot: PerceptionSnapshot
    current_action: str | None
    recent_actions: list[str]
    recent_memory: list[dict[str, Any]]
    interaction_count: int
    affinity: int
    local_time: str
    part_of_day: str
    session_minutes: int
    raw_keys_enabled: bool = False
    character: CharacterProfile | None = None
    long_term: list[dict[str, Any]] = field(default_factory=list)
    memory_recalled: bool = False
    # False while the pet is tucked away in the tray: the user cannot see a
    # speech bubble, so the Replier is not available this turn.
    replier_available: bool = True

    def to_prompt(self) -> dict[str, Any]:
        activity = self.snapshot.public_dict()
        if self.raw_keys_enabled and not self.snapshot.is_private:
            activity["recent_key_labels"] = list(self.snapshot.recent_keys[-10:])
        return {
            "local_time": self.local_time,
            "part_of_day": self.part_of_day,
            "session_minutes": self.session_minutes,
            "idle_seconds": int(self.snapshot.idle_seconds),
            "typing_per_minute": int(self.snapshot.typing_rate),
            "typed_recently": self.snapshot.typed_recently,
            "app_switches_last_10m": self.snapshot.app_switch_count,
            "activity": activity,
            "desktop_pet": {
                "current_action": self.current_action,
                "recent_actions": self.recent_actions[-5:],
                "replier_available": self.replier_available,
            },
            "interaction_count": self.interaction_count,
            "affinity": self.affinity,
            "recent_memory": self.recent_memory[-5:],
            "trigger": self.trigger,
            "user_message": self.user_text,
            "character": self.character.summary() if self.character else None,
            "long_term_memory": self.long_term,
            "memory_recall_performed": self.memory_recalled,
        }


@dataclass(slots=True)
class Plan:
    intent: str = "observe"
    emotion: str = "neutral"
    should_speak: bool = False
    should_act: bool = False
    speech_goal: str = ""
    replier_brief: str = ""
    should_recall: bool = False
    recall_query: str = ""
    memory_write: str = ""
    memory_importance: float = 0.5
    actor_brief: str = ""
    action_candidates: list[str] = field(default_factory=list)
    intensity: float = 0.5
    reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Plan":
        candidates = data.get("action_candidates", [])
        if not isinstance(candidates, list):
            candidates = []
        emotion = str(data.get("emotion", "neutral")).strip().lower()
        if emotion not in EMOTIONS:
            emotion = "neutral"
        intensity = data.get("intensity", 0.5)
        try:
            intensity = max(0.0, min(1.0, float(intensity)))
        except (TypeError, ValueError):
            intensity = 0.5
        speech_goal = str(data.get("speech_goal", ""))[:240]
        replier_brief = str(data.get("replier_brief", "")).strip()[:700]
        actor_brief = str(data.get("actor_brief", "")).strip()[:500]
        recall_query = str(data.get("recall_query", "")).strip()[:300]
        try:
            importance = max(0.0, min(1.0, float(data.get("memory_importance", 0.5))))
        except (TypeError, ValueError):
            importance = 0.5
        return cls(
            intent=str(data.get("intent", "observe"))[:120],
            emotion=emotion,
            should_speak=bool(data.get("should_speak", False)),
            should_act=bool(data.get("should_act", False)),
            speech_goal=speech_goal,
            replier_brief=replier_brief or speech_goal,
            should_recall=bool(data.get("should_recall", bool(recall_query))),
            recall_query=recall_query,
            memory_write=str(data.get("memory_write", "")).strip()[:1000],
            memory_importance=importance,
            actor_brief=actor_brief or str(data.get("reason", ""))[:240],
            action_candidates=[str(item) for item in candidates if isinstance(item, str)][:4],
            intensity=intensity,
            reason=str(data.get("reason", ""))[:300],
            raw=data,
        )


@dataclass(slots=True)
class ActorDecision:
    action_id: str | None = None
    hold_seconds: float = 0.0
    reason: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActorDecision":
        action = data.get("action_id")
        if action is not None:
            action = str(action).strip()
            if action in {"", "none", "null", "None"}:
                action = None
        try:
            hold = max(0.0, min(120.0, float(data.get("hold_seconds", 0.0))))
        except (TypeError, ValueError):
            hold = 0.0
        return cls(action_id=action, hold_seconds=hold, reason=str(data.get("reason", ""))[:240])


@dataclass(slots=True)
class Reply:
    text: str = ""
    emotion: str = "neutral"
    bubble_style: str = "soft"
    reason: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reply":
        text = str(data.get("text", "")).strip()
        # Bubble-friendly: normalize accidental markdown/newline noise.
        text = " ".join(text.split())
        if len(text) > 220:
            text = text[:217].rstrip("，,。 ") + "…"
        emotion = str(data.get("emotion", "neutral")).strip().lower()
        if emotion not in EMOTIONS:
            emotion = "neutral"
        style = str(data.get("bubble_style", "soft")).strip().lower()
        if style not in BUBBLE_STYLES:
            style = "soft"
        return cls(
            text=text,
            emotion=emotion,
            bubble_style=style,
            reason=str(data.get("reason", data.get("expression_note", "")))[:240],
        )


@dataclass(slots=True)
class AgentTrace:
    """Safe, structured decision summaries for the thought-process window.

    These are deliberately model-authored short explanations, never hidden CoT,
    prompts, credentials or raw perception payloads.
    """

    role: str
    model: str = ""
    status: str = "done"
    summary: str = ""
    detail: str = ""
    duration_ms: int = 0


@dataclass(slots=True)
class BrainResult:
    source: str = "offline"
    trigger: str = "timer"
    speech: str = ""
    emotion: str = "neutral"
    bubble_style: str = "soft"
    action_id: str | None = None
    plan: Plan | None = None
    actor_decision: ActorDecision | None = None
    reply: Reply | None = None
    trace: list[AgentTrace] = field(default_factory=list)
    error: str = ""
    duration_ms: int = 0
    created_at: float = field(default_factory=time.time)
    skipped_reason: str = ""

    @property
    def did_anything(self) -> bool:
        return bool(self.speech or self.action_id)
