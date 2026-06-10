from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

from deepagents import create_deep_agent
from langchain_core.messages import AIMessage, HumanMessage

from agents.agent import AgentRunner
from agents.llm_schemas import LLMActionProposal
from agents.memory import AgentMemory
from agents.prompts import (
    REASONING_INSTRUCTION,
    TARGETING_INSTRUCTION,
    DecisionPromptContext,
    format_constraint_notes,
    render_decision_prompt,
    render_retry_prompt,
)
from agents.relationships import RelationshipManager
from agents.roster_utils import default_talk_action, other_agents
from agents.village_harness import register_village_harness
from config import AppConfig
from db.repository import Repository
from exceptions import InvalidActionError, LLMParseError
from llm.langchain_utils import message_to_llm_response
from llm.provider import LLMResponse, LLMResponsePath
from llm.router import LLMRouter
from models.schemas import VALID_ACTIONS, Action, Agent, WorldState
from observability.langfuse_tracer import LangfuseTracer
from observability.tick_profiler import get_profiler
from simulation_core.economy import Economy, ResourceBalance

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    agent: Agent
    world: WorldState
    agents: list[Agent]
    relationships: list[dict]
    structured_memories: list[dict]
    semantic_memories: list[dict]
    llm_response: str
    thinking: str
    action: dict
    prompt: str
    prompt_context: DecisionPromptContext
    response_path: str


