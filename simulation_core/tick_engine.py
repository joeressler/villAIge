from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from agents.agent import AgentRunner
from agents.decision_graph import DecisionGraph
from agents.memory import AgentMemory
from agents.relationships import RelationshipManager
from config import AppConfig
from db.repository import Repository
from memory.embedding import SentenceTransformerEmbedding
from memory.vector_store import VectorStore
from models.schemas import Action, WorldState
from observability.langfuse_tracer import LangfuseTracer
from simulation_core.action_resolver import ActionResolver
from simulation_core.economy import Economy
from simulation_core.elections import ElectionSystem
from simulation_core.events import EventGenerator
from llm.router import LLMRouter
from simulation_core.world import World

logger = logging.getLogger(__name__)


class TickEngine:
    def __init__(self, config: AppConfig):
        self.config = config
        self.repo = Repository(config.database.path)
        self.world = World(config, self.repo)
        self.economy = Economy(config)
        self.events = EventGenerator(self.repo)
        self.elections = ElectionSystem(config, self.repo)
        self.relationships = RelationshipManager(self.repo)
        self.embedding = SentenceTransformerEmbedding.get_instance(
            config.memory.embedding_model
        )
        self.vector_store = VectorStore(self.repo, self.embedding)
        self.memory = AgentMemory(self.repo, self.embedding, self.vector_store)
        self.tracer = LangfuseTracer(config.langfuse, self.repo)
        self.agent_runner = AgentRunner()
        self.decision_graph = DecisionGraph(
            repo=self.repo,
            memory=self.memory,
            relationships=self.relationships,
            llm_router=LLMRouter(config.llm),
            tracer=self.tracer,
            agent_runner=self.agent_runner,
            use_llm=False,
        )
        self.resolver = ActionResolver(
            self.repo, self.economy, self.relationships, self.memory
        )
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._listeners: list[Callable[[dict[str, Any]], None]] = []

    def add_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.append(callback)

    def _emit(self, event: dict[str, Any]) -> None:
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("Listener error")

    @property
    def state(self) -> WorldState:
        return self.world.state

    @property
    def agents(self) -> dict:
        return self.world.agents

    def initialize(self) -> WorldState:
        return self.world.initialize()

    async def start(self) -> None:
        if self._running:
            return
        self.initialize()
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        self._emit({"type": "simulation_started", "tick": self.state.tick})

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._emit({"type": "simulation_stopped", "tick": self.state.tick})

    async def step(self) -> dict[str, Any]:
        if not self.world.agents:
            self.initialize()
        result = await self._execute_tick()
        return result

    async def _run_loop(self) -> None:
        while self._running:
            await self._execute_tick()
            await asyncio.sleep(self.config.simulation.tick_duration_seconds)

    async def _execute_tick(self) -> dict[str, Any]:
        state = self.world.state
        state.tick += 1
        tick = state.tick

        world_events = self.events.generate(state)
        election_started = self.elections.maybe_start_election(state, self.world.agents)

        actions_taken: list[dict] = []
        for agent in list(self.world.agents.values()):
            try:
                action = self.decision_graph.run(agent, state)
                description = self.resolver.resolve(
                    tick, agent.id, action, self.world.agents, state
                )
                actions_taken.append(
                    {
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "action": action.model_dump(),
                        "description": description,
                    }
                )
            except Exception:
                logger.exception("Agent %s decision failed", agent.id)
                fallback = Action(type="talk", payload={"topic": "idle"})
                self.resolver.resolve(
                    tick, agent.id, fallback, self.world.agents, state
                )

        election_ended = self.elections.tick_election(state)
        if election_ended:
            winner_id, scores = self.elections.finalize_election(
                state, self.world.agents, self.relationships.get_trust
            )
            if winner_id and winner_id in self.world.agents:
                self.world.set_chief(winner_id)
                self.repo.save_world_event(
                    tick,
                    "election_won",
                    f"{self.world.agents[winner_id].name} became chief!",
                    {"winner": winner_id, "scores": scores},
                )
                self._emit({
                    "type": "election",
                    "tick": tick,
                    "winner": winner_id,
                    "winner_name": self.world.agents[winner_id].name,
                    "scores": scores,
                })

        state = self.economy.produce(self.world.agents, state)
        state = self.economy.consume(self.world.agents, state)
        self.relationships.decay_all()

        for agent in self.world.agents.values():
            self.repo.save_agent(agent)

        self.repo.save_world_state(state)
        self.repo.save_tick_snapshot(state)
        self.world.state = state

        result = {
            "tick": tick,
            "world_events": world_events,
            "actions": actions_taken,
            "chief": state.chief,
            "resources": state.resources.model_dump(),
            "election_active": state.election_state.active,
            "election_started": election_started,
        }
        self._emit({"type": "tick_update", **result})
        return result

    def set_use_llm(self, enabled: bool) -> None:
        self.decision_graph.use_llm = enabled

    def get_agent_detail(self, agent_id: str) -> Optional[dict]:
        agent = self.world.get_agent(agent_id)
        if not agent:
            return None
        return {
            "agent": agent.model_dump(),
            "relationships": [
                r.model_dump()
                for r in self.relationships.repo.get_relationships_for_agent(agent_id)
            ],
            "memories": [
                m.model_dump()
                for m in self.memory.get_recent(agent_id, limit=20)
            ],
            "traces": self.repo.get_llm_traces(agent_id),
        }

    def get_tick_detail(self, tick: int) -> Optional[dict]:
        snapshot = self.repo.get_tick_snapshot(tick)
        if not snapshot:
            return None
        return {
            "tick": tick,
            "state": snapshot.model_dump(),
            "actions": self.repo.get_actions_for_tick(tick),
            "events": self.repo.get_world_events(tick=tick),
        }
