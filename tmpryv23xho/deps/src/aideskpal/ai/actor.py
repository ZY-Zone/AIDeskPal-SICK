"""Actor: picks exactly one designed action, or none.

The Actor no longer receives the whole catalogue on every turn.  The orchestrator
passes a retrieval-narrowed candidate set (built from the moment's context plus
the Planner's own suggestions), which keeps the prompt small and the choice
grounded in actions that actually fit the situation.
"""

from __future__ import annotations

from aideskpal.ai.character import CharacterProfile
from aideskpal.ai.client import LLMClient
from aideskpal.ai.prompts import actor_system, wrap_context
from aideskpal.ai.types import ActorDecision, AIContext, Plan
from aideskpal.animation.action import ActionClip


class Actor:
    def __init__(
        self,
        client: LLMClient,
        actions: list[ActionClip],
        allowed: list[str],
        blocked: list[str],
        character: CharacterProfile | None = None,
        *,
        candidates: list[ActionClip] | None = None,
    ) -> None:
        self.client = client
        # ``actions`` stays the full permissible set for validation; the prompt
        # only shows the narrowed ``candidates``.
        self.actions = actions
        self.allowed = allowed
        self.blocked = blocked
        self.character = character
        self.candidates = candidates if candidates is not None else actions

    def choose(self, context: AIContext, plan: Plan) -> ActorDecision:
        system = actor_system(
            actions=self.candidates,
            allowed=self.allowed,
            blocked=self.blocked,
            character=self.character,
        )
        user = wrap_context(
            {
                "context": context.to_prompt(),
                "planner_advice": {
                    "intent": plan.intent,
                    "emotion": plan.emotion,
                    "should_act": plan.should_act,
                    "actor_brief": plan.actor_brief,
                    "action_candidates": plan.action_candidates,
                    "intensity": plan.intensity,
                },
                "candidates_note": (
                    "candidates were pre-filtered for this moment; the full "
                    "allowed id list above is still authoritative"
                ),
            }
        )
        data = self.client.chat_json(system, user, max_tokens=180, temperature=0.65)
        return ActorDecision.from_dict(data)
