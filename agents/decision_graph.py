from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

logger = logging.getLogger(__name__)

from langgraph.graph import END, StateGraph

from agents.agent import AgentRunner
from agents.memory import AgentMemory
from agents.relationships import RelationshipManager
from config import AppConfig
from db.repository import Repository
from exceptions import InvalidActionError, LLMParseError
from llm.router import LLMRouter
from models.schemas import Action, Agent, WorldState
from observability.langfuse_tracer import LangfuseTracer
from observability.tick_profiler import get_profiler


class AgentState(TypedDict):
    agent: Agent
    world: WorldState
    relationships: list[dict]
    structured_memories: list[dict]
    semantic_memories: list[dict]
    context_summary: str
    llm_response: str
    thinking: str
    action: dict
    prompt: str


class DecisionGraph:
    ACTION_SCHEMA = """Respond with ONLY valid JSON:
{"type": "<trade|talk|campaign|vote|gift|steal|build|persuade>",
 "target": "<agent_id>",
 "payload": {}}
Every action MUST target another villager by agent_id — never yourself, never null.
Valid types only — use "build" to construct with someone (not "craft" alone); use "trade" to exchange with someone (not solo "gather"/"hunt"/"resource").
Use agent_id from the other-villagers roster for target, not names."""

    REASONING_INSTRUCTION = (
        "Reason about the situation using the context above. "
        "Your final answer must be ONLY the JSON action object — no prose outside the JSON."
    )

    RETRY_INSTRUCTION = """CORRECTION REQUIRED (attempt {attempt} of {max_attempts}):
Your previous response was invalid: {error}
Respond with ONLY a single valid JSON object — no prose, markdown, or invented action names.
Valid types: trade, talk, campaign, vote, gift, steal, build, persuade.
Every action must target another villager's agent_id (not yourself, not null).
Previous response (truncated): {snippet}"""

    def __init__(
        self,
        repo: Repository,
        memory: AgentMemory,
        relationships: RelationshipManager,
        llm_router: LLMRouter,
        tracer: LangfuseTracer,
        agent_runner: AgentRunner,
        config: AppConfig,
    ):
        self.repo = repo
        self.memory = memory
        self.relationships = relationships
        self.llm_router = llm_router
        self.tracer = tracer
        self.agent_runner = agent_runner
        self.config = config
        self.graph = self._build_graph()

    def _build_graph(self):
        g = StateGraph(AgentState)
        g.add_node("observe", self._observe)
        g.add_node("fetch_relationships", self._fetch_relationships)
        g.add_node("fetch_structured_memory", self._fetch_structured_memory)
        g.add_node("fetch_semantic_memory", self._fetch_semantic_memory)
        g.add_node("synthesize_context", self._synthesize_context)
        g.add_node("llm_decision", self._llm_decision)
        g.add_node("validate_action", self._validate_action)

        g.set_entry_point("observe")
        g.add_edge("observe", "fetch_relationships")
        g.add_edge("fetch_relationships", "fetch_structured_memory")
        g.add_edge("fetch_structured_memory", "fetch_semantic_memory")
        g.add_edge("fetch_semantic_memory", "synthesize_context")
        g.add_edge("synthesize_context", "llm_decision")
        g.add_edge("llm_decision", "validate_action")
        g.add_edge("validate_action", END)
        return g.compile()

    def run(self, agent: Agent, world: WorldState) -> Action:
        initial: AgentState = {
            "agent": agent,
            "world": world,
            "relationships": [],
            "structured_memories": [],
            "semantic_memories": [],
            "context_summary": "",
            "llm_response": "",
            "thinking": "",
            "action": {},
            "prompt": "",
        }

        def invoke_graph(handler) -> dict:
            config: dict = {}
            if handler is not None:
                config["callbacks"] = [handler]
                config["metadata"] = {
                    "langfuse_session_id": f"tick-{world.tick}",
                    "langfuse_user_id": agent.id,
                    "langfuse_tags": ["village-sim", agent.role],
                }
            return self.graph.invoke(initial, config=config)

        result = self.tracer.run_agent_decision(agent, world, invoke_graph)
        action_data = result.get("action")
        if not action_data or not action_data.get("type"):
            raise InvalidActionError(
                f"Decision graph produced no valid action for agent {agent.id}"
            )
        return self.agent_runner.action_from_dict(action_data)

    def _observe(self, state: AgentState) -> dict:
        return {}

    def _fetch_relationships(self, state: AgentState) -> dict:
        agent = state["agent"]
        profiler = get_profiler()
        with profiler.agent_phase(agent.id, "relationships"):
            rels = self.relationships.repo.get_relationships_for_agent(agent.id)
        rel_dicts = []
        for r in rels:
            other = r.b_id if r.a_id == agent.id else r.a_id
            other_agent = self.repo.get_agent(other)
            rel_dicts.append(
                {
                    "other_id": other,
                    "other_name": other_agent.name if other_agent else other,
                    "trust": r.trust,
                    "respect": r.respect,
                    "fear": r.fear,
                    "friendship": r.friendship,
                }
            )
        return {"relationships": rel_dicts}

    def _fetch_structured_memory(self, state: AgentState) -> dict:
        agent = state["agent"]
        with get_profiler().agent_phase(agent.id, "structured_memory"):
            memories = self.memory.get_recent(agent.id, limit=10)
        return {
            "structured_memories": [m.model_dump() for m in memories],
        }

    def _fetch_semantic_memory(self, state: AgentState) -> dict:
        agent = state["agent"]
        world = state["world"]
        query = f"tick {world.tick} role {agent.role} goal {agent.goals.primary} chief {world.chief}"
        with get_profiler().agent_phase(agent.id, "semantic_memory"):
            memories = self.memory.recall(agent.id, query, world.tick, limit=5)
        return {
            "semantic_memories": [m.model_dump() for m in memories],
        }

    def _agent_roster_line(self, agent_id: str) -> str:
        others = [a for a in self.repo.get_all_agents() if a.id != agent_id]
        if not others:
            return "No other villagers available to interact with."
        roster = ", ".join(f"{a.name} ({a.id})" for a in others)
        return f"Other villagers (required target — pick one, not yourself): {roster}"

    def _synthesize_context(self, state: AgentState) -> dict:
        agent = state["agent"]
        world = state["world"]
        parts = [
            f"You are {agent.name}, a {agent.role} in a village simulation.",
            f"Tick: {world.tick}, Chief: {world.chief or 'none'}",
            f"Stats: wealth={agent.stats.wealth}, reputation={agent.stats.reputation}",
            f"Personality: greed={agent.personality.greed}, sociability={agent.personality.sociability}",
            f"Resources: food={world.resources.food}, wood={world.resources.wood}, gold={world.resources.gold}",
            f"Threat: {world.threat.level} — {world.threat.message}",
            f"Food days remaining: {world.threat.food_days_remaining}",
            f"Election active: {world.election_state.active}, candidates: {world.election_state.candidates}",
            self._agent_roster_line(agent.id),
            f"Relationships: {json.dumps(state['relationships'][:5])}",
            f"Recent memories: {json.dumps([m['text'] for m in state['structured_memories'][:3]])}",
            f"Relevant memories: {json.dumps([m['text'] for m in state['semantic_memories'][:3]])}",
            self.ACTION_SCHEMA,
        ]
        if self.config.llm.reasoning_enabled:
            parts.append(self.REASONING_INSTRUCTION)
        return {"context_summary": "\n".join(parts), "prompt": "\n".join(parts)}

    def _build_retry_prompt(
        self,
        base_prompt: str,
        *,
        attempt: int,
        max_attempts: int,
        error: Exception,
        bad_response: str,
    ) -> str:
        return (
            f"{base_prompt}\n\n"
            + self.RETRY_INSTRUCTION.format(
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(error),
                snippet=bad_response[:300],
            )
        )

    def _try_parse_and_validate(
        self,
        response_text: str,
        thinking: str,
        agents: list[Agent],
        acting_agent_id: str,
    ) -> tuple[Action, list[str]]:
        parsed = self.agent_runner.parse_llm_action(
            response_text,
            fallback_text=thinking,
        )
        normalized = self.agent_runner.normalize(
            parsed.model_dump(),
            agents=agents,
            acting_agent_id=acting_agent_id,
        )
        return normalized.action, normalized.adjustments

    def _llm_decision(self, state: AgentState) -> dict:
        agent = state["agent"]
        world = state["world"]
        base_prompt = state["prompt"]
        agents = self.repo.get_all_agents()
        max_attempts = max(1, self.config.llm.max_decision_attempts)

        response = None
        thinking = ""
        action: Action | None = None
        adjustments: list[str] = []
        last_error: Exception | None = None
        last_response_text = ""

        for attempt in range(1, max_attempts + 1):
            prompt = base_prompt
            if attempt > 1 and last_error is not None:
                prompt = self._build_retry_prompt(
                    base_prompt,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=last_error,
                    bad_response=last_response_text,
                )

            with get_profiler().agent_phase(agent.id, "llm"):
                response = self.llm_router.generate(prompt)
            thinking = response.thinking or AgentRunner.extract_inline_thinking(
                response.text
            )
            last_response_text = response.text

            with get_profiler().agent_phase(agent.id, "parse"):
                try:
                    action, adjustments = self._try_parse_and_validate(
                        response.text,
                        thinking,
                        agents,
                        agent.id,
                    )
                    if attempt > 1:
                        logger.info(
                            "LLM decision succeeded on attempt %s/%s agent_id=%s tick=%s",
                            attempt,
                            max_attempts,
                            agent.id,
                            world.tick,
                        )
                    break
                except (LLMParseError, InvalidActionError) as e:
                    last_error = e
                    if attempt < max_attempts:
                        self.tracer.trace_decision_retry(
                            agent_id=agent.id,
                            tick=world.tick,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            error_type=type(e).__name__,
                            message=str(e),
                            raw_response=response.text,
                        )
                        logger.warning(
                            "LLM decision attempt %s/%s failed agent_id=%s tick=%s error=%s",
                            attempt,
                            max_attempts,
                            agent.id,
                            world.tick,
                            e,
                        )
                        continue
                    self.tracer.trace_decision_error(
                        agent_id=agent.id,
                        tick=world.tick,
                        error_type=type(e).__name__,
                        message=str(e),
                        raw_response=response.text,
                    )
                    raise

        if action is None or response is None:
            raise InvalidActionError(
                f"Decision graph produced no valid action for agent {agent.id}"
            )

        if adjustments:
            self.tracer.trace_action_normalization(
                agent_id=agent.id,
                tick=world.tick,
                adjustments=adjustments,
            )

        if self.config.llm.store_reasoning_memory and thinking.strip():
            with get_profiler().agent_phase(agent.id, "reasoning_memory"):
                self.memory.store(
                    agent.id,
                    world.tick,
                    text=f"[Deliberation] {thinking.strip()[:500]}",
                    importance=self.config.llm.reasoning_memory_importance,
                    emotion="neutral",
                )

        with get_profiler().agent_phase(agent.id, "trace"):
            self.tracer.trace_llm_decision(
                agent_id=agent.id,
                agent_name=agent.name,
                tick=world.tick,
                provider=self.llm_router.config.default_provider,
                prompt=base_prompt,
                response=response,
                thinking=thinking,
                action_type=action.type,
                action_category=action.category,
                action_target=action.target,
            )
        return {
            "llm_response": response.text,
            "thinking": thinking,
            "action": action.model_dump(),
        }

    def _validate_action(self, state: AgentState) -> dict:
        return {"action": state["action"]}