class DecisionGraph:
    """Village decision pipeline powered by the LangChain DeepAgent SDK."""

    def __init__(
        self,
        repo: Repository,
        memory: AgentMemory,
        relationships: RelationshipManager,
        llm_router: LLMRouter,
        tracer: LangfuseTracer,
        agent_runner: AgentRunner,
        config: AppConfig,
        economy: Economy | None = None,
    ):
        self.repo = repo
        self.memory = memory
        self.relationships = relationships
        self.llm_router = llm_router
        self.tracer = tracer
        self.agent_runner = agent_runner
        self.config = config
        self.economy = economy or Economy(config)
        self._model_key = f"{config.llm.default_provider}:{config.llm.default_model}"
        register_village_harness(self._model_key)
        self.agent = self._build_agent()

    def _build_agent(self):
        model = self._build_chat_model()
        return create_deep_agent(
            model=model,
            system_prompt=(
                "Decide the villager's next action from the simulation context. "
                "Return exactly one valid action."
            ),
            response_format=LLMActionProposal,
        )

    def _build_chat_model(self):
        llm = self.config.llm
        timeout = (
            llm.reasoning_request_timeout_seconds
            if llm.reasoning_enabled
            else llm.request_timeout_seconds
        )
        if llm.default_provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                base_url=llm.ollama_base_url,
                model=llm.default_model,
                temperature=llm.temperature,
                reasoning=llm.ollama_think if llm.reasoning_enabled else False,
                client_kwargs={"timeout": timeout},
            )
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=llm.openai_api_key,
            base_url=llm.openai_base_url,
            model=llm.default_model,
            temperature=llm.temperature,
            timeout=timeout,
        )

    def run(self, agent: Agent, world: WorldState) -> Action:
        agents = self.repo.get_all_agents()
        state: AgentState = {
            "agent": agent,
            "world": world,
            "agents": agents,
            "relationships": [],
            "structured_memories": [],
            "semantic_memories": [],
            "llm_response": "",
            "thinking": "",
            "action": {},
            "prompt": "",
            "prompt_context": self._empty_prompt_context(),
            "response_path": "freeform",
        }
        state.update(self._fetch_relationships(state))
        state.update(self._fetch_structured_memory(state))
        state.update(self._fetch_semantic_memory(state))
        state.update(self._synthesize_context(state))

        def invoke_agent(handler) -> dict:
            config: dict = {}
            if handler is not None:
                config["callbacks"] = [handler]
                config["metadata"] = {
                    "langfuse_session_id": f"simulation-tick-{world.tick}",
                    "langfuse_user_id": agent.id,
                    "langfuse_tags": ["village-sim", agent.role],
                }
            return self._invoke_decision_agent(state, config)

        graph_result = self.tracer.run_agent_decision(agent, world, invoke_agent)
        action_data = graph_result.get("action")
        if not action_data or not action_data.get("type"):
            raise InvalidActionError(
                f"Decision agent produced no valid action for agent {agent.id}"
            )
        return Action.model_validate(action_data)

    def _invoke_decision_agent(self, state: AgentState, invoke_config: dict) -> dict:
        agent = state["agent"]
        world = state["world"]
        agents = state["agents"]
        base_prompt = state["prompt"]
        prompt_context = state.get("prompt_context") or self._empty_prompt_context()

        (
            response,
            thinking,
            action,
            adjustments,
            response_path,
            winning_attempt,
        ) = self._run_decision_attempts(
            agent=agent,
            world=world,
            agents=agents,
            base_prompt=base_prompt,
            prompt_context=prompt_context,
            invoke_config=invoke_config,
        )

        return self._record_decision_outcome(
            agent=agent,
            world=world,
            base_prompt=base_prompt,
            response=response,
            thinking=thinking,
            action=action,
            adjustments=adjustments,
            response_path=response_path,
            winning_attempt=winning_attempt,
        )

    @staticmethod
    def _empty_prompt_context() -> DecisionPromptContext:
        return DecisionPromptContext(
            agent_name="",
            agent_role="",
            tick=0,
            chief="none",
            wealth=0,
            reputation=0,
            supply_credit=0,
            greed=0.0,
            sociability=0.0,
            aggression=0.0,
            honesty=0.0,
            primary_goal="",
            food=0,
            wood=0,
            stone=0,
            gold=0,
            resource_balance_line="",
            role_stewardship_line="",
            threat_level="",
            threat_message="",
            food_days_remaining=0.0,
            election_active=False,
            candidates=[],
            roster_line="",
            relationships_json="[]",
            recent_memories_json="[]",
            semantic_memories_json="[]",
            action_schema_block="",
        )

    def _fetch_relationships(self, state: AgentState) -> dict:
        agent = state["agent"]
        profiler = get_profiler()
        with profiler.agent_phase(agent.id, "relationships"):
            relationships = self.relationships.repo.get_relationships_for_agent(agent.id)
        relationship_dicts = []
        for relationship in relationships:
            other = relationship.b_id if relationship.a_id == agent.id else relationship.a_id
            other_agent = self.repo.get_agent(other)
            relationship_dicts.append(
                {
                    "other_id": other,
                    "other_name": other_agent.name if other_agent else other,
                    "other_role": other_agent.role if other_agent else "unknown",
                    "other_wealth": other_agent.stats.wealth if other_agent else 0,
                    "trust": relationship.trust,
                    "respect": relationship.respect,
                    "fear": relationship.fear,
                    "friendship": relationship.friendship,
                }
            )
        return {"relationships": relationship_dicts}

    def _fetch_structured_memory(self, state: AgentState) -> dict:
        agent = state["agent"]
        with get_profiler().agent_phase(agent.id, "structured_memory"):
            memories = self.memory.get_recent(agent.id, limit=10)
        return {
            "structured_memories": [memory.model_dump() for memory in memories],
        }

    def _fetch_semantic_memory(self, state: AgentState) -> dict:
        agent = state["agent"]
        world = state["world"]
        query = f"tick {world.tick} role {agent.role} goal {agent.goals.primary} chief {world.chief}"
        with get_profiler().agent_phase(agent.id, "semantic_memory"):
            memories = self.memory.recall(agent.id, query, world.tick, limit=5)
        return {
            "semantic_memories": [memory.model_dump() for memory in memories],
        }

    @staticmethod
    def _agent_roster_line(agent_id: str, agents: list[Agent]) -> str:
        others = other_agents(agents, agent_id)
        if not others:
            return "No other villagers available to interact with."
        roster = ", ".join(
            f"{agent.name} [{agent.role}] ({agent.id})" for agent in others
        )
        return f"Other villagers (required target — pick one, not yourself): {roster}"

    def _forbidden_gift_targets(self, agent_id: str, tick: int) -> frozenset[str]:
        cooldown = self.config.economy.gift_pair_cooldown_ticks
        if cooldown <= 0:
            return frozenset()
        since_tick = tick - cooldown
        return frozenset(self.repo.get_gift_targets_since(agent_id, since_tick))

    def _trade_catalog_line(self) -> str:
        parts = []
        for resource, cfg in self.config.economy.trade_catalog.items():
            sellers = "/".join(cfg.seller_roles) or "nobody"
            parts.append(f"{resource} from {sellers}")
        return (
            "Trade sellers — "
            + "; ".join(parts)
            + " (target must be a villager whose role matches the resource; traders sell any commodity)."
        )

    def _resource_balance(
        self, agents: list[Agent], world: WorldState
    ) -> ResourceBalance:
        agent_map = {a.id: a for a in agents}
        return self.economy.resource_balance_summary(agent_map, world)

    def _community_gold_is_critical(
        self, world: WorldState, balance: ResourceBalance | None = None
    ) -> bool:
        cfg = self.config.economy
        stock = balance.gold_stock if balance is not None else world.resources.gold
        tier = (
            balance.gold_tier
            if balance is not None
            else self.economy._tier_from_amount(
                stock,
                cfg.threat_gold_stable,
                cfg.threat_gold_strained,
                cfg.threat_gold_critical,
            )
        )
        return tier in ("critical", "crisis") or stock < cfg.threat_gold_critical

    def _community_gold_guardrail(
        self, agent: Agent, world: WorldState, balance: ResourceBalance
    ) -> str:
        if not self._community_gold_is_critical(world, balance):
            return ""
        cfg = self.config.economy
        if agent.role == "trader":
            return (
                f"GUARDRAIL: Community gold is critically low ({balance.gold_stock} units, "
                f"threshold {cfg.threat_gold_critical}). Your role's conversions spend "
                f"{cfg.trader_gold_cost} village gold when food/wood are strained — do not "
                "broker trades that export village stock without replenishing the treasury. "
                "Prefer talk, persuade, or campaign until gold recovers (e.g. trade caravans)."
            )
        return (
            f"GUARDRAIL: Village gold is critically low ({balance.gold_stock} units) — "
            "conserve personal gold; prefer talk and persuade over gifts or trades."
        )

    def _role_stewardship_guidance(
        self, agent: Agent, balance: ResourceBalance, world: WorldState
    ) -> str:
        cfg = self.config.economy
        role = agent.role
        if role == "farmer":
            return (
                f"You produce {balance.food_production} food/tick; the village needs "
                f"{balance.food_demand}. Sell only surplus ({balance.food_net:+d}); "
                "never buy food — feeding the village is your duty."
            )
        if role == "woodcutter":
            return (
                f"You produce {balance.wood_production} wood/tick; builders consume "
                f"{balance.wood_consumption}. Do not enable wood trades that drain stock "
                "below builder needs — prioritize production over selling."
            )
        if role == "builder":
            quarry_hint = (
                " Use quarry with a partner to produce stone when stock is low."
                if balance.stone_net < 0 or balance.stone_tier in ("critical", "crisis")
                else ""
            )
            return (
                "Passive work uses 2 wood/tick and yields stone (net +1/tick when stock allows)."
                f"{quarry_hint} Do not sell stone via trade. "
                "Use build only when wood allows; quarry before trading stone away."
            )
        if role == "trader":
            guidance = (
                f"Each conversion costs {cfg.trader_gold_cost} village gold when food/wood "
                "are strained. Broker trades only when village net balance improves — do "
                "not drain wood, stone, or gold faster than production replaces them."
            )
            guardrail = self._community_gold_guardrail(agent, world, balance)
            if guardrail:
                guidance = f"{guidance} {guardrail}"
            return guidance
        if role == "guard":
            return (
                "Protect village stock — discourage wasteful trades and sabotage that "
                "deplete resources the village needs to survive."
            )
        return (
            "The village needs production to exceed consumption. Avoid actions that "
            "drain scarce resources for personal gain."
        )

    def _strategic_guidance(
        self, agent: Agent, world: WorldState, balance: ResourceBalance
    ) -> str:
        scarce = world.threat.level in ("strained", "critical", "crisis")
        personality = agent.personality
        hints: list[str] = [
            "Vary actions — talk and persuade cost no gold; gifts have per-person cooldown "
            "and no standing gain when returning a recent gift."
        ]
        if agent.role == "farmer":
            hints.append(
                "You feed the village through daily production — do NOT trade to buy food. "
                "Sell only surplus; prioritize talk, quarry-partner, build, or campaign "
                "over overselling food."
            )
        if scarce:
            hints.append(
                "Village resources are low — secure supply through production and prudent "
                "trade, rather than giving gold away or draining stock."
            )
        if balance.wood_tier in ("critical", "crisis") and agent.role != "woodcutter":
            hints.append(
                "Wood is critically low — do not buy wood via trade unless absolutely necessary."
            )
        if balance.stone_tier in ("critical", "crisis") and agent.role != "builder":
            hints.append(
                "Stone is critically low — do not buy stone via trade; encourage builders to quarry."
            )
        if self._community_gold_is_critical(world, balance):
            if agent.role == "trader":
                hints.append(
                    "Community treasury is critically low — steward village gold; "
                    "choose talk or persuade over trade brokering until reserves recover."
                )
            else:
                hints.append(
                    "Village gold reserves are critically low — favor talk over costly gifts or trades."
                )
        if agent.role == "builder" and balance.stone_net < 0:
            hints.append(
                "Stone runs a deficit each tick — prefer quarry over trade to replenish village stone."
            )
        if agent.stats.supply_credit == 0 and scarce:
            hints.append(
                "You have no supply_credit buffer — buy goods via trade so a shortage "
                "does not cost you reputation."
            )
        if world.election_state.active:
            hints.append(
                "Election active — campaign and vote raise standing; avoid gift loops."
            )
        if agent.stats.wealth <= 3:
            hints.append("Low personal wealth — conserve gold for trade or emergencies.")
        if personality.greed >= 0.7 and agent.goals.primary == "accumulate_wealth":
            hints.append(
                "You are greedy and wealth-driven — stealing gold from a wealthy rival you "
                "distrust can pay off despite the reputation hit, especially if few admire them."
            )
        if personality.aggression >= 0.7:
            hints.append(
                "You are aggressive — hostile actions against rivals you distrust are viable; "
                "villagers who also dislike the victim will respect you for it."
            )
            if scarce:
                hints.append(
                    "Under scarcity, destroying village resources hurts everyone — "
                    "sabotage only as a last resort against rivals villagers already distrust."
                )
        if personality.honesty >= 0.7:
            hints.append("You value honesty — favor trade and talk over stealing or sabotage.")
        return " ".join(hints)

    def _action_constraints(
        self, agent: Agent, world: WorldState
    ) -> tuple[list[str], list[str]]:
        allowed = list(sorted(VALID_ACTIONS))
        notes: list[str] = []
        cfg = self.config.economy

        if agent.stats.wealth < 1:
            allowed = [action_type for action_type in allowed if action_type not in {"gift", "trade"}]
            notes.append(
                "gift and trade are FORBIDDEN — you have 0 gold; use talk, persuade, "
                "steal, sabotage, campaign, vote, build, or quarry instead"
            )
        if agent.role == "farmer":
            notes.append(
                "trade for food is FORBIDDEN — you produce food for the village; use talk, "
                "build, quarry-partner, campaign, persuade, or trade for wood/stone only"
            )
        if agent.role != "builder":
            allowed = [action_type for action_type in allowed if action_type != "quarry"]
            if "quarry" in VALID_ACTIONS:
                notes.append(
                    "quarry is FORBIDDEN — only builders can quarry stone"
                )
        elif world.resources.wood < cfg.builder_quarry_wood_cost:
            allowed = [action_type for action_type in allowed if action_type != "quarry"]
            notes.append(
                f"quarry is FORBIDDEN — village wood is below {cfg.builder_quarry_wood_cost} "
                "(tools required)"
            )
        if world.resources.wood < 2:
            allowed = [action_type for action_type in allowed if action_type != "build"]
            notes.append("build is FORBIDDEN — village wood is below 2")
        if not world.election_state.active:
            allowed = [action_type for action_type in allowed if action_type not in {"vote", "campaign"}]
            notes.append("vote and campaign are FORBIDDEN — no election is active")

        gift_blocked = self._forbidden_gift_targets(agent.id, world.tick)
        if gift_blocked:
            blocked = ", ".join(sorted(gift_blocked))
            notes.append(
                f"gift to these villagers is FORBIDDEN (recently gifted): {blocked} — "
                "use talk, trade, build, persuade, or gift someone else"
            )

        if self._community_gold_is_critical(world):
            threshold = cfg.threat_gold_critical
            if agent.role == "trader":
                notes.append(
                    f"GUARDRAIL: community gold is below {threshold} — prefer talk/persuade; "
                    "avoid brokering trades that drain village commodities while treasury is empty"
                )
            else:
                notes.append(
                    f"GUARDRAIL: village gold is below {threshold} — prefer talk/persuade "
                    "over gift or trade"
                )

        return allowed, notes

    def _action_schema(
        self, agent: Agent, world: WorldState, balance: ResourceBalance
    ) -> str:
        allowed, notes = self._action_constraints(agent, world)
        type_options = "|".join(allowed)
        lines = [
            "Respond with ONLY valid JSON:",
            f'{{"type": "<{type_options}>", "target": "<agent_id>", "payload": {{}}}}',
            "JSON rules: standard JSON only (numbers without + prefix); payload uses game "
            "fields only (topic for talk, amount/price/resource for trades) — never invent "
            "cooldown_remaining, reputation_change, trust_change, effect, or other stats.",
            TARGETING_INSTRUCTION,
        ]
        constraint_line = format_constraint_notes(notes)
        if constraint_line:
            lines.append(constraint_line)
        if agent.stats.wealth >= 1:
            lines.append(
                "Economic payloads: gift uses \"amount\" (gold you give away, max = your wealth); "
                "trade uses \"resource\" (food|wood|stone), \"amount\" (units to buy), and "
                "\"price\" (gold you pay, max = your wealth)."
            )
            lines.append(self._trade_catalog_line())
        lines.append(
            'gift just hands over gold for goodwill; trade spends gold to buy village '
            'goods from a qualified seller and earns you supply_credit against shortages.'
        )
        lines.append(
            'sabotage uses "resource" (food|wood) and "amount" (units to destroy from '
            "village stock) to undermine a rival; avoid when village stock is scarce."
        )
        lines.append(
            'Use "build" to construct with someone (not "craft" alone); '
            'use "trade" to buy goods from someone (not solo "gather"/"hunt"/"resource").'
        )
        lines.append(
            'quarry uses "amount" (stone units to extract, default 1) — builder-only; '
            "costs village wood for tools; adds stone to village stock."
        )
        lines.append(
            "Use agent_id from the other-villagers roster for target, not names."
        )
        lines.append(self._strategic_guidance(agent, world, balance))
        return "\n".join(lines)

    def _build_prompt_context(
        self, state: AgentState, agent: Agent, world: WorldState
    ) -> DecisionPromptContext:
        reasoning_instruction = (
            REASONING_INSTRUCTION if self.config.llm.reasoning_enabled else ""
        )
        balance = self._resource_balance(state["agents"], world)
        return DecisionPromptContext(
            agent_name=agent.name,
            agent_role=agent.role,
            tick=world.tick,
            chief=world.chief or "none",
            wealth=agent.stats.wealth,
            reputation=agent.stats.reputation,
            supply_credit=agent.stats.supply_credit,
            greed=agent.personality.greed,
            sociability=agent.personality.sociability,
            aggression=agent.personality.aggression,
            honesty=agent.personality.honesty,
            primary_goal=agent.goals.primary,
            food=world.resources.food,
            wood=world.resources.wood,
            stone=world.resources.stone,
            gold=world.resources.gold,
            resource_balance_line=self.economy.format_balance_line(balance),
            role_stewardship_line=self._role_stewardship_guidance(agent, balance, world),
            threat_level=world.threat.level,
            threat_message=world.threat.message,
            food_days_remaining=world.threat.food_days_remaining,
            election_active=world.election_state.active,
            candidates=world.election_state.candidates,
            roster_line=self._agent_roster_line(agent.id, state["agents"]),
            relationships_json=json.dumps(state["relationships"][:5]),
            recent_memories_json=json.dumps(
                [memory["text"] for memory in state["structured_memories"][:3]]
            ),
            semantic_memories_json=json.dumps(
                [memory["text"] for memory in state["semantic_memories"][:3]]
            ),
            action_schema_block=self._action_schema(agent, world, balance),
            reasoning_instruction=reasoning_instruction,
        )

    @staticmethod
    def _is_blocked_economic_error(error: Exception, agent: Agent) -> bool:
        if agent.stats.wealth >= 1:
            return False
        message = str(error).lower()
        return "cannot gift" in message or "cannot trade" in message

    def _synthesize_context(self, state: AgentState) -> dict:
        agent = state["agent"]
        world = state["world"]
        prompt_context = self._build_prompt_context(state, agent, world)
        prompt = render_decision_prompt(prompt_context)
        return {
            "prompt": prompt,
            "prompt_context": prompt_context,
        }

    def _build_retry_prompt(
        self,
        base_prompt: str,
        *,
        prompt_context: DecisionPromptContext,
        agent: Agent,
        world: WorldState,
        attempt: int,
        max_attempts: int,
        error: Exception,
        bad_response: str,
    ) -> str:
        allowed, notes = self._action_constraints(agent, world)
        return render_retry_prompt(
            prompt_context,
            base_prompt=base_prompt,
            attempt=attempt,
            max_attempts=max_attempts,
            error=str(error),
            valid_types=", ".join(allowed),
            constraints=format_constraint_notes(notes),
            snippet=bad_response[:300],
        )

    def _normalize_action_dict(
        self,
        action_data: dict[str, Any],
        agents: list[Agent],
        acting_agent_id: str,
        *,
        forbidden_gift_targets: frozenset[str] | None = None,
    ) -> tuple[Action, list[str]]:
        normalized = self.agent_runner.normalize(
            action_data,
            agents=agents,
            acting_agent_id=acting_agent_id,
            forbidden_gift_targets=forbidden_gift_targets,
            trade_catalog=self.config.economy.trade_catalog,
            stewardship_mode=self.config.economy.stewardship_mode,
        )
        return normalized.action, normalized.adjustments

    def _try_parse_and_validate(
        self,
        response_text: str,
        thinking: str,
        agents: list[Agent],
        acting_agent_id: str,
        *,
        forbidden_gift_targets: frozenset[str] | None = None,
    ) -> tuple[Action, list[str]]:
        normalized = self.agent_runner.parse_llm_action(
            response_text,
            fallback_text=thinking,
            agents=agents,
            acting_agent_id=acting_agent_id,
            forbidden_gift_targets=forbidden_gift_targets,
            trade_catalog=self.config.economy.trade_catalog,
            stewardship_mode=self.config.economy.stewardship_mode,
        )
        return normalized.action, normalized.adjustments

    def _response_from_agent_result(
        self,
        result: dict[str, Any],
        *,
        model_name: str,
        elapsed_ms: float,
    ) -> LLMResponse:
        messages = result.get("messages") or []
        ai_message = next(
            (message for message in reversed(messages) if isinstance(message, AIMessage)),
            None,
        )
        if ai_message is not None:
            return message_to_llm_response(
                ai_message,
                model=model_name,
                latency_ms=elapsed_ms,
            )
        structured = result.get("structured_response")
        text = structured.model_dump_json() if structured is not None else ""
        return LLMResponse(text=text, latency_ms=elapsed_ms, model=model_name)

    def _invoke_deep_agent_attempt(
        self,
        prompt: str,
        agent: Agent,
        agents: list[Agent],
        *,
        tick: int,
        invoke_config: dict,
    ) -> tuple[LLMResponse, str, Action | None, list[str], Exception | None, LLMResponsePath]:
        thinking = ""
        parse_error: Exception | None = None
        forbidden_gift_targets = self._forbidden_gift_targets(agent.id, tick)
        model_name = self.config.llm.default_model
        response_path: LLMResponsePath = "structured"

        with get_profiler().agent_phase(agent.id, "llm"):
            import time

            start = time.perf_counter()
            try:
                result = self.agent.invoke(
                    {"messages": [HumanMessage(content=prompt)]},
                    config=invoke_config,
                )
            except Exception as error:
                if self.config.llm.structured_output_enabled:
                    self.tracer.trace_structured_fallback(
                        agent_id=agent.id,
                        tick=tick,
                        message=str(error),
                    )
                raise
            elapsed = (time.perf_counter() - start) * 1000

        response = self._response_from_agent_result(
            result,
            model_name=model_name,
            elapsed_ms=elapsed,
        )
        thinking = response.thinking or AgentRunner.extract_inline_thinking(response.text)

        structured = result.get("structured_response")
        if isinstance(structured, LLMActionProposal):
            with get_profiler().agent_phase(agent.id, "parse"):
                try:
                    action, adjustments = self._normalize_action_dict(
                        structured.model_dump(),
                        agents,
                        agent.id,
                        forbidden_gift_targets=forbidden_gift_targets,
                    )
                    return response, thinking, action, adjustments, None, "structured"
                except InvalidActionError as error:
                    return response, thinking, None, [], error, "structured"
                except LLMParseError as error:
                    parse_error = error

        if self.config.llm.structured_output_enabled and parse_error is not None:
            self.tracer.trace_structured_fallback(
                agent_id=agent.id,
                tick=tick,
                message=str(parse_error),
            )

        with get_profiler().agent_phase(agent.id, "parse"):
            try:
                action, adjustments = self._try_parse_and_validate(
                    response.text,
                    thinking,
                    agents,
                    agent.id,
                    forbidden_gift_targets=forbidden_gift_targets,
                )
                path: LLMResponsePath = (
                    "structured_fallback" if parse_error is not None else "freeform"
                )
                return response, thinking, action, adjustments, None, path
            except (LLMParseError, InvalidActionError) as error:
                if parse_error is not None and isinstance(error, LLMParseError):
                    return response, thinking, None, [], parse_error, "structured_fallback"
                path = "structured_fallback" if parse_error is not None else "freeform"
                return response, thinking, None, [], error, path

    def _run_decision_attempts(
        self,
        *,
        agent: Agent,
        world: WorldState,
        agents: list[Agent],
        base_prompt: str,
        prompt_context: DecisionPromptContext,
        invoke_config: dict,
    ) -> tuple[LLMResponse, str, Action, list[str], LLMResponsePath, int]:
        max_attempts = max(1, self.config.llm.max_decision_attempts)
        response: LLMResponse | None = None
        thinking = ""
        action: Action | None = None
        adjustments: list[str] = []
        last_error: Exception | None = None
        last_response_text = ""
        response_path: LLMResponsePath = "freeform"
        winning_attempt = 1

        for attempt in range(1, max_attempts + 1):
            prompt = base_prompt
            if attempt > 1 and last_error is not None:
                prompt = self._build_retry_prompt(
                    base_prompt,
                    prompt_context=prompt_context,
                    agent=agent,
                    world=world,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=last_error,
                    bad_response=last_response_text,
                )

            (
                response,
                thinking,
                attempt_action,
                attempt_adjustments,
                attempt_error,
                attempt_path,
            ) = self._invoke_deep_agent_attempt(
                prompt,
                agent,
                agents,
                tick=world.tick,
                invoke_config=invoke_config,
            )

            last_response_text = response.text
            response_path = attempt_path

            if attempt_action is not None:
                action = attempt_action
                adjustments = attempt_adjustments
                winning_attempt = attempt
                if attempt > 1:
                    logger.info(
                        "LLM decision succeeded on attempt %s/%s agent_id=%s tick=%s",
                        attempt,
                        max_attempts,
                        agent.id,
                        world.tick,
                    )
                break

            last_error = attempt_error or LLMParseError("Unknown parse failure")
            if self._is_blocked_economic_error(last_error, agent):
                action = default_talk_action(agent, agents)
                adjustments = ["fallback:talk(wealth=0)"]
                logger.info(
                    "Skipping retries for agent_id=%s tick=%s — "
                    "economic action blocked at 0 wealth",
                    agent.id,
                    world.tick,
                )
                break
            if attempt < max_attempts:
                self.tracer.trace_decision_retry(
                    agent_id=agent.id,
                    tick=world.tick,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error_type=type(last_error).__name__,
                    message=str(last_error),
                    raw_response=response.text,
                )
                logger.warning(
                    "LLM decision attempt %s/%s failed agent_id=%s tick=%s error=%s",
                    attempt,
                    max_attempts,
                    agent.id,
                    world.tick,
                    last_error,
                )
                continue

            self.tracer.trace_decision_error(
                agent_id=agent.id,
                tick=world.tick,
                error_type=type(last_error).__name__,
                message=str(last_error),
                raw_response=response.text,
            )
            action = default_talk_action(agent, agents)
            adjustments = ["fallback:talk"]
            logger.warning(
                "Using fallback talk for agent_id=%s tick=%s after %s "
                "failed attempts: %s",
                agent.id,
                world.tick,
                max_attempts,
                last_error,
            )
            break

        if action is None or response is None:
            raise InvalidActionError(
                f"Decision agent produced no valid action for agent {agent.id}"
            )
        return response, thinking, action, adjustments, response_path, winning_attempt

    def _record_decision_outcome(
        self,
        *,
        agent: Agent,
        world: WorldState,
        base_prompt: str,
        response: LLMResponse,
        thinking: str,
        action: Action,
        adjustments: list[str],
        response_path: LLMResponsePath,
        winning_attempt: int,
    ) -> dict:
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
                response_path=response_path,
                attempt=winning_attempt,
            )
        return {
            "llm_response": response.text,
            "thinking": thinking,
            "action": action.model_dump(),
            "response_path": response_path,
        }
