# Emergent Village Simulation

A standalone multi-agent simulation where villagers evolve socially, economically, and politically over time. Agents compete to become Village Chief through popular vote, wealth dominance, and coalition power.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLite, asyncio, Pydantic
- **Vector Memory**: ChromaDB (Docker Compose service or external server)
- **Embeddings**: Provider-agnostic layer (Ollama, OpenAI-compatible) — default `nomic-embed-text` (768 dims)
- **Agent Orchestration**: LangGraph decision pipeline per agent
- **LLM**: Provider-agnostic layer (Ollama, OpenAI-compatible) — required for all agent decisions
- **Observability**: Langfuse tracing + SQLite replay
- **Frontend**: React + Vite, D3.js relationship graph, Recharts

## Prerequisites

The simulation **fails fast at startup** if dependencies are missing:

1. **Ollama** (default) or OpenAI API key in `config.yaml`
   - Run on the host: `ollama serve` and pull both the chat and embedding models from config (e.g. `ollama pull lfm2.5:8b-a1b-q8_0` and `ollama pull nomic-embed-text`)
   - Docker Compose calls host Ollama at `http://host.docker.internal:11434` (override with `OLLAMA_BASE_URL` in `.env`)
2. **ChromaDB** for semantic memory search (`chromadb` client in `requirements.txt`)
   - Docker Compose includes a `chroma` service on http://localhost:8100
   - For local `python run.py`, start Chroma first: `docker compose up -d chroma`
3. **Embedding provider** must be reachable at startup (Ollama `/api/embed` or OpenAI `/embeddings`). Changing `embedding_model` or `embedding_dim` requires a simulation **Reset** to re-index memories.

## Architecture

```
simulation_core/   # World, tick engine, economy, elections, events
agents/            # Agent model, LangGraph pipeline, memory, relationships
llm/               # Ollama, OpenAI providers + routers (LLM + embeddings)
memory/            # Embedding contract + ChromaDB vector store client
db/                # SQLite schema + repository
api/               # FastAPI REST + WebSocket
frontend/          # React dashboard
observability/     # Langfuse integration + logging config
exceptions.py      # Typed error hierarchy
```

## Quick Start

### Backend

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -r requirements.txt
docker compose up -d chroma   # vector store on localhost:8100
ollama serve                  # separate terminal; pull model per config.yaml
python run.py
```

API runs at `http://localhost:8000`. Docs at `/docs`.

Set `LOG_LEVEL=DEBUG` for verbose logging.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at `http://localhost:5173`.

## Docker Compose (Self-Hosted Langfuse)

Run the village API, React dashboard, and self-hosted Langfuse v3 with Docker Compose. **Ollama runs on the host** (not in a container) so inference uses your machine's CPU/GPU directly.

**Requirements:** Docker Desktop (or Docker Engine + Compose v2), ~4–8 GB RAM for the Langfuse stack, and **Ollama running on the host** before `docker compose up`.

### Setup

```bash
cp .env.example .env
```

Edit `.env` and replace every `CHANGEME` value. Generate secrets with:

```bash
openssl rand -hex 32
```

Use the same password for `POSTGRES_PASSWORD` and in `DATABASE_URL`.

### Start

On the host, start Ollama and pull the configured chat and embedding models (see `config.yaml`):

```bash
ollama serve
ollama pull lfm2.5:8b-a1b-q8_0
ollama pull nomic-embed-text
```

Then start the stack:

```bash
docker compose up --build
```

First startup may take 1–2 minutes while Langfuse dependencies (Postgres, ClickHouse, Redis, MinIO) become healthy. The API healthcheck allows extra time for embedding + LLM validation.

### URLs

| Service | URL |
|---------|-----|
| Village dashboard | http://localhost:8080 |
| Village API | http://localhost:8000 |
| Langfuse UI | http://localhost:3000 |
| Ollama (host) | http://localhost:11434 |
| ChromaDB | http://localhost:8100 |

