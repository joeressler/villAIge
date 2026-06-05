from __future__ import annotations

import sqlite3
import struct
from typing import Optional

import numpy as np

from db.repository import Repository
from memory.embedding import EmbeddingProvider


def _blob_from_vector(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _vector_from_blob(blob: bytes) -> np.ndarray:
    count = len(blob) // 4
    return np.array(struct.unpack(f"{count}f", blob), dtype=np.float32)


class VectorStore:
    """SQLite-VSS wrapper with numpy cosine fallback."""

    def __init__(self, repo: Repository, embedding: EmbeddingProvider):
        self.repo = repo
        self.embedding = embedding
        self._vss_available = False
        self._init_vss()

    def _init_vss(self) -> None:
        try:
            self.repo.conn.enable_load_extension(True)
            for ext in ("sqlite-vss", "vss0", "/usr/local/lib/sqlite-vss"):
                try:
                    self.repo.conn.load_extension(ext)
                    self._vss_available = True
                    break
                except sqlite3.OperationalError:
                    continue
            if self._vss_available:
                dim = self.embedding.dimension
                self.repo.conn.execute(
                    f"""CREATE VIRTUAL TABLE IF NOT EXISTS memories_vss
                        USING vss0(embedding({dim}))"""
                )
                self.repo.conn.commit()
        except Exception:
            self._vss_available = False

    def insert(self, memory_id: str, text: str) -> bytes:
        vec = self.embedding.embed(text)
        blob = _blob_from_vector(vec)
        if self._vss_available:
            try:
                rowid = self._get_rowid(memory_id)
                if rowid is not None:
                    self.repo.conn.execute(
                        "DELETE FROM memories_vss WHERE rowid = ?", (rowid,)
                    )
                self.repo.conn.execute(
                    "INSERT INTO memories_vss(rowid, embedding) VALUES (?, ?)",
                    (self._memory_rowid(memory_id), blob),
                )
                self.repo.conn.commit()
            except sqlite3.Error:
                pass
        return blob

    def _memory_rowid(self, memory_id: str) -> int:
        row = self.repo.conn.execute(
            "SELECT rowid FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return row[0] if row else abs(hash(memory_id)) % (10**9)

    def _get_rowid(self, memory_id: str) -> Optional[int]:
        row = self.repo.conn.execute(
            "SELECT rowid FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return row[0] if row else None

    def search(
        self,
        query: str,
        agent_id: Optional[str] = None,
        limit: int = 10,
        current_tick: int = 0,
    ) -> list[dict]:
        query_vec = np.array(self.embedding.embed(query), dtype=np.float32)

        if self._vss_available:
            results = self._vss_search(query_vec, agent_id, limit * 3)
            if results:
                return self._rerank(results, current_tick, limit)

        return self._fallback_search(query_vec, agent_id, current_tick, limit)

    def _vss_search(
        self, query_vec: np.ndarray, agent_id: Optional[str], limit: int
    ) -> list[dict]:
        try:
            blob = _blob_from_vector(query_vec.tolist())
            rows = self.repo.conn.execute(
                """SELECT m.id, m.agent_id, m.tick, m.text, m.importance, m.emotion,
                          v.distance
                   FROM memories_vss v
                   JOIN memories m ON m.rowid = v.rowid
                   WHERE vss_search(v.embedding, vss_search_params(?, 20))
                   ORDER BY distance
                   LIMIT ?""",
                (blob, limit),
            ).fetchall()
            results = []
            for r in rows:
                if agent_id and r["agent_id"] != agent_id:
                    continue
                results.append(
                    {
                        "id": r["id"],
                        "agent_id": r["agent_id"],
                        "tick": r["tick"],
                        "text": r["text"],
                        "importance": r["importance"],
                        "emotion": r["emotion"],
                        "similarity": 1.0 - r["distance"],
                    }
                )
            return results
        except sqlite3.Error:
            return []

    def _fallback_search(
        self,
        query_vec: np.ndarray,
        agent_id: Optional[str],
        current_tick: int,
        limit: int,
    ) -> list[dict]:
        if agent_id:
            rows = self.repo.conn.execute(
                "SELECT id, agent_id, tick, text, importance, emotion, embedding FROM memories WHERE agent_id = ?",
                (agent_id,),
            ).fetchall()
        else:
            rows = self.repo.conn.execute(
                "SELECT id, agent_id, tick, text, importance, emotion, embedding FROM memories"
            ).fetchall()

        scored = []
        for r in rows:
            if r["embedding"] is None:
                continue
            vec = _vector_from_blob(r["embedding"])
            sim = float(np.dot(query_vec, vec) / (np.linalg.norm(vec) + 1e-8))
            scored.append(
                {
                    "id": r["id"],
                    "agent_id": r["agent_id"],
                    "tick": r["tick"],
                    "text": r["text"],
                    "importance": r["importance"],
                    "emotion": r["emotion"],
                    "similarity": sim,
                }
            )
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return self._rerank(scored[: limit * 3], current_tick, limit)

    def _rerank(self, results: list[dict], current_tick: int, limit: int) -> list[dict]:
        emotion_weights = {
            "fear": 1.2,
            "anger": 1.1,
            "joy": 0.9,
            "neutral": 1.0,
            "hope": 1.05,
        }
        for r in results:
            recency = 1.0 / (1.0 + max(0, current_tick - r["tick"]) * 0.05)
            emotion_w = emotion_weights.get(r.get("emotion", "neutral"), 1.0)
            r["score"] = (
                r.get("similarity", 0.5) * 0.5
                + r["importance"] * 0.3
                + recency * 0.15
                + emotion_w * 0.05
            )
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
