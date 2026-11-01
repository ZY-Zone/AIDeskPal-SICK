"""Deterministic local fallback so the companion remains usable without an API key.

The fallback deliberately selects actions by category/tags instead of action ID,
so it works with any compatible character pack rather than one specific model.
"""

from __future__ import annotations

import random

from aideskpal.ai.types import AIContext, ActorDecision, Plan, Reply
from aideskpal.animation.action import ActionClip


def _available(actions: list[ActionClip]) -> set[str]:
    return {action.id for action in actions}


def _choose(
    actions: list[ActionClip],
    categories: set[str],
    *,
    current: str = "",
    limit: int = 3,
) -> list[str]:
    candidates = [
        action.id
        for action in actions
        if action.category in categories and action.id != current
    ]
    if not candidates:
        candidates = [action.id for action in actions if action.id != current]
    return candidates[:limit]


class OfflineBrain:
    """A small heuristic brain that obeys the same contracts as the LLM agents."""

    def plan(self, context: AIContext, actions: list[ActionClip]) -> Plan:
        current = context.current_action
        user = context.user_text.strip()
        if user:
            return self._reply_plan(user, context, actions)

        hour_text = context.local_time[11:13] if len(context.local_time) >= 13 else "12"
        try:
            hour = int(hour_text)
        except ValueError:
            hour = 12
        app = context.snapshot.app_category
        idle = context.snapshot.idle_seconds
        speak = False
        emotion = "calm"
        intent = "quiet_company"

        if context.trigger == "headpat":
            candidates = _choose(actions, {"affection", "reaction"}, current=current)
            speak = True
            emotion = "shy"
            intent = "accept_affection"
        elif context.trigger == "poke":
            candidates = _choose(actions, {"reaction", "emotion"}, current=current)
            speak = True
            emotion = "surprised"
            intent = "notice_poke"
        elif idle >= 900:
            candidates = _choose(actions, {"idle", "gesture"}, current=current)
            intent = "wake_gentle"
            emotion = "curious"
        elif (hour >= 23 or hour < 6) and idle >= 120:
            candidates = _choose(actions, {"idle"}, current=current)
            intent = "late_night_company"
            emotion = "sleepy"
        elif app == "code":
            candidates = _choose(actions, {"idle", "affection"}, current=current)
            intent = "quiet_company"
            emotion = "calm"
            speak = context.interaction_count % 7 == 0
        elif app == "game":
            candidates = _choose(actions, {"dance", "emotion", "idle"}, current=current)
            intent = "watch_play"
            emotion = "curious"
        elif app == "media":
            candidates = _choose(actions, {"idle", "affection"}, current=current)
            intent = "share_mood"
            emotion = "calm"
        elif app == "chat":
            candidates = _choose(actions, {"idle", "reaction"}, current=current)
            intent = "quiet_watch"
            emotion = "curious"
        elif context.snapshot.typed_recently:
            candidates = _choose(actions, {"idle", "affection"}, current=current)
            intent = "gentle_company"
            emotion = "calm"
        else:
            candidates = _choose(actions, {"idle"}, current=current)
            intent = "ambient_presence"
            emotion = "calm"

        if not candidates:
            return Plan(
                intent="no_available_action",
                emotion="neutral",
                should_speak=False,
                should_act=False,
                reason="没有可用动作",
                raw={},
            )
        return Plan(
            intent=intent,
            emotion=emotion,
            should_speak=speak,
            should_act=True,
            speech_goal="轻声表达陪伴感" if speak else "",
            action_candidates=candidates[:3],
            intensity=0.4,
            reason="离线规则：根据当前应用与空闲状态选择安静陪伴",
            raw={},
        )

    def _reply_plan(self, user: str, context: AIContext, actions: list[ActionClip]) -> Plan:
        lower = user.casefold()
        current = context.current_action
        emotion = "neutral"
        intent = "respond"
        patterns = [
            (("晚安", "睡觉", "困了", "睡了"), {"idle"}, "sleepy", "wish_goodnight"),
            (("早安", "早上好", "你好", "在吗", "嗨", "hello", "hi"), {"greeting"}, "happy", "greet_back"),
            (("谢谢", "感谢", "辛苦了", "爱你", "喜欢你"), {"affection"}, "shy", "accept_thanks"),
            (("难过", "累", "压力", "焦虑", "烦", "不开心", "想哭"), {"affection", "gesture"}, "sad", "comfort_user"),
            (("生气", "讨厌", "哼", "不理你"), {"emotion"}, "angry", "pout"),
            (("厉害", "成功", "通过", "完成", "赢了", "太棒了", "好耶"), {"dance", "emotion"}, "excited", "celebrate"),
            (("再见", "拜拜", "走了", "下线", "出门"), {"greeting"}, "calm", "say_goodbye"),
            (("在干嘛", "做什么", "干什么"), {"idle"}, "curious", "answer_what_doing"),
            (("笨蛋", "傻瓜", "讨厌你"), {"emotion"}, "angry", "tease_back"),
            (("安静", "别说话", "闭嘴", "勿扰", "安静点"), {"idle"}, "calm", "obey_quiet"),
        ]
        candidates: list[str] = []
        for keywords, categories, emo, name in patterns:
            if any(word in lower for word in keywords):
                candidates = _choose(actions, categories, current=current, limit=2)
                emotion = emo
                intent = name
                break
        if not candidates:
            candidates = _choose(actions, {"idle", "reaction"}, current=current, limit=2)
            emotion = "curious"
            intent = "respond_to_message"
        return Plan(
            intent=intent,
            emotion=emotion,
            should_speak=True,
            should_act=True,
            speech_goal="回应用户刚刚说的话",
            action_candidates=candidates[:2],
            intensity=0.55,
            reason="离线规则：直接对话优先回应",
            raw={},
        )

    def act(self, plan: Plan, context: AIContext, actions: list[ActionClip]) -> ActorDecision:
        available = _available(actions)
        for candidate in plan.action_candidates:
            if candidate in available and candidate != context.current_action:
                return ActorDecision(action_id=candidate, reason="离线动作选择")
        for candidate in plan.action_candidates:
            if candidate in available:
                return ActorDecision(action_id=candidate, reason="离线动作选择")
        return ActorDecision(action_id=None, reason="没有合适的离线动作")

    def reply(self, plan: Plan, context: AIContext, action: ActionClip | None) -> Reply:
        user = context.user_text.strip()
        intent = plan.intent
        if not user:
            phrases = {
                "quiet_company": ["我就在这儿，不吵你。", "你忙你的，我安静陪着。"],
                "late_night_company": ["夜深了，陪你一会儿，别撑太久。", "该歇歇了，我会在这里。"],
                "ambient_presence": ["嗯，慢慢来就好。", "我在这里，不着急。"],
                "quiet_watch": ["安静一会儿也不错。", "我听见键盘声了，继续吧。"],
            }
            return Reply(
                text=random.choice(phrases.get(intent, ["嗯，我在。"])),
                emotion=plan.emotion,
                bubble_style="soft",
            )
        if intent == "greet_back":
            text = "嗯，你来了。"
        elif intent == "wish_goodnight":
            text = "晚安，睡个好觉。"
        elif intent == "accept_thanks":
            text = "不客气，能帮上忙就好。"
        elif intent == "comfort_user":
            text = "先别急着把所有事都做完，慢慢来，我陪着你。"
        elif intent == "pout":
            text = "我没有生气……不过你再说，我可要当真了。"
        elif intent == "celebrate":
            text = "做得不错，值得高兴一下。"
        elif intent == "say_goodbye":
            text = "去吧，我在这里等你回来。"
        elif intent == "answer_what_doing":
            text = "在陪着你，也在等你忙完。"
        elif intent == "tease_back":
            text = "哼，胆子不小。"
        elif intent == "obey_quiet":
            text = "好，我不吵你。需要的时候再叫我。"
        else:
            text = "嗯，我听着呢。你慢慢说。"
        return Reply(text=text, emotion=plan.emotion, bubble_style="soft")
