"""Planner: the stateful experiencer that owns memory intent and turn shape.

Compared with the earlier implementation this Planner keeps a bounded rolling
state between turns instead of re-deriving everything from a stateless context:

* the last few intents, emotions and gripes, so it can notice repetition,
* an unresolved-thread list (a topic the character meant to return to),
* a compact relationship summary derived from affinity and interaction count.

The state is deliberately small and inspectable.  It is not a hidden transcript:
every field is a short, model-authored summary that also appears in the trace.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from aideskpal.ai.character import CharacterProfile
from aideskpal.ai.client import LLMClient
from aideskpal.ai.prompts import planner_system, wrap_context
from aideskpal.ai.types import AIContext, Plan
from aideskpal.animation.action import ActionClip
from aideskpal.config import AIConfig

STATE_TURNS = 6
OPEN_THREADS = 3


@dataclass(slots=True)
class PlannerState:
    """Bounded rolling memory of the character's own recent inner weather."""

    turns: list[dict[str, Any]] = field(default_factory=list)
    open_threads: list[str] = field(default_factory=list)
    last_intent: str = ""
    last_emotion: str = "neutral"
    # Mirrors whether the Replier can actually reach the user.  Driven by the
    # pet being hidden/restored, and surfaced to the Planner every turn.
    replier_available: bool = True
    replier_notice: str = ""

    def set_replier_available(self, available: bool) -> bool:
        """Record a hide/restore transition; returns True when it changed.

        The transition also leaves a one-shot notice so the Planner hears about
        the change itself, not just the steady state: "the Replier just became
        unavailable" and "the Replier is back".  The notice is cleared once the
        Planner has seen it in a turn.
        """
        available = bool(available)
        if available == self.replier_available:
            return False
        self.replier_available = available
        self.replier_notice = (
            "Replier 刚刚恢复可用：桌宠已从托盘恢复，可以正常说话，也可以回到收起期间攒下的话题。"
            if available
            else "Replier 刚刚变为不可用：桌宠已收起到托盘，本轮起的台词用户看不到；先记在 speech_goal 里。"
        )
        return True

    def consume_replier_notice(self) -> str:
        notice = self.replier_notice
        self.replier_notice = ""
        return notice

    def observe(self, plan: Plan, *, trigger: str, user_text: str) -> None:
        self.turns.append(
            {
                "at": round(time.time(), 3),
                "trigger": trigger,
                "intent": plan.intent,
                "emotion": plan.emotion,
                "spoke": plan.should_speak,
                "acted": plan.should_act,
                "user_text": (user_text or "")[:120],
            }
        )
        del self.turns[:-STATE_TURNS]
        self.last_intent = plan.intent
        self.last_emotion = plan.emotion
        # A memory-worthy promise becomes an open thread the character can
        # return to later without a full recall round trip.
        thread = (plan.memory_write or plan.speech_goal or "").strip()
        if plan.should_speak and thread:
            existing = [item for item in self.open_threads if item != thread]
            self.open_threads = (existing + [thread])[-OPEN_THREADS:]
        # The transition notice is one-shot: the Planner has now seen it.
        self.replier_notice = ""

    def resolve_thread(self, keyword: str) -> None:
        keyword = (keyword or "").strip()
        if not keyword:
            return
        self.open_threads = [
            item for item in self.open_threads if keyword not in item
        ]

    def summary(self, *, affinity: int = 0, interaction_count: int = 0) -> dict[str, Any]:
        """Compact state handed to the Planner as part of its context."""
        if affinity >= 70:
            relationship = "很亲近"
        elif affinity >= 45:
            relationship = "熟悉"
        elif affinity >= 20:
            relationship = "认识不久"
        else:
            relationship = "刚见面"
        recent_emotions = [turn.get("emotion", "") for turn in self.turns[-4:] if turn.get("emotion")]
        return {
            "relationship": relationship,
            "interaction_count": interaction_count,
            "last_intent": self.last_intent,
            "last_emotion": self.last_emotion,
            "recent_emotions": recent_emotions,
            "open_threads": list(self.open_threads),
            "replier_available": self.replier_available,
            "replier_notice": self.replier_notice,
            "recent_turns": [
                {
                    "trigger": turn.get("trigger", ""),
                    "intent": turn.get("intent", ""),
                    "emotion": turn.get("emotion", ""),
                    "spoke": turn.get("spoke", False),
                    "acted": turn.get("acted", False),
                }
                for turn in self.turns[-3:]
            ],
        }

    def reset(self) -> None:
        self.turns.clear()
        self.open_threads.clear()
        self.last_intent = ""
        self.last_emotion = "neutral"
        self.replier_notice = ""


class Planner:
    def __init__(
        self,
        client: LLMClient,
        config: AIConfig,
        actions: list[ActionClip],
        allowed: list[str],
        blocked: list[str],
        character: CharacterProfile | None = None,
        *,
        state: PlannerState | None = None,
    ) -> None:
        self.client = client
        self.config = config
        self.actions = actions
        self.allowed = allowed
        self.blocked = blocked
        self.character = character
        self.state = state if state is not None else PlannerState()

    def plan(self, context: AIContext) -> Plan:
        system = planner_system(
            actions=self.actions,
            allowed=self.allowed,
            blocked=self.blocked,
            autonomy=self.config.autonomy,
            speech_enabled=self.config.speech_enabled,
            proactive=self.config.proactive,
            personality=self.config.personality,
            instructions=self.config.instructions,
            character=self.character,
            replier_available=context.replier_available,
        )
        payload = context.to_prompt()
        payload["planner_state"] = self.state.summary(
            affinity=context.affinity, interaction_count=context.interaction_count
        )
        data = self.client.chat_json(
            system,
            wrap_context(payload),
            max_tokens=720,
            temperature=min(self.config.temperature, 0.75),
        )
        plan = Plan.from_dict(data)
        valid_ids = {action.id for action in self.actions}
        plan.action_candidates = [
            action_id for action_id in plan.action_candidates if action_id in valid_ids
        ]
        if context.replier_available:
            if context.user_text.strip():
                plan.should_speak = True
        else:
            # The Replier cannot reach the user while the pet is hidden, so a
            # speech request would only produce an invisible bubble.
            plan.should_speak = False
        return plan

    def commit(self, plan: Plan, context: AIContext) -> None:
        """Record the turn after the orchestrator finished validating it."""
        self.state.observe(plan, trigger=context.trigger, user_text=context.user_text)
