"""Long-term vector memory for interactions and user profile facts.

Storage is a small SQLite database.  Vectorisation itself lives in
``aideskpal.ai.embedding.EmbeddingService`` so the same vectors are shared with
expression selection and profile retrieval.  When no endpoint is usable the
service keeps a deterministic local hashing vector, so memory still works
offline instead of trying to download a model or leaking text unexpectedly.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from aideskpal.ai.embedding import (  # re-exported for backwards compatibility
    HASH_DIM,
    EmbeddingService,
    hash_embedding,
    normalize_vector,
)
from aideskpal.config import AIConfig, MemoryConfig

logger = logging.getLogger(__name__)

SENSITIVE_RE = re.compile(
    r"密码|password|passwd|api[\s_-]?key|secret|token|身份证|银行卡|信用卡|私钥",
    re.IGNORECASE,
)
_FACT_PATTERNS = (
    ("称呼", re.compile(r"(?:我叫|我的名字是|可以叫我)[：:\s]*([^\s，。,.!?！？]{1,20})")),
    ("身份", re.compile(r"我是(?:一名|一个|做|在)?([^，。！？!?\n]{2,40})")),
    ("喜欢", re.compile(r"我(?:很|最|比较)?喜欢([^，。！？!?\n]{1,40})")),
    ("不喜欢", re.compile(r"我(?:很|最|比较)?(?:讨厌|不喜欢)([^，。！？!?\n]{1,40})")),
    ("正在做", re.compile(r"我(?:正在|在做|在学|在开发)([^，。！？!?\n]{2,50})")),
)

__all__ = [
    "HASH_DIM",
    "LongTermMemory",
    "SENSITIVE_RE",
    "hash_embedding",
    "normalize_vector",
]


class LongTermMemory:
    def __init__(
        self,
        path: Path,
        memory: MemoryConfig,
        ai: AIConfig,
        *,
        embedder: EmbeddingService | None = None,
    ) -> None:
        self.path = Path(path)
        self.config = memory
        # A shared service may be injected so memory writes and expression
        # selection reuse one cache and one failure cooldown.
        self.embedder = embedder or EmbeddingService(memory, ai)
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # Retained for callers that poked the old private attribute.
    @property
    def _embedder(self) -> EmbeddingService:
        return self.embedder

    # ------------------------------------------------------------------ setup
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._lock, self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL DEFAULT 'episode',
                    text TEXT NOT NULL,
                    vector BLOB NOT NULL,
                    dim INTEGER NOT NULL,
                    fallback BLOB NOT NULL,
                    fallback_dim INTEGER NOT NULL,
                    model TEXT NOT NULL DEFAULT 'local-hash',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    importance REAL NOT NULL DEFAULT 0.5,
                    created_at REAL NOT NULL,
                    last_used REAL NOT NULL DEFAULT 0,
                    hits INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_memories_created
                    ON memories(created_at DESC);
                CREATE TABLE IF NOT EXISTS facts (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    hits INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def reconfigure(self, memory: MemoryConfig, ai: AIConfig) -> None:
        with self._lock:
            self.config = memory
            self._embedder.reconfigure(memory, ai)

    # ------------------------------------------------------------------ write
    def remember_summary(
        self,
        summary: str,
        *,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Store a Planner-curated durable summary, not a raw transcript.

        Only this curated text is sent to the configured embedding endpoint.
        Sensitive-looking summaries are rejected before any network request.
        """
        if not self.config.enabled:
            return False
        text = (summary or "").strip()
        if len(text) < 2 or SENSITIVE_RE.search(text):
            return False
        text = text[:1000]
        vector, fallback, model = self._embedder.embed_with_fallback(text)
        now = time.time()
        try:
            with self._lock, self._connect() as db:
                db.execute(
                    """INSERT INTO memories
                    (kind, text, vector, dim, fallback, fallback_dim, model,
                     metadata, importance, created_at)
                    VALUES ('planner', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        text,
                        vector.astype(np.float32).tobytes(),
                        int(vector.size),
                        fallback.astype(np.float32).tobytes(),
                        int(fallback.size),
                        model,
                        json.dumps(metadata or {}, ensure_ascii=False),
                        max(0.0, min(1.0, float(importance))),
                        now,
                    ),
                )
                self._prune(db)
            logger.info("Planner-curated long-term memory stored")
            return True
        except (sqlite3.Error, TypeError, ValueError):
            logger.exception("Could not store Planner memory summary")
            return False

    def remember_interaction(
        self,
        user_text: str,
        reply: str,
        *,
        action_id: str | None = None,
        app_category: str = "",
    ) -> bool:
        if not self.config.enabled:
            return False
        user_text = (user_text or "").strip()
        if len(user_text) < 2:
            return False
        if SENSITIVE_RE.search(user_text):
            logger.info("Long-term memory skipped a sensitive user message")
            return False
        text = f"用户：{user_text[:1000]}"
        if reply.strip():
            text += f"\n桌宠：{reply.strip()[:600]}"
        if action_id:
            text += f"\n动作：{action_id}"
        if app_category:
            text += f"\n场景：{app_category}"
        vector, fallback, model = self._embedder.embed_with_fallback(text)
        now = time.time()
        try:
            with self._lock, self._connect() as db:
                db.execute(
                    """INSERT INTO memories
                    (kind, text, vector, dim, fallback, fallback_dim, model,
                     metadata, importance, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "episode",
                        text,
                        vector.astype(np.float32).tobytes(),
                        int(vector.size),
                        fallback.astype(np.float32).tobytes(),
                        int(fallback.size),
                        model,
                        json.dumps(
                            {"action_id": action_id, "app_category": app_category},
                            ensure_ascii=False,
                        ),
                        0.55 if action_id else 0.45,
                        now,
                    ),
                )
                if self.config.profile_extraction:
                    for key, value in self._extract_facts(user_text):
                        db.execute(
                            """INSERT INTO facts(key, value, updated_at)
                            VALUES (?, ?, ?)
                            ON CONFLICT(key) DO UPDATE SET
                              value=excluded.value, updated_at=excluded.updated_at""",
                            (key, value, now),
                        )
                self._prune(db)
            logger.debug("Long-term memory stored: %s", text[:80])
            return True
        except sqlite3.Error:
            logger.exception("Could not store long-term memory")
            return False

    @staticmethod
    def _extract_facts(text: str) -> list[tuple[str, str]]:
        if SENSITIVE_RE.search(text):
            return []
        facts: list[tuple[str, str]] = []
        for key, pattern in _FACT_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            value = match.group(1).strip(" ：:，,。.!！?？")
            if 1 <= len(value) <= 80:
                facts.append((key, value))
        return facts

    def _prune(self, db: sqlite3.Connection) -> None:
        limit = max(100, min(20000, int(self.config.max_records)))
        count = int(db.execute("SELECT COUNT(*) FROM memories").fetchone()[0])
        if count <= limit:
            return
        db.execute(
            """DELETE FROM memories WHERE id IN (
                SELECT id FROM memories
                ORDER BY (importance + hits * 0.03) ASC, created_at ASC
                LIMIT ?
            )""",
            (count - limit,),
        )

    def add_fact(self, key: str, value: str) -> None:
        key = key.strip()[:40]
        value = value.strip()[:200]
        if not key or not value or SENSITIVE_RE.search(value):
            return
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO facts(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  value=excluded.value, updated_at=excluded.updated_at""",
                (key, value, time.time()),
            )

    # ------------------------------------------------------------------ read
    def recall(self, query: str, limit: int | None = None) -> list[dict[str, Any]]:
        if not self.config.enabled:
            return []
        query = (query or "").strip()
        top = max(1, min(12, int(limit if limit is not None else self.config.top_k)))
        facts = self.facts()
        if not query:
            return facts[:top]
        remote, fallback, _ = self._embedder.embed_with_fallback(query)
        now = time.time()
        scored: list[tuple[float, sqlite3.Row, int]] = []
        try:
            with self._lock, self._connect() as db:
                rows = db.execute(
                    "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?",
                    (max(50, min(20000, int(self.config.max_records))),),
                ).fetchall()
                for row in rows:
                    dim = int(row["dim"])
                    if dim == int(remote.size):
                        vector = np.frombuffer(row["vector"], dtype=np.float32)
                        score = float(np.dot(remote, vector))
                    else:
                        vector = np.frombuffer(row["fallback"], dtype=np.float32)
                        if vector.size != fallback.size:
                            continue
                        score = float(np.dot(fallback, vector))
                    age_days = max(0.0, now - float(row["created_at"])) / 86400.0
                    score += 0.12 * math.exp(-age_days / 45.0)
                    score += 0.05 * min(1.0, float(row["importance"]))
                    if score >= 0.045:
                        scored.append((score, row, int(row["id"])))
                scored.sort(key=lambda item: item[0], reverse=True)
                selected = scored[:top]
                for _, _, memory_id in selected:
                    db.execute(
                        "UPDATE memories SET hits=hits+1, last_used=? WHERE id=?",
                        (now, memory_id),
                    )
        except sqlite3.Error:
            logger.exception("Could not recall long-term memory")
            return facts[:top]
        results: list[dict[str, Any]] = [
            {
                "kind": "profile",
                "key": fact["key"],
                "text": f"{fact['key']}：{fact['value']}",
            }
            for fact in facts[:6]
        ]
        for score, row, _ in selected:
            results.append(
                {
                    "kind": row["kind"],
                    "text": row["text"],
                    "score": round(score, 4),
                    "created_at": row["created_at"],
                }
            )
        return results[: top + 6]

    def facts(self) -> list[dict[str, Any]]:
        try:
            with self._lock, self._connect() as db:
                rows = db.execute(
                    "SELECT key, value, updated_at FROM facts ORDER BY updated_at DESC"
                ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error:
            logger.exception("Could not read memory facts")
            return []

    def profile_text(self) -> str:
        facts = self.facts()
        if not facts:
            return "还没有形成用户画像。多聊几次后，称呼、身份、喜好和当前项目会出现在这里。"
        return "\n".join(f"{item['key']}：{item['value']}" for item in facts)

    def stats(self) -> dict[str, Any]:
        try:
            with self._lock, self._connect() as db:
                count = int(db.execute("SELECT COUNT(*) FROM memories").fetchone()[0])
                facts = int(db.execute("SELECT COUNT(*) FROM facts").fetchone()[0])
                models = [
                    str(row[0])
                    for row in db.execute(
                        "SELECT model, COUNT(*) c FROM memories GROUP BY model ORDER BY c DESC"
                    ).fetchall()
                ]
            return {
                "count": count,
                "facts": facts,
                "models": models,
                "path": str(self.path),
            }
        except sqlite3.Error:
            return {"count": 0, "facts": 0, "models": [], "path": str(self.path)}

    def clear(self) -> None:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM memories")
            db.execute("DELETE FROM facts")
        logger.info("Long-term memory cleared")
