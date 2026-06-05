from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Optional

from models.schemas import (
    Action,
    Agent,
    AgentGoals,
    AgentPersonality,
    AgentStats,
    MemoryEvent,
    Relationship,
    WorldState,
)


class Repository:
    def __init__(self, db_path: str = "data/village.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def initialize(self) -> None:
        schema_path = Path(__file__).parent / "schema.sql"
        with schema_path.open() as f:
            self.conn.executescript(f.read())
        self.conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Agents ---

    def save_agent(self, agent: Agent) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO agents
               (id, name, role, wealth, reputation, influence,
                greed, sociability, aggression, honesty,
                primary_goal, secondary_goals)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent.id,
                agent.name,
                agent.role,
                agent.stats.wealth,
                agent.stats.reputation,
                agent.stats.influence,
                agent.personality.greed,
                agent.personality.sociability,
                agent.personality.aggression,
                agent.personality.honesty,
                agent.goals.primary,
                json.dumps(agent.goals.secondary),
            ),
        )
        self.conn.commit()

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        row = self.conn.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        return self._row_to_agent(row) if row else None

    def get_all_agents(self) -> list[Agent]:
        rows = self.conn.execute("SELECT * FROM agents").fetchall()
        return [self._row_to_agent(r) for r in rows]

    def _row_to_agent(self, row: sqlite3.Row) -> Agent:
        return Agent(
            id=row["id"],
            name=row["name"],
            role=row["role"],
            stats=AgentStats(
                wealth=row["wealth"],
                reputation=row["reputation"],
                influence=row["influence"],
            ),
            personality=AgentPersonality(
                greed=row["greed"],
                sociability=row["sociability"],
                aggression=row["aggression"],
                honesty=row["honesty"],
            ),
            goals=AgentGoals(
                primary=row["primary_goal"],
                secondary=json.loads(row["secondary_goals"]),
            ),
        )

    # --- Memories ---

    def save_memory(self, memory: MemoryEvent, embedding: Optional[bytes] = None) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO memories
               (id, agent_id, tick, text, importance, emotion, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                memory.id,
                memory.agent_id,
                memory.tick,
                memory.text,
                memory.importance,
                memory.emotion,
                embedding,
            ),
        )
        self.conn.commit()

    def get_memories_for_agent(self, agent_id: str, limit: int = 50) -> list[MemoryEvent]:
        rows = self.conn.execute(
            """SELECT id, agent_id, tick, text, importance, emotion
               FROM memories WHERE agent_id = ?
               ORDER BY tick DESC LIMIT ?""",
            (agent_id, limit),
        ).fetchall()
        return [
            MemoryEvent(
                id=r["id"],
                agent_id=r["agent_id"],
                tick=r["tick"],
                text=r["text"],
                importance=r["importance"],
                emotion=r["emotion"],
            )
            for r in rows
        ]

    def get_memory_by_id(self, memory_id: str) -> Optional[MemoryEvent]:
        row = self.conn.execute(
            "SELECT id, agent_id, tick, text, importance, emotion FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        if not row:
            return None
        return MemoryEvent(
            id=row["id"],
            agent_id=row["agent_id"],
            tick=row["tick"],
            text=row["text"],
            importance=row["importance"],
            emotion=row["emotion"],
        )

    def get_all_memory_embeddings(self) -> list[tuple[str, bytes]]:
        rows = self.conn.execute(
            "SELECT id, embedding FROM memories WHERE embedding IS NOT NULL"
        ).fetchall()
        return [(r["id"], r["embedding"]) for r in rows]

    # --- Relationships ---

    def save_relationship(self, rel: Relationship) -> None:
        a_id, b_id = sorted([rel.a_id, rel.b_id])
        self.conn.execute(
            """INSERT OR REPLACE INTO relationships
               (a_id, b_id, trust, respect, fear, friendship)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (a_id, b_id, rel.trust, rel.respect, rel.fear, rel.friendship),
        )
        self.conn.commit()

    def get_relationship(self, a_id: str, b_id: str) -> Optional[Relationship]:
        x, y = sorted([a_id, b_id])
        row = self.conn.execute(
            "SELECT * FROM relationships WHERE a_id = ? AND b_id = ?",
            (x, y),
        ).fetchone()
        if not row:
            return None
        return Relationship(
            a_id=row["a_id"],
            b_id=row["b_id"],
            trust=row["trust"],
            respect=row["respect"],
            fear=row["fear"],
            friendship=row["friendship"],
        )

    def get_relationships_for_agent(self, agent_id: str) -> list[Relationship]:
        rows = self.conn.execute(
            """SELECT * FROM relationships
               WHERE a_id = ? OR b_id = ?""",
            (agent_id, agent_id),
        ).fetchall()
        return [
            Relationship(
                a_id=r["a_id"],
                b_id=r["b_id"],
                trust=r["trust"],
                respect=r["respect"],
                fear=r["fear"],
                friendship=r["friendship"],
            )
            for r in rows
        ]

    def get_all_relationships(self) -> list[Relationship]:
        rows = self.conn.execute("SELECT * FROM relationships").fetchall()
        return [
            Relationship(
                a_id=r["a_id"],
                b_id=r["b_id"],
                trust=r["trust"],
                respect=r["respect"],
                fear=r["fear"],
                friendship=r["friendship"],
            )
            for r in rows
        ]

    # --- Actions ---

    def save_action(self, tick: int, agent_id: str, action: Action) -> int:
        cursor = self.conn.execute(
            """INSERT INTO actions (tick, agent_id, type, target, payload)
               VALUES (?, ?, ?, ?, ?)""",
            (tick, agent_id, action.type, action.target, json.dumps(action.payload)),
        )
        self.conn.commit()
        return cursor.lastrowid or 0

    def get_actions_for_tick(self, tick: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM actions WHERE tick = ? ORDER BY id",
            (tick,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "tick": r["tick"],
                "agent_id": r["agent_id"],
                "type": r["type"],
                "target": r["target"],
                "payload": json.loads(r["payload"]),
            }
            for r in rows
        ]

    # --- World State ---

    def save_world_state(self, state: WorldState) -> None:
        blob = state.model_dump_json()
        self.conn.execute(
            """INSERT OR REPLACE INTO world_state (id, tick, json_blob)
               VALUES (1, ?, ?)""",
            (state.tick, blob),
        )
        self.conn.commit()

    def get_world_state(self) -> Optional[WorldState]:
        row = self.conn.execute("SELECT json_blob FROM world_state WHERE id = 1").fetchone()
        if not row:
            return None
        return WorldState.model_validate_json(row["json_blob"])

    def save_tick_snapshot(self, state: WorldState) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO tick_snapshots (tick, json_blob) VALUES (?, ?)",
            (state.tick, state.model_dump_json()),
        )
        self.conn.commit()

    def get_tick_snapshot(self, tick: int) -> Optional[WorldState]:
        row = self.conn.execute(
            "SELECT json_blob FROM tick_snapshots WHERE tick = ?", (tick,)
        ).fetchone()
        if not row:
            return None
        return WorldState.model_validate_json(row["json_blob"])

    # --- World Events ---

    def save_world_event(
        self, tick: int, event_type: str, description: str, payload: dict | None = None
    ) -> None:
        self.conn.execute(
            """INSERT INTO world_events (tick, event_type, description, payload)
               VALUES (?, ?, ?, ?)""",
            (tick, event_type, description, json.dumps(payload or {})),
        )
        self.conn.commit()

    def get_world_events(self, tick: Optional[int] = None, limit: int = 100) -> list[dict]:
        if tick is not None:
            rows = self.conn.execute(
                """SELECT * FROM world_events WHERE tick = ?
                   ORDER BY id DESC LIMIT ?""",
                (tick, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM world_events ORDER BY tick DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "tick": r["tick"],
                "event_type": r["event_type"],
                "description": r["description"],
                "payload": json.loads(r["payload"]),
            }
            for r in rows
        ]

    # --- LLM Traces ---

    def save_llm_trace(
        self,
        agent_id: str,
        tick: int,
        prompt: str,
        response: str,
        latency_ms: float = 0.0,
        token_usage: int = 0,
        action_type: str = "",
    ) -> str:
        trace_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO llm_traces
               (id, agent_id, tick, prompt, response, latency_ms, token_usage, action_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (trace_id, agent_id, tick, prompt, response, latency_ms, token_usage, action_type),
        )
        self.conn.commit()
        return trace_id

    def get_llm_traces(self, agent_id: str, tick: Optional[int] = None) -> list[dict]:
        if tick is not None:
            rows = self.conn.execute(
                "SELECT * FROM llm_traces WHERE agent_id = ? AND tick = ?",
                (agent_id, tick),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM llm_traces WHERE agent_id = ? ORDER BY tick DESC",
                (agent_id,),
            ).fetchall()
        return [dict(r) for r in rows]
