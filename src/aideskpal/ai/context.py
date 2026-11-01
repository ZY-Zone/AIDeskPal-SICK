"""Build a compact, privacy-filtered context object for the three agents."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from aideskpal.ai.character import CharacterProfile
from aideskpal.ai.memory import AgentMemory
from aideskpal.ai.types import AIContext
from aideskpal.perception.snapshot import PerceptionSnapshot


def part_of_day(hour: int) -> str:
    if hour < 5:
        return "late_night"
    if hour < 9:
        return "early_morning"
    if hour < 12:
        return "morning"
    if hour < 14:
        return "noon"
    if hour < 18:
        return "afternoon"
    if hour < 22:
        return "evening"
    return "late_night"


def build_context(
    *,
    trigger: str,
    user_text: str,
    snapshot: PerceptionSnapshot,
    current_action: str | None,
    memory: AgentMemory,
    raw_keys_enabled: bool = False,
    character: CharacterProfile | None = None,
    long_term: list[dict[str, Any]] | None = None,
    replier_available: bool = True,
) -> AIContext:
    now = datetime.now()
    conversations = memory.recent_conversations(6)
    recent_memory = [
        {
            "role": item.get("role"),
            "text": str(item.get("text", ""))[:240],
        }
        for item in conversations
    ]
    return AIContext(
        trigger=trigger,
        user_text=user_text[:1000],
        snapshot=snapshot,
        current_action=current_action,
        recent_actions=memory.recent_actions(6),
        recent_memory=recent_memory,
        interaction_count=memory.interaction_count,
        affinity=memory.affinity,
        local_time=now.strftime("%Y-%m-%d %H:%M"),
        part_of_day=part_of_day(now.hour),
        session_minutes=snapshot.session_minutes,
        raw_keys_enabled=raw_keys_enabled,
        character=character,
        long_term=long_term or [],
        replier_available=replier_available,
    )
