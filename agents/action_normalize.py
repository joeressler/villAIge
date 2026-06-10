from __future__ import annotations

from dataclasses import dataclass, field

from config import TradeResourceConfig
from exceptions import InvalidActionError
from models.schemas import VALID_ACTIONS, Action, Agent, coerce_stat_int, normalize_action_type


@dataclass
class NormalizedAction:
    action: Action
    adjustments: list[str] = field(default_factory=list)


def _valid_ids(
    agents: list[Agent] | None,
    valid_agent_ids: frozenset[str] | None,
) -> frozenset[str]:
    if valid_agent_ids is not None:
        return valid_agent_ids
    if agents is not None:
        return frozenset(agent.id for agent in agents)
    return frozenset()


def normalize_action(
    raw_action_dict: dict,
    *,
    agents: list[Agent] | None = None,
    valid_agent_ids: frozenset[str] | None = None,
    aliases: dict[str, str] | None = None,
    acting_agent_id: str | None = None,
    forbidden_gift_targets: frozenset[str] | None = None,
    trade_catalog: dict[str, TradeResourceConfig] | None = None,
    stewardship_mode: bool = True,
) -> NormalizedAction:
    adjustments: list[str] = []
    action_type = str(raw_action_dict.get("type", "")).strip().lower()
    if aliases and action_type in aliases:
        mapped = aliases[action_type]
        adjustments.append(f"alias:{action_type}->{mapped}")
        action_type = mapped
    action_type = normalize_action_type(action_type)
    if action_type not in VALID_ACTIONS:
        raise InvalidActionError(f"Unknown action type: {action_type!r}")

    target = raw_action_dict.get("target")
    if isinstance(target, str):
        target = target.strip() or None
    else:
        target = None

    ids = _valid_ids(agents, valid_agent_ids)
    if ids:
        if not target:
            raise InvalidActionError(f"Action {action_type} requires a target agent_id")
        if target not in ids:
            raise InvalidActionError(f"Invalid target agent_id: {target!r}")
        if acting_agent_id and target == acting_agent_id:
            raise InvalidActionError("Cannot target yourself")

    payload = raw_action_dict.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    acting = next((agent for agent in agents or [] if agent.id == acting_agent_id), None)
    if acting is not None:
        if action_type in {"gift", "trade"} and acting.stats.wealth < 1:
            raise InvalidActionError(
                f"Cannot {action_type} with 0 gold"
            )
        if action_type == "gift" and target and forbidden_gift_targets and target in forbidden_gift_targets:
            raise InvalidActionError(f"Cannot gift to {target} (recent cooldown)")
        if (
            stewardship_mode
            and action_type == "trade"
            and acting.role == "farmer"
            and str(payload.get("resource", "food")).lower() == "food"
        ):
            raise InvalidActionError("Farmers cannot trade to buy food")

    if action_type == "trade":
        resource = str(payload.get("resource", "food")).lower()
        if trade_catalog and resource not in trade_catalog:
            raise InvalidActionError(f"Unsupported trade resource: {resource!r}")
        payload = {
            **payload,
            "resource": resource,
            "amount": coerce_stat_int(payload.get("amount"), default=1),
            "price": coerce_stat_int(payload.get("price"), default=3),
        }
    elif action_type == "gift":
        payload = {
            **payload,
            "amount": coerce_stat_int(payload.get("amount"), default=1),
        }
    elif action_type == "talk":
        payload = {
            **payload,
            "topic": str(payload.get("topic", "greetings")),
        }
    elif action_type == "sabotage":
        payload = {
            **payload,
            "resource": str(payload.get("resource", "wood")).lower(),
            "amount": coerce_stat_int(payload.get("amount"), default=1),
        }
    elif action_type == "quarry":
        payload = {
            **payload,
            "amount": coerce_stat_int(payload.get("amount"), default=1),
        }
    elif action_type == "steal":
        payload = {
            **payload,
            "amount": coerce_stat_int(payload.get("amount"), default=2),
        }

    return NormalizedAction(
        action=Action(type=action_type, target=target, payload=payload),
        adjustments=adjustments,
    )
