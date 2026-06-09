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
from llm.embedding_router import EmbeddingRouter
from memory.vector_store import VectorStore
from models.schemas import Action, WorldState
from observability.langfuse_tracer import LangfuseTracer
from simulation_core.action_resolver import ActionResolver
from simulation_core.economy import Economy
from simulation_core.elections import ElectionSystem
from simulation_core.events import EventGenerator
from llm.router import LLMRouter
from simulation_core.threat import ThreatEngine
from simulation_core.world import World
from observability.feed import feed
from observability.tick_profiler import configure_profiler, get_profiler

logger = logging.getLogger(__name__)


class TickEngine:
    def __init__(self, config: AppConfig):
        self.config = config
        self.repo = Repository(config.database.path)
        self.world = World(config, self.repo)
        self.economy = Economy(config)
        self.events = EventGenerator(config, self.repo)
        self.elections = ElectionSystem(config, self.repo)
        self.threat_engine = ThreatEngine(config)
        self.relationships = RelationshipManager(self.repo)
        self.embedding_router = EmbeddingRouter(config)
        self.embedding = self.embedding_router.get_provider()
        self.vector_store = VectorStore(self.repo, self.embedding, config.memory)
        self.memory = AgentMemory(self.repo, self.embedding, self.vector_store)
        self.tracer = LangfuseTracer(config.langfuse, self.repo)
        self.agent_runner = AgentRunner(aliases=config.llm.action_aliases)
        llm_router = LLMRouter(config.llm)
        self.decision_graph = DecisionGraph(
            repo=self.repo,
            memory=self.memory,
            relationships=self.relationships,
            llm_router=llm_router,
            tracer=self.tracer,
            agent_runner=self.agent_runner,
            config=config,
        )
        self.resolver = ActionResolver(
            self.repo, self.economy, self.relationships, self.memory, self.elections, self.tracer
        )
        self._validate_dependencies(llm_router)
        configure_profiler(config.simulation.profile_ticks)
        self.profiler = get_profiler()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._listeners: list[Callable[[dict[str, Any]], None]] = []

    def _validate_dependencies(self, llm_router: LLMRouter) -> None:
        logger.info("Validating embedding provider...")
        self.embedding_router.verify()
        logger.info("Validating vector store (ChromaDB)...")
        _ = self.embedding.dimension
        self.vector_store.ensure_compatible_dimension()
        logger.info("Probing LLM provider...")
        llm_router.generate("Reply with exactly: ok")

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

    async def reset(self) -> WorldState:
        await self.stop()
        state = self.world.reset()
        self.vector_store.clear()
        self.profiler.clear()
        self._emit({"type": "simulation_reset", "tick": state.tick})
        return state

    async def step(self) -> dict[str, Any]:
        if not self.world.agents:
            self.initialize()
        result = await self._execute_tick()
        return result

    async def _run_loop(self) -> None:
        try:
            while self._running:
                await self._execute_tick()
                await asyncio.sleep(self.config.simulation.tick_duration_seconds)
        except Exception as e:
            self._running = False
            logger.exception("Simulation tick failed")
            feed.record_error(
                source="simulation",
                error_type=type(e).__name__,
                message=str(e),
                tick=self.state.tick,
            )
            self._emit({
                "type": "simulation_error",
                "tick": self.state.tick,
                "error_type": type(e).__name__,
                "message": str(e),
            })
            raise

    async def _execute_tick(self) -> dict[str, Any]:
        state = self.world.state
        state.tick += 1
        tick = state.tick

        with self.tracer.trace_tick(tick, state.population):
            result = await self._run_tick_body(state, tick)
        self.tracer.flush()
        return result

    async def _run_tick_body(self, state: WorldState, tick: int) -> dict[str, Any]:
        self.profiler.begin_tick(tick, population=state.population)

        with self.profiler.phase("events"):
            world_events = self.events.generate(state, self.world.agents)
            election_started = self.elections.maybe_start_election(
                state, self.world.agents
            )

        agents_this_tick = list(self.world.agents.values())
        total_agents = len(agents_this_tick)
        self._emit({
            "type": "tick_started",
            "tick": tick,
            "total_agents": total_agents,
            "world_events": world_events,
        })

        actions_taken: list[dict] = []
        with self.profiler.phase("agent_loop"):
            for index, agent in enumerate(agents_this_tick, start=1):
                if not self._running:
                    break
                self._emit({
                    "type": "agent_deciding",
                    "tick": tick,
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "index": index,
                    "total": total_agents,
                })
                with self.profiler.agent_phase(agent.id, "agent_total"):
                    with self.profiler.agent_phase(agent.id, "decision"):
                        action = await asyncio.to_thread(
                            self.decision_graph.run, agent, state
                        )
                    with self.profiler.agent_phase(agent.id, "resolve"):
                        description = self.resolver.resolve(
                            tick, agent.id, action, self.world.agents, state
                        )
                entry = self._action_log_entry(
                    tick, agent.id, agent.name, action, description
                )
                actions_taken.append(entry)
                self._emit({
                    "type": "action_taken",
                    "tick": tick,
                    "action": entry,
                    "index": index,
                    "total": total_agents,
                })

        with self.profiler.phase("election"):
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

        with self.profiler.phase("economy"):
            state = self.economy.produce(self.world.agents, state)
            state = self.economy.consume(self.world.agents, state)
            state.threat = self.threat_engine.compute_threat(
                state, self.world.agents, self.economy.food_demand(self.world.agents)
            )
            self.threat_engine.apply_threat_effects(state, self.world.agents)
            self.economy.apply_rep_decay(self.world.agents)
            self.relationships.decay_all()

        with self.profiler.phase("persist"):
            for agent in self.world.agents.values():
                self.repo.save_agent(agent)
            self.repo.save_world_state(state)
            self.repo.save_tick_snapshot(state)
        self.world.state = state

        ballot_tally = self.elections.ballot_tally(state)
        candidate_names = {
            cid: self.world.agents[cid].name
            for cid in state.election_state.candidates
            if cid in self.world.agents
        }
        profile = self.profiler.end_tick()
        result = {
            "tick": tick,
            "world_events": world_events,
            "actions": actions_taken,
            "profile": profile,
            "chief": state.chief,
            "resources": state.resources.model_dump(),
            "threat": state.threat.model_dump(),
            "election_active": state.election_state.active,
            "election_started": election_started,
            "election_candidates": state.election_state.candidates,
            "election_candidate_names": candidate_names,
            "election_ballot_tally": ballot_tally,
        }
        self._emit({"type": "tick_update", **result})
        return result

    def _action_log_entry(
        self,
        tick: int,
        agent_id: str,
        agent_name: str,
        action: Action,
        description: str,
    ) -> dict[str, Any]:
        return {
            "tick": tick,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "type": action.type,
            "category": action.category,
            "action": action.model_dump(),
            "description": description,
        }

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
