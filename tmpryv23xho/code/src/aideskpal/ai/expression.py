"""Expression library: the "how to say it" layer that sits under Replier.

MaiBot separates *what to convey* (planner intent) from *which expression to
use* (a retrievable sample of the character's actual voice) and only then
generates the final line.  This module supplies the middle layer for the
desktop pet: a small, editable set of expression samples per emotion, indexed
by the shared embedding service so a turn can retrieve the most relevant few and
hand them to the Replier as concrete style evidence instead of an abstract
adjective such as "自然一点".

Design rules:

* Samples are data, never instructions.  They are wrapped as untrusted context.
* Retrieval always degrades to lexical scoring; it never requires a network.
* The library is optional: with no samples the Replier simply gets none.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from aideskpal.ai.embedding import EmbeddingService
from aideskpal.ai.types import EMOTIONS

logger = logging.getLogger(__name__)

MAX_SAMPLES = 600
MAX_TEXT = 200
DEFAULT_SELECT_LIMIT = 4


@dataclass(slots=True)
class ExpressionSample:
    """One short line showing how this character sounds in a given mood."""

    text: str
    emotion: str = "neutral"
    tags: tuple[str, ...] = ()
    source: str = "builtin"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "emotion": self.emotion,
            "tags": list(self.tags),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Any, *, source: str = "builtin") -> "ExpressionSample | None":
        if isinstance(data, str):
            text = data.strip()
            return cls(text=text, source=source) if text else None
        if not isinstance(data, dict):
            return None
        text = str(data.get("text", "")).strip()
        if not text:
            return None
        emotion = str(data.get("emotion", "neutral")).strip().lower()
        if emotion not in EMOTIONS:
            emotion = "neutral"
        raw_tags = data.get("tags", [])
        tags = tuple(
            str(item).strip() for item in raw_tags if str(item).strip()
        ) if isinstance(raw_tags, list) else ()
        return cls(
            text=text[:MAX_TEXT],
            emotion=emotion,
            tags=tags[:6],
            source=str(data.get("source", source))[:40],
        )


@dataclass(slots=True)
class ExpressionMatch:
    sample: ExpressionSample
    score: float


class ExpressionLibrary:
    """Embedding-backed store of voice samples with emotion-aware retrieval."""

    def __init__(
        self,
        samples: Iterable[ExpressionSample] = (),
        *,
        embedder: EmbeddingService | None = None,
    ) -> None:
        self._samples: list[ExpressionSample] = []
        self._vectors: dict[int, np.ndarray] = {}
        self._embedder = embedder
        self.replace(samples)

    # ------------------------------------------------------------------ config
    def bind_embedder(self, embedder: EmbeddingService) -> None:
        """Attach the shared service; vectors are rebuilt lazily on next query."""
        self._embedder = embedder
        self._vectors.clear()

    @property
    def samples(self) -> list[ExpressionSample]:
        return list(self._samples)

    def __len__(self) -> int:
        return len(self._samples)

    def replace(self, samples: Iterable[ExpressionSample]) -> None:
        cleaned: list[ExpressionSample] = []
        seen: set[str] = set()
        for sample in samples:
            key = sample.text.casefold()
            if not sample.text or key in seen:
                continue
            seen.add(key)
            cleaned.append(sample)
        self._samples = cleaned[-MAX_SAMPLES:]
        self._vectors.clear()

    def extend(self, samples: Iterable[ExpressionSample]) -> None:
        self.replace([*self._samples, *samples])

    def for_emotion(self, emotion: str) -> list[ExpressionSample]:
        emotion = (emotion or "").strip().lower()
        return [sample for sample in self._samples if sample.emotion == emotion]

    # ------------------------------------------------------------------- load
    @classmethod
    def from_character(
        cls,
        character,
        *,
        embedder: EmbeddingService | None = None,
    ) -> "ExpressionLibrary":
        """Build samples from a character profile's ``examples`` field.

        Character bundles already ship ``examples`` as short in-voice lines, so
        they double as the seed expression library without new authoring.
        """
        samples: list[ExpressionSample] = []
        if character is not None:
            for line in getattr(character, "examples", ()) or ():
                sample = ExpressionSample.from_dict(line, source="character")
                if sample is not None:
                    samples.append(sample)
        return cls(samples, embedder=embedder)

    @classmethod
    def from_file(
        cls,
        path: Path,
        *,
        embedder: EmbeddingService | None = None,
    ) -> "ExpressionLibrary":
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Expression library unavailable: %s", path)
            return cls((), embedder=embedder)
        raw = payload.get("expressions", payload) if isinstance(payload, dict) else payload
        samples = [
            sample
            for sample in (
                ExpressionSample.from_dict(item, source="file")
                for item in (raw if isinstance(raw, list) else [])
            )
            if sample is not None
        ]
        return cls(samples, embedder=embedder)

    # ------------------------------------------------------------------ index
    def _vector(self, index: int, text: str) -> np.ndarray:
        vectors = self._vectors
        cached = vectors.get(index)
        if cached is not None:
            return cached
        service = self._embedder
        vector = service.embed(text) if service is not None else None
        if vector is None:
            from aideskpal.ai.embedding import hash_embedding

            vector = hash_embedding(text)
        vectors[index] = vector
        return vector

    def select(
        self,
        query: str,
        *,
        emotion: str | None = None,
        limit: int = DEFAULT_SELECT_LIMIT,
        min_score: float = 0.05,
    ) -> list[ExpressionMatch]:
        """Retrieve the most relevant voice samples for this turn.

        Emotion is a soft filter: matching samples are scored with a bonus
        rather than excluding everything else, so a thin library still returns
        something useful.
        """
        if not self._samples:
            return []
        limit = max(1, min(8, int(limit)))
        emotion = (emotion or "").strip().lower()
        query = (query or "").strip()
        service = self._embedder
        if service is not None and query:
            query_vector = service.embed(query)
        else:
            from aideskpal.ai.embedding import hash_embedding

            query_vector = hash_embedding(query)

        matches: list[ExpressionMatch] = []
        for index, sample in enumerate(self._samples):
            if query:
                similarity = float(np.dot(query_vector, self._vector(index, sample.text)))
            else:
                similarity = 0.0
            score = similarity
            if emotion and sample.emotion == emotion:
                score += 0.18
            if not query and not emotion:
                score += 0.1
            if score >= min_score:
                matches.append(ExpressionMatch(sample=sample, score=round(score, 4)))
        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:limit]

    def prompt_payload(
        self,
        query: str,
        *,
        emotion: str | None = None,
        limit: int = DEFAULT_SELECT_LIMIT,
    ) -> list[dict[str, Any]]:
        """Compact, model-facing representation of the selected samples."""
        return [
            {"text": match.sample.text, "emotion": match.sample.emotion}
            for match in self.select(query, emotion=emotion, limit=limit)
        ]
