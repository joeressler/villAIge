from __future__ import annotations

import logging
import struct
from typing import Any, Optional

import chromadb
from chromadb.api import ClientAPI
from chromadb.config import Settings

from config import MemoryConfig
from db.repository import Repository
from exceptions import VectorStoreError
from memory.embedding import EmbeddingProvider
from models.schemas import MemoryEvent

logger = logging.getLogger(__name__)


def _blob_from_vector(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


class VectorStore:
    """ChromaDB-backed semantic memory search."""

    def __init__(
        self,
        repo: Repository,
        embedding: EmbeddingProvider,
        config: MemoryConfig,
        chroma_client: ClientAPI | None = None,
    ):
        self.repo = repo
        self.embedding = embedding
        self._collection_name = config.chroma_collection
        self._expected_dim = config.embedding_dim
        if chroma_client is not None:
            self._client = chroma_client
        else:
            try:
                self._client = chromadb.HttpClient(
                    host=config.chroma_host,
                    port=config.chroma_port,
                    settings=Settings(anonymized_telemetry=False),
                )
                self._client.heartbeat()
            except Exception as e:
                logger.exception(
                    "Failed to connect to ChromaDB host=%s port=%s",
                    config.chroma_host,
                    config.chroma_port,
                )
                raise VectorStoreError(
                    "Could not connect to ChromaDB at "
                    f"{config.chroma_host}:{config.chroma_port}: {e}"
                ) from e
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        try:
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
            )
        except Exception as e:
            logger.exception("Failed to initialize Chroma collection")
            raise VectorStoreError(
                f"Failed to initialize Chroma collection {self._collection_name!r}: {e}"
            ) from e

    def clear(self) -> None:
        try:
            self._client.delete_collection(self._collection_name)
        except Exception:
            pass
        self._ensure_collection()

    def _stored_embedding_dim(self) -> int | None:
        if self._collection.count() == 0:
            return None
        result = self._collection.get(limit=1, include=["embeddings"])
        embeddings = result.get("embeddings")
        if embeddings is None or len(embeddings) == 0:
            return None
        first = embeddings[0]
        if first is None or len(first) == 0:
            return None
        return len(first)

    def _is_dimension_mismatch_error(self, error: Exception) -> bool:
        return "dimension" in str(error).lower()

    def _recreate_on_dimension_mismatch(self, reason: str) -> None:
        logger.warning(
            "Chroma collection %r incompatible with embedding_dim=%s (%s); "
            "recreating collection — run simulation Reset to re-index SQLite memories",
            self._collection_name,
            self._expected_dim,
            reason,
        )
        self.clear()

    def ensure_compatible_dimension(self) -> None:
        stored_dim = self._stored_embedding_dim()
        if stored_dim is not None and stored_dim != self._expected_dim:
            self._recreate_on_dimension_mismatch(
                f"stored vectors are {stored_dim}-dimensional"
            )
            return
        if self._collection.count() == 0:
            return
        try:
            probe = self.embedding.embed("dimension probe")
            self._collection.query(query_embeddings=[probe], n_results=1)
        except Exception as e:
            if self._is_dimension_mismatch_error(e):
                self._recreate_on_dimension_mismatch(str(e))
                return
            raise VectorStoreError(f"Chroma dimension probe failed: {e}") from e

    def insert(self, memory: MemoryEvent, text: str) -> bytes:
        vec = self.embedding.embed(text)
        blob = _blob_from_vector(vec)
        try:
            self._collection.upsert(
                ids=[memory.id],
                embeddings=[vec],
                documents=[text],
                metadatas=[
                    {
                        "agent_id": memory.agent_id,
                        "tick": int(memory.tick),
                        "importance": float(memory.importance),
                        "emotion": memory.emotion,
                    }
                ],
            )
        except Exception as e:
            if self._is_dimension_mismatch_error(e):
                self._recreate_on_dimension_mismatch(str(e))
                return self.insert(memory, text)
            logger.exception("Chroma upsert failed memory_id=%s", memory.id)
            raise VectorStoreError(
                f"Chroma insert failed for memory {memory.id!r}: {e}"
            ) from e
        return blob

    def search(
        self,
        query: str,
        agent_id: Optional[str] = None,
        limit: int = 10,
        current_tick: int = 0,
    ) -> list[dict]:
        if limit <= 0:
            return []
        if self._collection.count() == 0:
            return []

        query_vec = self.embedding.embed(query)
        where: Optional[dict[str, Any]] = (
            {"agent_id": agent_id} if agent_id else None
        )
        n_results = min(limit * 3, self._collection.count())
        try:
            response = self._collection.query(
                query_embeddings=[query_vec],
                n_results=n_results,
                where=where,
                include=["metadatas", "distances", "documents"],
            )
        except Exception as e:
            if self._is_dimension_mismatch_error(e):
                self._recreate_on_dimension_mismatch(str(e))
                return []
            logger.exception("Chroma search failed agent_id=%s", agent_id)
            raise VectorStoreError(f"Chroma search failed: {e}") from e

        results: list[dict] = []
        ids = response.get("ids", [[]])[0]
        distances = response.get("distances", [[]])[0]
        metadatas = response.get("metadatas", [[]])[0]
        documents = response.get("documents", [[]])[0]
        for memory_id, distance, meta, document in zip(
            ids, distances, metadatas, documents
        ):
            if meta:
                results.append(
                    {
                        "id": memory_id,
                        "agent_id": meta["agent_id"],
                        "tick": int(meta["tick"]),
                        "text": document or "",
                        "importance": float(meta["importance"]),
                        "emotion": meta["emotion"],
                        "similarity": max(0.0, 1.0 - float(distance)),
                    }
                )
                continue
            row = self.repo.get_memory_by_id(memory_id)
            if not row:
                continue
            results.append(
                {
                    "id": row.id,
                    "agent_id": row.agent_id,
                    "tick": row.tick,
                    "text": row.text,
                    "importance": row.importance,
                    "emotion": row.emotion,
                    "similarity": max(0.0, 1.0 - float(distance)),
                }
            )
        return self._rerank(results, current_tick, limit)

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
