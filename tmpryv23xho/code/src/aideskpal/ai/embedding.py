"""One embedding service shared by memory, expression selection and retrieval.

The previous design buried vectorisation inside long-term memory, so nothing else
could reuse it and every consumer had its own idea of when it was safe to call a
remote endpoint.  This module is the single place that owns:

* the local deterministic hashing vector (always available, no network),
* the optional OpenAI-compatible ``/embeddings`` endpoint,
* failure cooldown and a small result cache.

Vectors are always L2-normalised, so cosine similarity is a plain dot product.
``embed`` never raises and never blocks on a dead endpoint for long: callers
either get a remote vector or the local fallback.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time

import numpy as np

logger = logging.getLogger(__name__)

HASH_DIM = 384
CACHE_LIMIT = 512
COOLDOWN_SECONDS = 300.0

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+")


def normalize_vector(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-9:
        return np.zeros(HASH_DIM, dtype=np.float32)
    return (vector / norm).astype(np.float32)


# Historical private name, still used by the memory module's internals.
_normalize = normalize_vector


def hash_embedding(text: str, dim: int = HASH_DIM) -> np.ndarray:
    """Stable local feature hashing for Chinese/English short text.

    Unigrams plus bigrams give short Chinese phrases enough overlap to be useful
    for lexical retrieval without downloading a model.
    """
    vector = np.zeros(dim, dtype=np.float32)
    tokens = _TOKEN_RE.findall((text or "").lower())
    features: list[str] = []
    features.extend(tokens)
    features.extend(tokens[i] + tokens[i + 1] for i in range(len(tokens) - 1))
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "little")
        index = value % dim
        sign = 1.0 if (value >> 63) & 1 else -1.0
        vector[index] += sign
    return _normalize(vector)


class EmbeddingService:
    """Remote-first, local-always vectoriser shared by every AI sub-system."""

    def __init__(self, memory, ai) -> None:
        self.memory = memory
        self.ai = ai
        self._cooldown_until = 0.0
        self._failed = False
        self._cache: dict[str, np.ndarray] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ config
    def reconfigure(self, memory, ai) -> None:
        with self._lock:
            # The endpoint settings changed, so cached vectors of unknown origin
            # are no longer trustworthy.
            if memory.embedding_model != self.memory.embedding_model:
                self._cache.clear()
            self.memory = memory
            self.ai = ai
            self._cooldown_until = 0.0
            self._failed = False

    # Kept because long-term memory used to call ``update`` on its private
    # embedder; both names now mean the same thing.
    update = reconfigure

    @property
    def model(self) -> str:
        return str(getattr(self.memory, "embedding_model", "")).strip() or "text-embedding-3-small"

    @property
    def remote_available(self) -> bool:
        return bool(getattr(self.memory, "enabled", False)) and time.monotonic() >= self._cooldown_until

    # ------------------------------------------------------------------ remote
    def _endpoint(self) -> tuple[str, str]:
        base = (
            str(getattr(self.memory, "embedding_base_url", "") or "")
            or str(getattr(self.ai, "base_url", "") or "")
        ).strip().rstrip("/")
        if not base:
            return "", ""
        url = base if base.endswith("/embeddings") else base + "/embeddings"
        key = (
            str(getattr(self.memory, "api_key", "") or "")
            or str(getattr(self.ai, "api_key", "") or "")
        ).strip()
        return url, key

    def _remote(self, text: str) -> np.ndarray | None:
        if not getattr(self.memory, "enabled", False):
            return None
        if time.monotonic() < self._cooldown_until:
            return None
        url, key = self._endpoint()
        if not url:
            return None
        if not key and not any(host in url for host in ("127.0.0.1", "localhost", "::1")):
            return None
        # The DeepSeek chat API does not expose an embeddings endpoint.  Unless a
        # dedicated URL was supplied, skip the guaranteed timeout.
        if not getattr(self.memory, "embedding_base_url", "") and "deepseek" in url.lower():
            return None
        try:
            import httpx

            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            with httpx.Client(timeout=httpx.Timeout(4.0, connect=2.5)) as client:
                response = client.post(
                    url, headers=headers, json={"model": self.model, "input": text}
                )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("data")
            if not isinstance(items, list) or not items:
                raise ValueError("embedding response has no data")
            vector = _normalize(np.asarray(items[0]["embedding"], dtype=np.float32))
            if vector.size < 8:
                raise ValueError("embedding dimension too small")
            return vector
        except Exception as exc:  # noqa: BLE001 - any failure falls back locally
            self._cooldown_until = time.monotonic() + COOLDOWN_SECONDS
            if not self._failed:
                logger.warning("Embedding endpoint unavailable, using local vectors: %s", exc)
                self._failed = True
            return None

    # ------------------------------------------------------------------- public
    def local(self, text: str) -> np.ndarray:
        """Deterministic offline vector; used for indexes that must stay free."""
        return hash_embedding(text)

    def embed(self, text: str) -> np.ndarray:
        """Best available vector: cached remote result, else local hashing."""
        text = (text or "").strip()
        if not text:
            return np.zeros(HASH_DIM, dtype=np.float32)
        with self._lock:
            cached = self._cache.get(text)
        if cached is not None:
            return cached
        vector = self._remote(text)
        if vector is None:
            vector = self.local(text)
        with self._lock:
            if len(self._cache) >= CACHE_LIMIT:
                self._cache.clear()
            self._cache[text] = vector
        return vector

    def embed_with_fallback(self, text: str) -> tuple[np.ndarray, np.ndarray, str]:
        """Return ``(vector, fallback, model)``.

        Long-term memory stores both so a database written with a remote model
        keeps working after the endpoint disappears.
        """
        fallback = self.local(text)
        vector = self._remote(text)
        if vector is not None:
            return vector, fallback, self.model
        return fallback, fallback, "local-hash"

    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        a = np.asarray(a, dtype=np.float32).reshape(-1)
        b = np.asarray(b, dtype=np.float32).reshape(-1)
        if a.size == 0 or a.size != b.size:
            return 0.0
        return float(np.dot(a, b))
