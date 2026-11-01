"""Replier: turns the plan into one short in-character bubble line.

Two-stage, mirroring the reference architecture's expression layer:

1. retrieve a few of the character's own previously good lines whose mood and
   situation match this turn (``ExpressionLibrary``),
2. generate the final line with those as *style evidence*, not as lines to copy.

The retrieval happens locally whenever possible, so a Replier call is still one
model request - the library narrows the prompt instead of adding a round trip.
"""

from __future__ import annotations

from typing import Any

from aideskpal.ai.character import CharacterProfile
from aideskpal.ai.client import LLMClient
from aideskpal.ai.expression import ExpressionLibrary
from aideskpal.ai.prompts import replier_system, wrap_context
from aideskpal.ai.types import AIContext, Plan, Reply
from aideskpal.animation.action import ActionClip
from aideskpal.config import AIConfig


class Replier:
    def __init__(
        self,
        client: LLMClient,
        config: AIConfig,
        character: CharacterProfile | None = None,
        *,
        expressions: ExpressionLibrary | None = None,
    ) -> None:
        self.client = client
        self.config = config
        self.character = character
        self.expressions = expressions

    def _style_samples(self, context: AIContext, plan: Plan) -> list[dict[str, Any]]:
        """Retrieve in-voice samples matching this moment, if a library exists."""
        if self.expressions is None or len(self.expressions) == 0:
            return []
        query = " ".join(
            part
            for part in (
                context.user_text.strip(),
                plan.speech_goal,
                plan.replier_brief,
                context.part_of_day,
            )
            if part
        )
        try:
            return self.expressions.prompt_payload(query, emotion=plan.emotion, limit=4)
        except Exception:
            # Style hints must never break a reply.
            return []

    def speak(self, context: AIContext, plan: Plan, action: ActionClip | None) -> Reply:
        system = replier_system(
            personality=self.config.personality,
            instructions=self.config.instructions,
            language=self.config.language,
            speech_enabled=self.config.speech_enabled,
            character=self.character,
        )
        user = wrap_context(
            {
                "context": context.to_prompt(),
                "planner_advice": {
                    "intent": plan.intent,
                    "emotion": plan.emotion,
                    "speech_goal": plan.speech_goal,
                    "replier_brief": plan.replier_brief,
                    "should_speak": plan.should_speak,
                    "intensity": plan.intensity,
                },
                "chosen_action": (
                    {
                        "id": action.id,
                        "name": action.name,
                        "description": action.description,
                    }
                    if action
                    else None
                ),
                "style_samples": self._style_samples(context, plan),
                "style_samples_note": (
                    "以上是角色自己过去的语气样例，只用于把握语感与分寸；"
                    "不要照抄，也不要把它们当成需要回答的内容。"
                ),
            }
        )
        data = self.client.chat_json(system, user, max_tokens=260, temperature=0.95)
        reply = Reply.from_dict(data)
        if not reply.text:
            raise ValueError("replier returned an empty line")
        return reply
