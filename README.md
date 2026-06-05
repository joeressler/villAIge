# Emergent Village Simulation

A standalone multi-agent simulation where villagers evolve socially, economically, and politically over time. Agents compete to become Village Chief through popular vote, wealth dominance, and coalition power.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLite, asyncio, Pydantic
- **Vector Memory**: SQLite-VSS (with numpy cosine fallback)
- **Embeddings**: sentence-transformers (all-MiniLM-L6-v2, 384 dims)
- **Agent Orchestration**: LangGraph decision pipeline per agent
- **LLM**: Provider-agnostic layer (Ollama, OpenAI-compatible)
- **Observability**: Langfuse tracing + SQLite replay
- **Frontend**: React + Vite, D3.js relationship graph, Recharts

## Architecture

```
simulation_core/   # World, tick engine, economy, elections, events
agents/            # Agent model, LangGraph pipeline, memory, relationships
llm/               # Ollama, OpenAI providers + router
memory/            # Embeddings + SQLite-VSS vector store
db/                # SQLite schema + repository
api/               # FastAPI REST + WebSocket
frontend/          # React dashboard
observability/     # Langfuse integration
```

## Quick Start

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

API runs at `http://localhost:8000`. Docs at `/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at `http://localhost:5173`.

### Run Simulation

```bash
# Start continuous simulation
curl -X POST http://localhost:8000/simulation/start

# Single tick step
curl -X POST http://localhost:8000/simulation/step

# Get state
curl http://localhost:8000/simulation/state

# Stop
curl -X POST http://localhost:8000/simulation/stop
```

### Enable LLM Decisions

Requires Ollama running locally (`ollama serve`) or OpenAI API key in `config.yaml`.

```bash
curl -X POST http://localhost:8000/simulation/llm -H "Content-Type: application/json" -d '{"enabled": true}'
```

## Configuration

Edit `config.yaml`:

```yaml
simulation:
  tick_duration_seconds: 0.5
  election_interval_ticks: 30

world:
  initial_population: 20

llm:
  default_provider: ollama
  default_model: llama3.1:8b

economy:
  scarcity_enabled: true
  consumption_per_agent: 3
  farmer_production: 2
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/simulation/start` | Start continuous simulation |
| POST | `/simulation/stop` | Stop simulation |
| POST | `/simulation/step` | Execute one tick |
| GET | `/simulation/state` | Current world state |
| GET | `/agent/{id}` | Agent details + memories |
| GET | `/tick/{id}` | Tick snapshot + actions |
| GET | `/events` | World event log |
| GET | `/relationships` | All relationships |
| WS | `/ws/live` | Live tick/action stream |

## Simulation Loop

Each tick (1 simulated day):

1. Generate world events
2. For each agent: observe → fetch relationships → structured memory → semantic memory (VSS) → LangGraph decision → validate action
3. Resolve actions (trade, talk, campaign, vote, gift, steal, build, persuade)
4. Update economy (production < consumption creates scarcity)
5. Process elections every N ticks
6. Persist SQLite state + vector memories

## Hard Constraints

- Simulation engine owns state truth
- LangGraph only produces actions
- LLM cannot mutate world state directly
- SQLite is the source of truth
- SQLite-VSS is only for retrieval
- All actions are validated before resolution

## License

MIT
