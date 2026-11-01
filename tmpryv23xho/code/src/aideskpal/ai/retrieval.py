"""Embedding-backed retrieval helpers shared by the agent pipeline.

Two indexes live here:

* :class:`ActionRetriever` narrows a large action catalogue to the handful that
  plausibly fit the current moment, so the Actor prompt carries relevant
  candidates instead of an undifferentiated dump.
* :class:`MemoryRetriever` is a thin, validated wrapper over long-term memory
  recall used by the Planner's second pass.

Both are pure local computation unless an embedding endpoint is configured; the
deterministic hashing vectors keep them useful offline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from aideskpal.ai.embedding import EmbeddingService, hash_embedding
from aideskpal.animation.action import ActionClip

logger = logging.getLogger(__name__)

DEFAULT_ACTION_CANDIDATES = 12


def action_fingerprint(action: ActionClip) -> str:
    """Text used to index one action: name, category, tags and description."""
    parts = [action.name, action.category, " ".join(action.tags), action.description]
    return " ".join(part for part in parts if part).strip()


@dataclass(slots=True)
class RetrievedAction:
    action: ActionClip
    score: float


class ActionRetriever:
    """Vector index over the action catalogue.

    The index is built lazily and invalidated when the catalogue object changes,
    because packs reload while the app stays running.
    """

    def __init__(
        self,
        embedder: EmbeddingService | None = None,
        actions: Iterable[ActionClip] = (),
    ) -> None:
        self._embedder = embedder
        self._actions: list[ActionClip] = list(actions)
        self._vectors: list[np.ndarray] = []
        self._lock_key: tuple[str, ...] = ()

    # ------------------------------------------------------------------ config
    def bind_embedder(self, embedder: EmbeddingService) -> None:
        self._embedder = embedder
        self._vectors = []

    def set_actions(self, actions: Iterable[ActionClip]) -> None:
        actions = list(actions)
        key = tuple(action.id for action in actions)
        if key == self._lock_key and self._vectors:
            self._actions = actions
            return
        self._actions = actions
        self._lock_key = key
        self._vectors = []

    def _embed(self, text: str) -> np.ndarray:
        if self._embedder is not None:
            return self._embedder.embed(text)
        return hash_embedding(text)

    def _build(self) -> None:
        if self._vectors or not self._actions:
            return
        self._vectors = [self._embed(action_fingerprint(action)) for action in self._actions]

    # ------------------------------------------------------------------- query
    def search(
        self,
        query: str,
        *,
        limit: int = DEFAULT_ACTION_CANDIDATES,
        pinned: Iterable[str] = (),
    ) -> list[RetrievedAction]:
        """Rank actions against *query*, always keeping *pinned* ids available.

        ``pinned`` is used for the Planner's own candidate list so an explicit
        suggestion never disappears because of embedding noise.
        """
        limit = max(1, min(len(self._actions) or 1, int(limit)))
        pinned_set = {str(item) for item in pinned if item}
        if not self._actions:
            return []
        self._build()
        query = (query or "").strip()
        results: list[RetrievedAction] = []
        if query and self._vectors:
            query_vector = self._embed(query)
            for action, vector in zip(self._actions, self._vectors):
                results.append(
                    RetrievedAction(action=action, score=round(float(np.dot(query_vector, vector)), 4))
                )
            results.sort(key=lambda item: item.score, reverse=True)
        else:
            results = [RetrievedAction(action=action, score=0.0) for action in self._actions]

        selected = [item for item in results if item.action.id in pinned_set]
        for item in results:
            if len(selected) >= limit:
                break
            if item.action.id not in pinned_set:
                selected.append(item)
        return selected[:limit]


class MemoryRetriever:
    """Guard-railed access to long-term recall for one planning pass.

    The Planner remains the only component that decides *when* to recall; this
    wrapper only enforces the per-turn budget so a looping model cannot turn one
    turn into several network round trips.
    """

    def __init__(self, memory: Any, *, enabled: bool = True) -> None:
        self.memory = memory
        self.enabled = enabled
        self._used = False

    @property
    def used(self) -> bool:
        return self._used

    def recall(self, query: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        if self._used or not self.enabled or self.memory is None:
            return []
        config = getattr(self.memory, "config", None)
        if config is not None and not getattr(config, "enabled", True):
            return []
        self._used = True
        try:
            if limit is None:
                return list(self.memory.recall(query))
            return list(self.memory.recall(query, limit))
        except TypeError:
            # A probe or an older memory implementation may only accept the query.
            return list(self.memory.recall(query))
        except Exception:
            logger.exception("Long-term recall failed")
            return []
