# Emergent Village Simulation

A standalone multi-agent simulation where villagers evolve socially, economically, and politically over time. Agents compete to become Village Chief through popular vote, wealth dominance, and coalition power.

For module-level architecture, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLite, asyncio, Pydantic
- **Vector Memory**: ChromaDB (Docker Compose service or external server)
- **Embeddings**: Provider-agnostic layer (Ollama, OpenAI-compatible) — default `nomic-embed-text-v2-moe` (768 dims)
- **Agent Orchestration**: LangChain DeepAgent SDK decision agent per villager
- **LLM**: Provider-agnostic layer (Ollama, OpenAI-compatible) — required for all agent decisions
- **Observability**: Langfuse tracing + SQLite replay + in-app metrics and tick profiling
- **Frontend**: React + Vite, D3.js relationship graph, Recharts

## Prerequisites

The simulation **fails fast at startup** if dependencies are missing. Before any setup path:

- **Docker Desktop** (Compose v2) for the recommended quickstart, **or** Python 3.11+ and Node 18+ for local development
- **Ollama on the host** (default) with chat and embedding models from `config.yaml`, **or** an OpenAI API key (see [OpenAI alternative](#openai-alternative))
- **ChromaDB** for semantic memory search — included in Docker Compose; for local API dev run `docker compose up -d chroma`
- **~4–8 GB RAM** if running the full stack with self-hosted Langfuse

Pull models after reading `config.yaml` (`llm.default_model` and `memory.embedding_model`). Current defaults:

```bash
ollama serve
ollama pull qwen3.5:2b
ollama pull nomic-embed-text-v2-moe
```

Docker Compose reaches host Ollama at `http://host.docker.internal:11434` (override with `OLLAMA_BASE_URL` in `.env`). On Linux, if the API container cannot reach Ollama, start Ollama with `OLLAMA_HOST=0.0.0.0`.

The embedding provider must be reachable at startup (Ollama `/api/embed` or OpenAI `/embeddings`). Changing `embedding_model` or `embedding_dim` requires a simulation **Reset** to re-index memories.

## Architecture

```
simulation_core/   # World, tick engine, economy, elections, events
agents/            # Agent model, DeepAgent decision pipeline, memory, relationships
llm/               # Ollama, OpenAI providers + routers (LLM + embeddings)
memory/            # Embedding contract + ChromaDB vector store client
db/                # SQLite schema + repository
api/               # FastAPI REST + WebSocket
frontend/          # React dashboard
observability/     # Langfuse integration, logging, tick profiler
exceptions.py      # Typed error hierarchy
```

## Quick Start — Docker Compose (recommended)

Run the village API, React dashboard, ChromaDB, and self-hosted Langfuse v3. **Ollama runs on the host** (not in a container) so inference uses your machine's CPU/GPU directly.

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and replace every `CHANGEME` value. Generate secrets with:

```bash
openssl rand -hex 32
```

On Windows PowerShell:

```powershell
-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
```

Use the same password for `POSTGRES_PASSWORD` and in `DATABASE_URL`.

### 2. Start Ollama and pull models

```bash
ollama serve
ollama pull qwen3.5:2b
ollama pull nomic-embed-text-v2-moe
```

(Model names must match `config.yaml`.)

### 3. Start the stack

```bash
docker compose up --build
```

First startup may take 1–2 minutes while Langfuse dependencies (Postgres, ClickHouse, Redis, MinIO) become healthy. The API healthcheck allows extra time (`start_period: 120s`) for embedding and LLM validation.

### 4. Open the dashboard

| Service | URL |
|---------|-----|
| Village dashboard | http://localhost:8080 |
| Village API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Langfuse UI | http://localhost:3000 |
| Ollama (host) | http://localhost:11434 |
| ChromaDB | http://localhost:8100 |

### 5. Run your first simulation

On the **Simulation** tab:

1. Click **Step** (one tick) or **Start** (continuous loop)
2. Watch the live timeline and relationship graph update via WebSocket
3. Select an agent in **Agent Inspector** to view decision traces (thinking + response) and the relationship history chart
4. Switch to **Errors & Logs** for structured errors, runtime logs, Langfuse metrics (6h/24h/7d), and tick profiling

Or via API:

```bash
curl -X POST http://localhost:8000/simulation/step
curl http://localhost:8000/simulation/state
```

### Langfuse

Log in at http://localhost:3000 with the **UI** credentials from `.env` (`LANGFUSE_INIT_USER_EMAIL` / `LANGFUSE_INIT_USER_PASSWORD`). These are separate from the API keys (`LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `LANGFUSE_INIT_PROJECT_SECRET_KEY`, which must use `pk-lf-*` / `sk-lf-*` format).

Langfuse keys are auto-provisioned via `LANGFUSE_INIT_*` in `.env` and passed to the API container — no manual key copy from the UI is required.

**Verify tracing** after a tick:

```bash
curl -X POST http://localhost:8000/simulation/step
```

Open http://localhost:3000 and look for traces named `village-tick-*` with `llm-decision`, `llm-decision-structured`, or `llm-decision-fallback` generation spans.

**Langfuse login not working?** `LANGFUSE_INIT_*` values are applied only on the **first** Postgres boot. If you changed `.env` after an earlier `docker compose up`, the old user may still be in the database. Reset Langfuse auth data and re-init:

```bash
docker compose down
docker volume rm villaige_langfuse_postgres_data
docker compose up -d
```

Then sign in with the current `LANGFUSE_INIT_USER_EMAIL` / `LANGFUSE_INIT_USER_PASSWORD`.

**Langfuse logs show `min_version` / `type` column missing?** That happens briefly when the `langfuse:3` image upgrades and Prisma migrations are still running. The schema should settle within a minute (`All migrations have been successfully applied` in `langfuse-web` logs). If errors persist after restart, reset the Langfuse Postgres volume (same commands as login reset above). `langfuse-worker` waits for healthy `langfuse-web` so seeding runs after migrations complete.

### Docker notes

- Ollama must be running on the host before the API container starts.
- LLM is **required** for agent decisions; there is no heuristic fallback.
- Tick failures stop the simulation loop and emit a `simulation_error` WebSocket event.
- SQLite data persists in the `village_data` volume; Chroma vectors persist in `chroma_data`; Langfuse data persists in named volumes from the Langfuse stack.
- If Chroma fails after an upgrade, reset its volume: `docker compose down` then `docker volume rm villaige_chroma_data`.

## Quick Start — Local development

For backend and frontend development without the full Docker stack (Langfuse optional).

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
docker compose up -d chroma     # vector store on localhost:8100
ollama serve                    # separate terminal; pull models per config.yaml
python run.py
```

API runs at http://localhost:8000. Docs at `/docs`. Set `LOG_LEVEL=DEBUG` for verbose logging.

Langfuse is optional for local dev: set `LANGFUSE_ENABLED=false` in `.env` or `langfuse.enabled: false` in `config.yaml`. Tracing is disabled without API keys.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at http://localhost:5173 (Vite proxies `/api` and `/ws` to the backend).

To use self-hosted Langfuse with local `python run.py`, run the Langfuse stack separately or via `docker compose up -d` and set `langfuse.base_url: http://localhost:3000` in `config.yaml`.

## OpenAI alternative

Skip host Ollama by configuring OpenAI for both chat and embeddings in `config.yaml`:

```yaml
llm:
  default_provider: openai
  default_model: gpt-4o-mini
  openai_api_key: "sk-..."

memory:
  embedding_provider: openai
  embedding_model: text-embedding-3-small
  embedding_dim: 1536
```

Set `OPENAI_API_KEY` in `.env` instead of embedding the key in YAML if you prefer. ChromaDB is still required for semantic memory.

## Configuration

Edit `config.yaml`. Representative excerpt (see the file for full economy/threat tuning):

```yaml
simulation:
  tick_duration_seconds: 0.5
  election_interval_ticks: 30
  profile_ticks: true

world:
  initial_population: 10
  initial_resources:
    food: 30
    wood: 100
    stone: 50
    gold: 200

llm:
  default_provider: ollama
  default_model: qwen3.5:2b
  structured_output_enabled: true
  max_decision_attempts: 3

memory:
  embedding_provider: ollama
  embedding_model: nomic-embed-text-v2-moe
  embedding_dim: 768
  chroma_host: localhost
  chroma_port: 8100

election:
  standing_wealth_weight: 0.45
  standing_reputation_weight: 0.55

economy:
  stewardship_mode: true
  scarcity_enabled: true
  consumption_per_agent: 1
  farmer_production: 3

langfuse:
  simulate_cost: true
  input_cost_per_million_usd: 1.50
  output_cost_per_million_usd: 9.00

database:
  path: data/village.db
```

### Environment variable overrides

Values in `.env` override `config.yaml` at runtime (see `.env.example` for the full template).

| Group | Variable | Description |
|-------|----------|-------------|
| **Paths** | `LOG_LEVEL` | Python log level (default `INFO`) |
| | `DATABASE_PATH` | SQLite path (compose: `data/village.db` in container) |
| | `CONFIG_PATH` | Alternate config file path |
| **Langfuse** | `LANGFUSE_ENABLED` | Enable tracing (`true` in compose) |
| | `LANGFUSE_PUBLIC_KEY` | Project public key |
| | `LANGFUSE_SECRET_KEY` | Project secret key |
| | `LANGFUSE_BASE_URL` | Langfuse API URL (compose internal: `http://langfuse-web:3000`) |
| | `LANGFUSE_SIMULATE_COST` | Simulate USD cost for local models |
| | `LANGFUSE_INPUT_COST_PER_MILLION_USD` | Input token rate for cost simulation |
| | `LANGFUSE_OUTPUT_COST_PER_MILLION_USD` | Output token rate for cost simulation |
| **Chroma** | `CHROMA_HOST` | ChromaDB hostname (compose: `chroma`) |
| | `CHROMA_PORT` | ChromaDB port (compose internal: `8000`, host-mapped: `8100`) |
| | `CHROMA_COLLECTION` | Collection name |
| **LLM / embeddings** | `OLLAMA_BASE_URL` | Host Ollama URL from API container (default: `http://host.docker.internal:11434`) |
| | `EMBEDDING_PROVIDER` | `ollama` or `openai` |
| | `EMBEDDING_MODEL` | Embedding model name |
| | `EMBEDDING_DIM` | Vector dimension (reset simulation after change) |
| | `LLM_REASONING_ENABLED` | Native reasoning in a single LLM call |
| | `OLLAMA_THINK` | Ollama `think` parameter |
| | `LLM_TEMPERATURE` | Sampling temperature |
| | `OPENAI_REASONING_EFFORT` | Reasoning effort for o-series models |
| | `LLM_REQUEST_TIMEOUT_SECONDS` | Standard request timeout |
| | `LLM_REASONING_REQUEST_TIMEOUT_SECONDS` | Timeout when reasoning is enabled |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/simulation/start` | Start continuous simulation |
| POST | `/simulation/stop` | Stop simulation |
| POST | `/simulation/reset` | Reset world and clear simulation data |
| POST | `/simulation/step` | Execute one tick |
| GET | `/simulation/state` | Current world state (chief, standings, election, threat) |
| GET | `/agent/{id}` | Agent details, memories, and decision traces |
| GET | `/agent/{id}/relationships/history` | Per-neighbor trust/friendship/respect/fear time series |
| GET | `/tick/{id}` | Tick snapshot + actions |
| GET | `/events` | World event log |
| GET | `/actions/types` | Valid action types and categories |
| GET | `/relationships` | All pairwise relationships |
| GET | `/observability/errors` | Structured error feed |
| GET | `/observability/logs` | Captured runtime logs |
| GET | `/observability/metrics/dashboard` | Langfuse metrics summary for in-app dashboard |
| GET | `/observability/profile` | Tick phase and per-agent timing breakdown |
| WS | `/ws/live` | Live tick/action stream |

**WebSocket events:** `tick_started`, `agent_deciding`, `action_taken`, `tick_update`, `election`, `simulation_reset`, `simulation_error`.

## Simulation Loop

Each tick (1 simulated day):

1. **World events** — storms, harvests, bandits, etc.
2. **Per-agent decisions** — observe → relationships → structured memory → semantic memory (ChromaDB) → DeepAgent SDK decision → validate action
3. **Action resolution** — `trade`, `talk`, `campaign`, `vote`, `gift`, `steal`, `sabotage`, `build`, `quarry`, `persuade`
4. **Elections** — start or advance ballots; finalize winner and assign chief
5. **Economy** — production, consumption, scarcity, reputation decay; threat level from resource strain
6. **Persistence** — SQLite state, tick snapshots, relationship snapshots, and vector memories

## Observability

- **In-app dashboard** — **Errors & Logs** tab: structured errors (with optional raw LLM response), log stream with level filter, Langfuse metrics panel (volume, latency, cost, decision mix), tick profile panel (phase and per-agent timings)
- **Langfuse UI** — full trace tree when the Compose stack is running; one `village-tick-{N}` trace per tick with nested LLM generations
- **Agent Inspector** — SQLite decision traces replayed via `/agent/{id}` (thinking, response path, parsed action)

## Development

```bash
pytest
```

Typed exceptions in `exceptions.py` replace silent fallbacks:

| Exception | When |
|-----------|------|
| `LLMProviderError` | LLM HTTP/timeout failure |
| `LLMEmptyResponseError` | Whitespace-only LLM response |
| `LLMParseError` | Cannot parse action JSON |
| `InvalidActionError` | Unknown action type or invalid target |
| `EmbeddingLoadError` | Embedding provider request or validation failed |
| `VectorStoreError` | ChromaDB unavailable or vector operation failed |
| `ConfigurationError` | Unknown LLM provider |

## Hard Constraints

- Simulation engine owns state truth
- DeepAgent SDK only produces actions
- LLM cannot mutate world state directly
- SQLite is the source of truth
- ChromaDB is only for semantic retrieval; SQLite holds authoritative memory rows
- All actions are validated before resolution

## License

MIT
