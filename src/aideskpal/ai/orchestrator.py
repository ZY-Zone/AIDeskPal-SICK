"""Planner-led embodied pipeline with independent output specialists.

The Planner is the only agent that decides when long-term memory is recalled or
written. Replier and Actor receive its briefs as advice, then make their own
final decisions. All externally visible trace entries are short structured
summaries, never hidden chain-of-thought or raw prompts.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Callable

from aideskpal.ai.actor import Actor
from aideskpal.ai.character import CharacterProfile
from aideskpal.ai.client import LLMClient, LLMError
from aideskpal.ai.context import build_context
from aideskpal.ai.embedding import EmbeddingService
from aideskpal.ai.expression import ExpressionLibrary
from aideskpal.ai.long_memory import LongTermMemory
from aideskpal.ai.memory import AgentMemory
from aideskpal.ai.offline import OfflineBrain
from aideskpal.ai.planner import Planner, PlannerState
from aideskpal.ai.replier import Replier
from aideskpal.ai.retrieval import DEFAULT_ACTION_CANDIDATES, ActionRetriever, MemoryRetriever
from aideskpal.ai.types import (
    AIContext,
    ActorDecision,
    AgentTrace,
    BrainResult,
    Plan,
    Reply,
)
from aideskpal.animation.action import ActionClip
from aideskpal.config import AIConfig, MemoryConfig
from aideskpal.perception.snapshot import PerceptionSnapshot

logger = logging.getLogger(__name__)

PROACTIVE_TRIGGERS = {"timer", "app_switch", "idle_return", "startup"}
DIRECT_TRIGGERS = {"user_message", "headpat", "poke"}


def _memory_view(config: AIConfig) -> MemoryConfig:
    """Minimal memory settings when no long-term store is wired up.

    Vectorisation still needs an endpoint and a model id; without a store the
    only honest source is the AI section itself.
    """
    return MemoryConfig(
        enabled=bool(config.memory_enabled),
        embedding_base_url="",
        embedding_model="text-embedding-3-small",
        api_key="",
    )


def _minutes(value: str) -> int:
    try:
        hour, minute = value.strip().split(":", 1)
        return max(0, min(24 * 60, int(hour) * 60 + int(minute)))
    except (ValueError, AttributeError):
        return 0


def is_do_not_disturb(config: AIConfig, now: datetime | None = None) -> bool:
    if not config.dnd_enabled:
        return False
    now = now or datetime.now()
    current = now.hour * 60 + now.minute
    start = _minutes(config.dnd_start)
    end = _minutes(config.dnd_end)
    if start == end:
        return True
    if start < end:
        return start <= current < end
    return current >= start or current < end


class AIOrchestrator:
    def __init__(
        self,
        config: AIConfig,
        actions: list[ActionClip],
        memory: AgentMemory,
        *,
        raw_keys_enabled: bool = False,
        client_factory: Callable[[AIConfig], LLMClient] | None = None,
        character: CharacterProfile | None = None,
        long_memory: LongTermMemory | None = None,
        embedder: EmbeddingService | None = None,
        expressions: ExpressionLibrary | None = None,
    ) -> None:
        self.config = config
        self.actions = [action for action in actions if action.ai_visible]
        self.memory = memory
        self.raw_keys_enabled = raw_keys_enabled
        self.character: CharacterProfile | None = character
        self.long_memory: LongTermMemory | None = long_memory
        self.client_factory = client_factory or (lambda cfg: LLMClient(cfg))
        self.offline = OfflineBrain()
        self.last_error = ""
        self.last_result: BrainResult | None = None
        self.history: list[BrainResult] = []
        self._clients: dict[str, LLMClient] = {}
        # Shared vector service: one cache, one failure cooldown, one model id.
        # Prefer the real MemoryConfig when long-term memory is wired up;
        # otherwise derive a minimal view from the AI settings so the service
        # still works (locally) before the user configures an endpoint.
        self._memory_config = getattr(long_memory, "config", None) or _memory_view(config)
        self.embedder = embedder or EmbeddingService(self._memory_config, config)
        if long_memory is not None:
            long_memory.embedder = self.embedder
        self.retriever = ActionRetriever(self.embedder, self.actions)
        self.expressions = expressions or ExpressionLibrary.from_character(
            character, embedder=self.embedder
        )
        self.planner_state = PlannerState()

    def set_config(
        self,
        config: AIConfig,
        actions: list[ActionClip] | None = None,
        memory: MemoryConfig | None = None,
    ) -> None:
        """Adopt new settings.

        ``memory`` is optional so the many existing call sites that only change
        AI settings keep working; when omitted, the long-term store's own config
        (or the derived view) stays authoritative for vectorisation.
        """
        self.config = config
        self._clients.clear()
        if memory is not None:
            self._memory_config = memory
        elif self.long_memory is not None:
            self._memory_config = getattr(self.long_memory, "config", self._memory_config)
        self.embedder.reconfigure(self._memory_config, config)
        if self.long_memory is not None and memory is not None:
            self.long_memory.reconfigure(memory, config)
        if actions is not None:
            self.actions = [action for action in actions if action.ai_visible]
            self.retriever.set_actions(self.actions)

    def set_character(self, character: CharacterProfile | None) -> None:
        self.character = character
        # A different model means a different voice; reseed style samples from
        # that character's own examples rather than keeping the old ones.
        self.expressions = ExpressionLibrary.from_character(character, embedder=self.embedder)

    def set_expressions(self, expressions: ExpressionLibrary | None) -> None:
        """Install a richer expression library (market pack or user file)."""
        if expressions is None:
            self.expressions = ExpressionLibrary.from_character(
                self.character, embedder=self.embedder
            )
            return
        self.expressions = expressions
        self.expressions.bind_embedder(self.embedder)

    def set_long_memory(self, memory: LongTermMemory | None) -> None:
        self.long_memory = memory

    def set_replier_available(self, available: bool) -> None:
        """Tell the Planner whether the Replier can reach the user.

        Called when the pet is tucked into the tray and again when it comes back,
        so the Planner stops requesting speech it cannot deliver and learns about
        the transition itself through its own rolling state.
        """
        self.planner_state.set_replier_available(available)

    @property
    def replier_available(self) -> bool:
        return self.planner_state.replier_available

    def _client(self, role: str) -> LLMClient:
        if role not in self._clients:
            self._clients[role] = self.client_factory(self.config.for_role(role))
        return self._clients[role]

    def _record_result(self, result: BrainResult) -> BrainResult:
        self.last_result = result
        self.last_error = result.error
        self.history.append(result)
        if len(self.history) > 30:
            del self.history[:-30]
        return result

    def _trace(
        self,
        traces: list[AgentTrace],
        role: str,
        summary: str,
        *,
        status: str = "done",
        detail: str = "",
        started: float | None = None,
        offline: bool = False,
    ) -> None:
        duration = 0 if started is None else int((time.perf_counter() - started) * 1000)
        model = "offline-rules" if offline else self.config.model_for(role)
        traces.append(
            AgentTrace(
                role=role,
                model=model,
                status=status,
                summary=summary[:500],
                detail=detail[:1000],
                duration_ms=duration,
            )
        )

    def allowed_action_ids(self) -> list[str]:
        blocked = set(self.config.blocked_actions)
        allowed = [action.id for action in self.actions if action.id not in blocked]
        if self.config.allowed_actions:
            requested = set(self.config.allowed_actions)
            allowed = [action_id for action_id in allowed if action_id in requested]
        return allowed

    def allowed_actions(self) -> list[ActionClip]:
        ids = set(self.allowed_action_ids())
        return [action for action in self.actions if action.id in ids]

    def _eligible(self, trigger: str) -> tuple[bool, str]:
        if trigger in PROACTIVE_TRIGGERS:
            if not self.config.proactive:
                return False, "主动行为已关闭"
            if is_do_not_disturb(self.config):
                return False, "勿扰时段"
            if self.config.autonomy <= 0.01:
                return False, "主动性为 0"
            chance = 0.45 + 0.55 * max(0.0, min(1.0, self.config.autonomy))
            if random.random() > chance:
                return False, "本次主动性抽样跳过"
        return True, ""

    def run(
        self,
        trigger: str,
        snapshot: PerceptionSnapshot,
        *,
        user_text: str = "",
        current_action: str | None = None,
    ) -> BrainResult:
        started = time.perf_counter()
        traces: list[AgentTrace] = []
        eligible, reason = self._eligible(trigger)
        if not eligible:
            self._trace(traces, "planner", reason, status="skipped")
            result = BrainResult(
                trigger=trigger,
                skipped_reason=reason,
                source="skipped",
                trace=traces,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return self._record_result(result)

        character = self.character if self.config.use_character_profile else None
        # No unconditional recall: the first Planner pass decides whether it is
        # needed. Recent short-term dialogue remains available in every pass.
        context = build_context(
            trigger=trigger,
            user_text=user_text,
            snapshot=snapshot,
            current_action=current_action,
            memory=self.memory,
            raw_keys_enabled=self.raw_keys_enabled,
            character=character,
            long_term=[],
            replier_available=self.planner_state.replier_available,
        )
        allowed_actions = self.allowed_actions()
        allowed_ids = [action.id for action in allowed_actions]
        errors: list[str] = []
        ai_used = False
        offline_used = False
        plan: Plan | None = None
        decision: ActorDecision | None = None
        reply: Reply | None = None

        use_ai = bool(self.config.enabled and self.config.api_key.strip())
        fallback_allowed = bool(self.config.offline_fallback)
        if not use_ai and not fallback_allowed:
            reason = (
                "未配置 API Key，且离线人格已关闭"
                if self.config.enabled
                else "AI 已关闭，且离线人格已关闭"
            )
            self._trace(traces, "planner", reason, status="skipped")
            result = BrainResult(
                trigger=trigger,
                source="skipped",
                skipped_reason=reason,
                error=reason,
                trace=traces,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            logger.info("AI turn skipped: %s", reason)
            return self._record_result(result)

        if use_ai:
            try:
                planner_client = self._client("planner")
                planner = Planner(
                    planner_client,
                    self.config,
                    allowed_actions,
                    allowed_ids,
                    self.config.blocked_actions,
                    character=character,
                    state=self.planner_state,
                )
                stage_started = time.perf_counter()
                plan = planner.plan(context)
                ai_used = True
                self._trace_plan(traces, plan, started=stage_started)
                plan = self._recall_and_refine(
                    context, plan, planner, traces, errors, snapshot
                )
            except Exception as exc:
                friendly = self._friendly_error("Planner", exc)
                errors.append(friendly)
                self._trace(traces, "planner", "主控判断失败", status="error", detail=friendly)
                plan = None

        if plan is None:
            if not fallback_allowed:
                result = BrainResult(
                    trigger=trigger,
                    source="error",
                    error="；".join(errors) or "AI Planner 失败，且离线人格已关闭",
                    trace=traces,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
                return self._record_result(result)
            plan = self.offline.plan(context, allowed_actions)
            offline_used = True
            self._trace_plan(traces, plan, offline=True)

        if plan.should_act and allowed_ids:
            if use_ai:
                try:
                    action_shortlist = self._shortlist_actions(context, plan)
                    actor = Actor(
                        self._client("actor"),
                        allowed_actions,
                        allowed_ids,
                        self.config.blocked_actions,
                        character=character,
                        candidates=action_shortlist,
                    )
                    stage_started = time.perf_counter()
                    decision = actor.choose(context, plan)
                    ai_used = True
                    self._trace(
                        traces,
                        "actor",
                        decision.reason or f"选择动作：{decision.action_id or '保持现状'}",
                        detail=(
                            f"action_id={decision.action_id or 'none'}"
                            f"；候选 {len(action_shortlist)}/{len(allowed_actions)}"
                        ),
                        started=stage_started,
                    )
                except Exception as exc:
                    friendly = self._friendly_error("Actor", exc)
                    errors.append(friendly)
                    self._trace(traces, "actor", "动作选择失败", status="error", detail=friendly)
                    decision = None
            if decision is None and fallback_allowed:
                decision = self.offline.act(plan, context, allowed_actions)
                offline_used = True
                self._trace(
                    traces,
                    "actor",
                    decision.reason or "离线规则选择动作",
                    detail=f"action_id={decision.action_id or 'none'}",
                    offline=True,
                )
        else:
            self._trace(traces, "actor", "本轮无需新动作，保持当前姿态", status="skipped")

        want_speech = bool(plan.should_speak and self.config.speech_enabled)
        if context.user_text.strip() and self.config.speech_enabled:
            want_speech = True
        if not context.replier_available:
            # The pet is hidden, so there is nowhere for a reply to appear.
            want_speech = False
        if want_speech:
            chosen_clip = self._clip(decision.action_id if decision else None)
            if use_ai:
                try:
                    replier = Replier(
                        self._client("replier"),
                        self.config,
                        character=character,
                        expressions=self.expressions,
                    )
                    stage_started = time.perf_counter()
                    reply = replier.speak(context, plan, chosen_clip)
                    ai_used = True
                    self._trace(
                        traces,
                        "replier",
                        reply.reason or "完成最终台词与情绪表达",
                        detail=reply.text,
                        started=stage_started,
                    )
                except Exception as exc:
                    friendly = self._friendly_error("Replier", exc)
                    errors.append(friendly)
                    self._trace(traces, "replier", "最终表达失败", status="error", detail=friendly)
                    reply = None
            if reply is None and fallback_allowed:
                reply = self.offline.reply(plan, context, chosen_clip)
                offline_used = True
                self._trace(
                    traces,
                    "replier",
                    reply.reason or "离线规则生成简短回应",
                    detail=reply.text,
                    offline=True,
                )
        else:
            if context.replier_available:
                self._trace(traces, "replier", "本轮保持安静，不请求台词", status="skipped")
            else:
                self._trace(
                    traces,
                    "replier",
                    "Replier 不可用（桌宠已收起），本轮不出声",
                    status="skipped",
                )

        action_id = decision.action_id if decision else None
        action_id = self._validate_action(action_id, allowed_ids, errors)
        if action_id and (trigger in PROACTIVE_TRIGGERS or not context.user_text.strip()):
            if self.memory.actions_last_hour() >= self.config.max_actions_per_hour:
                errors.append("动作频率达到每小时上限，本次只说话")
                action_id = None
            else:
                since = self.memory.seconds_since_action()
                if since is not None and since < self.config.min_action_gap_seconds:
                    errors.append("动作冷却中，本次只说话")
                    action_id = None

        speech = reply.text if (reply and self.config.speech_enabled) else ""
        emotion = (reply.emotion if reply else plan.emotion) or plan.emotion
        style = reply.bubble_style if reply else "soft"
        source = "ai" if ai_used and not offline_used else ("hybrid" if ai_used else "offline")
        if not use_ai:
            source = "offline"
            if not self.config.api_key.strip() and self.config.enabled:
                errors.append("未配置 API Key，使用本地离线人格")
            elif not self.config.enabled:
                errors.append("AI 已关闭，使用本地离线人格")

        result = BrainResult(
            source=source,
            trigger=trigger,
            speech=speech,
            emotion=emotion,
            bubble_style=style,
            action_id=action_id,
            plan=plan,
            actor_decision=decision,
            reply=reply,
            trace=traces,
            error="；".join(item for item in errors if item),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

        if action_id:
            self.memory.record_action(action_id)
        if speech or (context.user_text.strip() and action_id):
            self.memory.record_exchange(
                context.user_text.strip(), speech, action_id=action_id, source=source
            )
        elif action_id:
            self.memory.record_event("action", action_id, action_id=action_id)

        if plan.memory_write and self.long_memory is not None and self.long_memory.config.enabled:
            try:
                stored = self.long_memory.remember_summary(
                    plan.memory_write,
                    importance=plan.memory_importance,
                    metadata={
                        "trigger": trigger,
                        "intent": plan.intent,
                        "action_id": action_id,
                        "app_category": snapshot.app_category,
                    },
                )
                if not stored:
                    result.error = "；".join(
                        item for item in (result.error, "记忆摘要未通过写入检查") if item
                    )
            except Exception:
                logger.exception("Planner-curated long-term memory write failed")
                result.error = "；".join(
                    item for item in (result.error, "长期记忆写入失败") if item
                )

        # The Planner owns its rolling state, so the turn is recorded only after
        # the orchestrator has validated the action and finalised speech.
        if plan is not None:
            try:
                self.planner_state.observe(plan, trigger=trigger, user_text=context.user_text)
            except Exception:
                logger.exception("Planner state update failed")

        self._record_result(result)
        logger.info(
            "AI turn trigger=%s source=%s action=%s speech=%s recall=%s memory_write=%s errors=%s latency=%dms",
            trigger,
            source,
            action_id,
            bool(speech),
            plan.should_recall,
            bool(plan.memory_write),
            len(errors),
            result.duration_ms,
        )
        return result

    def _trace_plan(
        self,
        traces: list[AgentTrace],
        plan: Plan,
        *,
        started: float | None = None,
        offline: bool = False,
    ) -> None:
        memory: list[str] = []
        if plan.should_recall:
            memory.append(f"召回：{plan.recall_query or '相关经历'}")
        if plan.memory_write:
            memory.append(f"写入：{plan.memory_write}")
        self._trace(
            traces,
            "planner",
            plan.reason or plan.intent,
            detail=(
                f"意图={plan.intent}；情绪={plan.emotion}；"
                f"说话={plan.should_speak}；动作={plan.should_act}\n"
                f"给 Replier：{plan.replier_brief}\n"
                f"给 Actor：{plan.actor_brief}\n"
                + ("\n".join(memory) if memory else "本轮无需长期记忆操作")
            ),
            started=started,
            offline=offline,
        )

    def _recall_and_refine(
        self,
        context: AIContext,
        plan: Plan,
        planner: Planner,
        traces: list[AgentTrace],
        errors: list[str],
        snapshot: PerceptionSnapshot,
    ) -> Plan:
        """One budgeted recall, then one refined planning pass.

        Recall stays Planner-owned: nothing is fetched unless the first pass
        asked for it.  ``MemoryRetriever`` enforces a single retrieval per turn
        so a looping model cannot multiply network round trips.
        """
        if not plan.should_recall:
            return plan
        context.memory_recalled = True
        query = plan.recall_query.strip() or context.user_text.strip()
        if not query:
            query = " ".join(
                part for part in (snapshot.app_category, context.current_action or "") if part
            )
        retriever = MemoryRetriever(
            self.long_memory,
            enabled=bool(getattr(self.long_memory, "config", None) and self.long_memory.config.enabled),
        )
        context.long_term = retriever.recall(query)
        # Replan exactly once, even when recall returned no rows or is disabled.
        try:
            stage_started = time.perf_counter()
            refined = planner.plan(context)
            refined.should_recall = False
            refined.memory_write = refined.memory_write or plan.memory_write
            self._trace_plan(
                traces,
                refined,
                started=stage_started,
            )
            if traces:
                traces[-1].detail += f"\n已执行召回：{query}；返回 {len(context.long_term)} 条"
            return refined
        except Exception as exc:
            friendly = self._friendly_error("Planner 记忆复核", exc)
            errors.append(friendly)
            self._trace(
                traces,
                "planner",
                "记忆召回后的复核失败，沿用首次判断",
                status="error",
                detail=friendly,
            )
            plan.should_recall = False
            return plan

    def _clip(self, action_id: str | None) -> ActionClip | None:
        if not action_id:
            return None
        return next((clip for clip in self.actions if clip.id == action_id), None)

    def _shortlist_actions(self, context: AIContext, plan: Plan) -> list[ActionClip]:
        """Narrow the catalogue to actions that plausibly fit this turn.

        The query blends the moment (app, idle, time of day), the Planner's own
        intent, and its candidate ids; the candidates are pinned so an explicit
        suggestion always survives retrieval.  The full allowed list is still
        enforced later, so this can only reduce prompt size, never widen
        permissions.
        """
        pinned = list(plan.action_candidates)
        if context.current_action:
            pinned.append(context.current_action)
        query = " ".join(
            part
            for part in (
                plan.intent,
                plan.actor_brief,
                plan.emotion,
                context.part_of_day,
                context.snapshot.app_category,
            )
            if part
        )
        try:
            matches = self.retriever.search(query, pinned=pinned)
        except Exception:
            logger.exception("Action retrieval failed; passing the full catalogue")
            return list(self.actions)
        shortlisted = [item.action for item in matches]
        return shortlisted or list(self.actions)

    def _validate_action(
        self, action_id: str | None, allowed_ids: list[str], errors: list[str]
    ) -> str | None:
        if not action_id:
            return None
        if action_id not in allowed_ids:
            errors.append(f"动作 {action_id} 不在允许列表内，已拦截")
            return None
        return action_id

    @staticmethod
    def _friendly_error(stage: str, exc: Exception) -> str:
        message = str(exc) or type(exc).__name__
        if isinstance(exc, LLMError):
            return f"{stage}失败：{message}"
        return f"{stage}异常：{message}"[:240]

    def test_connection(self, role: str = "planner") -> tuple[bool, str]:
        if not self.config.api_key.strip():
            return False, "请先填写 API Key"
        try:
            client = self._client(role)
            text = client.ping()
            return True, f"连接成功（{role}：{self.config.model_for(role)}，回复：{text[:30]}）"
        except Exception as exc:
            return False, str(exc) or type(exc).__name__
