from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from agents.agent import AgentRunner
from agents.memory import AgentMemory
from agents.relationships import RelationshipManager
from db.repository import Repository
from llm.router import LLMRouter
from models.schemas import Action, Agent, WorldState
from observability.langfuse_tracer import LangfuseTracer


class AgentState(TypedDict):
    agent: Agent
    world: WorldState
    relationships: list[dict]
    structured_memories: list[dict]
    semantic_memories: list[dict]
    context_summary: str
    llm_response: str
    action: dict
    prompt: str


class DecisionGraph:
    ACTION_SCHEMA = """Respond with ONLY valid JSON:
{"type": "<trade|talk|campaign|vote|gift|steal|build|persuade>",
 "target": "<agent_id or null>",
 "payload": {}}"""

    def __init__(
        self,
        repo: Repository,
        memory: AgentMemory,
        relationships: RelationshipManager,
        llm_router: LLMRouter,
        tracer: LangfuseTracer,
        agent_runner: AgentRunner,
        use_llm: bool = True,
    ):
        self.repo = repo
        self.memory = memory
        self.relationships = relationships
        self.llm_router = llm_router
        self.tracer = tracer
        self.agent_runner = agent_runner
        self.use_llm = use_llm
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
            "action": {},
            "prompt": "",
        }
        result = self.graph.invoke(initial)
        action_data = result.get("action", {})
        return Action(
            type=action_data.get("type", "talk"),
            target=action_data.get("target"),
            payload=action_data.get("payload", {}),
        )

    def _observe(self, state: AgentState) -> dict:
        return {}

    def _fetch_relationships(self, state: AgentState) -> dict:
        agent = state["agent"]
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
        memories = self.memory.get_recent(agent.id, limit=10)
        return {
            "structured_memories": [m.model_dump() for m in memories],
        }

    def _fetch_semantic_memory(self, state: AgentState) -> dict:
        agent = state["agent"]
        world = state["world"]
        query = f"tick {world.tick} role {agent.role} goal {agent.goals.primary} chief {world.chief}"
        memories = self.memory.recall(agent.id, query, world.tick, limit=5)
        return {
            "semantic_memories": [m.model_dump() for m in memories],
        }

    def _synthesize_context(self, state: AgentState) -> dict:
        agent = state["agent"]
        world = state["world"]
        parts = [
            f"You are {agent.name}, a {agent.role} in a village simulation.",
            f"Tick: {world.tick}, Chief: {world.chief or 'none'}",
            f"Stats: wealth={agent.stats.wealth}, reputation={agent.stats.reputation}",
            f"Personality: greed={agent.personality.greed}, sociability={agent.personality.sociability}",
            f"Resources: food={world.resources.food}, wood={world.resources.wood}",
            f"Election active: {world.election_state.active}, candidates: {world.election_state.candidates}",
            f"Relationships: {json.dumps(state['relationships'][:5])}",
            f"Recent memories: {json.dumps([m['text'] for m in state['structured_memories'][:3]])}",
            f"Relevant memories: {json.dumps([m['text'] for m in state['semantic_memories'][:3]])}",
            self.ACTION_SCHEMA,
        ]
        return {"context_summary": "\n".join(parts), "prompt": "\n".join(parts)}

    def _llm_decision(self, state: AgentState) -> dict:
        agent = state["agent"]
        world = state["world"]
        prompt = state["prompt"]

        if self.use_llm:
            response = self.llm_router.generate(prompt)
            if response.text.strip():
                action = self.agent_runner.parse_llm_action(response.text)
                self.tracer.trace_decision(
                    agent_id=agent.id,
                    tick=world.tick,
                    prompt=prompt,
                    response=response.text,
                    latency_ms=response.latency_ms,
                    token_usage=response.token_usage,
                    action_type=action.type,
                )
                return {
                    "llm_response": response.text,
                    "action": action.model_dump(),
                }

        other_agents = [
            {"id": a.id, "name": a.name}
            for a in self.repo.get_all_agents()
            if a.id != agent.id
        ]
        context = {
            "relationships": state["relationships"],
            "election_candidates": world.election_state.candidates,
            "other_agents": other_agents,
        }
        action = self.agent_runner.heuristic.decide(agent, world, context)
        return {"llm_response": "", "action": action.model_dump()}

    def _validate_action(self, state: AgentState) -> dict:
        action = Action(**state["action"])
        validated = self.agent_runner.validate_action(action)
        return {"action": validated.model_dump()}
