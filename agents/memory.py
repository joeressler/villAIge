from __future__ import annotations

import uuid

from db.repository import Repository
from memory.embedding import EmbeddingProvider
from memory.vector_store import VectorStore
from models.schemas import MemoryEvent


class AgentMemory:
    def __init__(
        self,
        repo: Repository,
        embedding: EmbeddingProvider,
        vector_store: VectorStore,
    ):
        self.repo = repo
        self.embedding = embedding
        self.vector_store = vector_store

    def store(
        self,
        agent_id: str,
        tick: int,
        text: str,
        importance: float = 0.5,
        emotion: str = "neutral",
    ) -> MemoryEvent:
        memory = MemoryEvent(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            tick=tick,
            text=text,
            importance=importance,
            emotion=emotion,
        )
        blob = self.vector_store.insert(memory, text)
        self.repo.save_memory(memory, embedding=blob)
        return memory

    def recall(
        self,
        agent_id: str,
        query: str,
        current_tick: int,
        limit: int = 10,
    ) -> list[MemoryEvent]:
        results = self.vector_store.search(
            query, agent_id=agent_id, limit=limit, current_tick=current_tick
        )
        memories: list[MemoryEvent] = []
        for search_hit in results:
            try:
                memories.append(MemoryEvent.model_validate(search_hit))
            except Exception:
                memories.append(
                    MemoryEvent(
                        id=search_hit["id"],
                        agent_id=search_hit["agent_id"],
                        tick=search_hit["tick"],
                        text=search_hit["text"],
                        importance=search_hit["importance"],
                        emotion=search_hit["emotion"],
                    )
                )
        return memories

    def get_recent(self, agent_id: str, limit: int = 20) -> list[MemoryEvent]:
        return self.repo.get_memories_for_agent(agent_id, limit=limit)