Log in to Langfuse with the **UI** credentials from `.env` (`LANGFUSE_INIT_USER_EMAIL` / `LANGFUSE_INIT_USER_PASSWORD`). These are separate from the API keys (`LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `LANGFUSE_INIT_PROJECT_SECRET_KEY`, which must use `pk-lf-*` / `sk-lf-*` format).

**Langfuse login not working?** `LANGFUSE_INIT_*` values are applied only on the **first** Postgres boot. If you changed `.env` after an earlier `docker compose up`, the old user may still be in the database. Reset Langfuse auth data and re-init:

```bash
docker compose down
docker volume rm villaige_langfuse_postgres_data
docker compose up -d
```

Then sign in with the current `LANGFUSE_INIT_USER_EMAIL` / `LANGFUSE_INIT_USER_PASSWORD`.

**Langfuse logs show `min_version` / `type` column missing?** That happens briefly when the `langfuse:3` image upgrades and Prisma migrations are still running. The schema should settle within a minute (`All migrations have been successfully applied` in `langfuse-web` logs). If errors persist after restart, reset the Langfuse Postgres volume (same commands as login reset above). `langfuse-worker` is configured to wait for healthy `langfuse-web` so seeding runs after migrations complete.

### Verify Langfuse tracing

```bash
# Run a simulation tick (traces are sent when agents make decisions)
curl -X POST http://localhost:8000/simulation/step
```

Open http://localhost:3000 and look for traces named `agent_decision_*`.

Langfuse keys are auto-provisioned via `LANGFUSE_INIT_*` in `.env` and passed to the API container — no manual key copy from the UI is required.

### Environment variables (API)

| Variable | Description |
|----------|-------------|
| `LOG_LEVEL` | Python log level (default `INFO`) |
| `LANGFUSE_ENABLED` | Enable Langfuse tracing (`true` in compose) |
| `LANGFUSE_PUBLIC_KEY` | Project public key |
| `LANGFUSE_SECRET_KEY` | Project secret key |
| `LANGFUSE_BASE_URL` | Langfuse API URL (internal: `http://langfuse-web:3000`) |
| `DATABASE_PATH` | SQLite path inside the container |
| `OLLAMA_BASE_URL` | Host Ollama URL from inside the API container (default: `http://host.docker.internal:11434`) |
| `CHROMA_HOST` | ChromaDB hostname (compose: `chroma`) |
| `CHROMA_PORT` | ChromaDB port (compose internal: `8000`, host-mapped: `8100`) |

### Notes

- Ollama must be running on the host before the API container starts. On Linux, if requests fail, set `OLLAMA_HOST=0.0.0.0` when starting Ollama so Docker can reach it.
- LLM is **required** for agent decisions; there is no heuristic fallback.
- Tick failures stop the simulation loop and emit a `simulation_error` WebSocket event.
- SQLite data persists in the `village_data` volume; Chroma vectors persist in `chroma_data`; Langfuse data persists in named volumes from the Langfuse stack.
- If Chroma fails after an upgrade, reset its volume: `docker compose down` then `docker volume rm villaige_chroma_data`.
- For local (non-Docker) development with self-hosted Langfuse, set `langfuse.base_url: http://localhost:3000` in `config.yaml` or use the env vars above.

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
  default_model: granite4.1:8b

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
2. For each agent: observe → fetch relationships → structured memory → semantic memory (ChromaDB) → LangGraph LLM decision → validate action
3. Resolve actions (trade, talk, campaign, vote, gift, steal, build, persuade)
4. Update economy (production < consumption creates scarcity)
5. Process elections every N ticks
6. Persist SQLite state + vector memories

## Error Handling

Typed exceptions in `exceptions.py` replace silent fallbacks:

| Exception | When |
|-----------|------|
| `LLMProviderError` | LLM HTTP/timeout failure |
| `LLMEmptyResponseError` | Whitespace-only LLM response |
| `LLMParseError` | Cannot parse action JSON |
| `InvalidActionError` | Unknown action type |
| `EmbeddingLoadError` | Embedding model load failure |
| `VectorStoreError` | ChromaDB unavailable or vector operation failed |
| `ConfigurationError` | Unknown LLM provider |

## Hard Constraints

- Simulation engine owns state truth
- LangGraph only produces actions
- LLM cannot mutate world state directly
- SQLite is the source of truth
- ChromaDB is only for semantic retrieval; SQLite holds authoritative memory rows
- All actions are validated before resolution

## License

MIT
