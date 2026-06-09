from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from api.websocket import manager, websocket_endpoint
from config import load_config
from models.schemas import ACTION_CATEGORIES
from observability.logging_config import configure_logging
from observability.feed import feed
from observability.langfuse_metrics import get_metrics_dashboard
from observability.tick_profiler import get_profiler
from simulation_core.standing import standings_for_agents
from simulation_core.tick_engine import TickEngine

configure_logging()
logger = logging.getLogger(__name__)

config = load_config()
engine = TickEngine(config)
_pump_task: asyncio.Task | None = None
_initialized = False


def _ensure_initialized() -> None:
    global _initialized
    if not _initialized or not engine.agents:
        engine.initialize()
        _initialized = True


def _on_engine_event(event: dict[str, Any]) -> None:
    manager.enqueue(event)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pump_task
    engine.add_listener(_on_engine_event)
    _ensure_initialized()
    _pump_task = asyncio.create_task(manager.pump())
    yield
    await engine.stop()
    if _pump_task:
        _pump_task.cancel()
        try:
            await _pump_task
        except asyncio.CancelledError:
            pass
    engine.tracer.flush()
    engine.repo.close()


app = FastAPI(
    title="Emergent Village Simulation",
    description="Multi-agent village simulation with SQLite + LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/simulation/start")
async def start_simulation():
    _ensure_initialized()
    await engine.start()
    return {"status": "running", "tick": engine.state.tick}


@app.post("/simulation/stop")
async def stop_simulation():
    await engine.stop()
    return {"status": "stopped", "tick": engine.state.tick}


@app.post("/simulation/reset")
async def reset_simulation():
    global _initialized
    state = await engine.reset()
    feed.clear()
    _initialized = True
    return {
        "status": "reset",
        "tick": state.tick,
        "population": state.population,
        "resources": state.resources.model_dump(),
    }


@app.post("/simulation/step")
async def step_simulation():
    _ensure_initialized()
    result = await engine.step()
    return result


@app.get("/simulation/state")
async def get_state():
    _ensure_initialized()
    state = engine.state
    agents = [a.model_dump() for a in engine.agents.values()]
    chief_name = None
    if state.chief and state.chief in engine.agents:
        chief_name = engine.agents[state.chief].name
    standings = standings_for_agents(engine.agents, config.election)
    ballot_tally = engine.elections.ballot_tally(state)
    candidate_names = {
        cid: engine.agents[cid].name
        for cid in state.election_state.candidates
        if cid in engine.agents
    }
    agents_with_standing = [
        {**a, "standing": round(standings.get(a["id"], 0.0), 3)}
        for a in agents
    ]
    return {
        "tick": state.tick,
        "population": state.population,
        "chief": state.chief,
        "chief_name": chief_name,
        "resources": state.resources.model_dump(),
        "threat": state.threat.model_dump(),
        "election_state": state.election_state.model_dump(),
        "election_candidate_names": candidate_names,
        "election_ballot_tally": ballot_tally,
        "agents": agents_with_standing,
        "running": engine._running,
    }


@app.get("/agent/{agent_id}")
async def get_agent(agent_id: str):
    detail = engine.get_agent_detail(agent_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Agent not found")
    return detail


@app.get("/tick/{tick_id}")
async def get_tick(tick_id: int):
    detail = engine.get_tick_detail(tick_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Tick not found")
    return detail


@app.get("/events")
async def get_events(limit: int = 50):
    return engine.repo.get_world_events(limit=limit)


@app.get("/actions/types")
async def get_action_types():
    return {
        action_type: {"category": category}
        for action_type, category in ACTION_CATEGORIES.items()
    }


@app.get("/relationships")
async def get_relationships():
    rels = engine.repo.get_all_relationships()
    agents = {a.id: a.name for a in engine.agents.values()}
    return [
        {
            **r.model_dump(),
            "a_name": agents.get(r.a_id, r.a_id),
            "b_name": agents.get(r.b_id, r.b_id),
        }
        for r in rels
    ]


@app.get("/observability/errors")
async def get_error_feed(limit: int = 100):
    return feed.get_errors(limit=limit)


@app.get("/observability/logs")
async def get_log_feed(limit: int = 100, min_level: str = "INFO"):
    return feed.get_logs(limit=limit, min_level=min_level)


@app.get("/observability/metrics/dashboard")
async def get_langfuse_metrics_dashboard(hours: int = 24):
    return get_metrics_dashboard(config.langfuse, hours=hours)


@app.get("/observability/profile")
async def get_tick_profile(limit: int = 10):
    profiler = get_profiler()
    return {
        "summary": profiler.get_summary(limit=limit),
        "recent_ticks": profiler.get_recent(limit=limit),
    }


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket_endpoint(websocket)
