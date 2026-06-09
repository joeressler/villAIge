-- Emergent Village Simulation schema

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    wealth INTEGER NOT NULL DEFAULT 10,
    reputation INTEGER NOT NULL DEFAULT 50,
    influence INTEGER NOT NULL DEFAULT 10,
    greed REAL NOT NULL DEFAULT 0.5,
    sociability REAL NOT NULL DEFAULT 0.5,
    aggression REAL NOT NULL DEFAULT 0.5,
    honesty REAL NOT NULL DEFAULT 0.5,
    primary_goal TEXT NOT NULL DEFAULT 'become_chief',
    secondary_goals TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    text TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 0.5,
    emotion TEXT NOT NULL DEFAULT 'neutral',
    embedding BLOB,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE INDEX IF NOT EXISTS idx_memories_agent_tick ON memories(agent_id, tick DESC);

CREATE TABLE IF NOT EXISTS relationships (
    a_id TEXT NOT NULL,
    b_id TEXT NOT NULL,
    trust REAL NOT NULL DEFAULT 0.5,
    respect REAL NOT NULL DEFAULT 0.5,
    fear REAL NOT NULL DEFAULT 0.0,
    friendship REAL NOT NULL DEFAULT 0.3,
    PRIMARY KEY (a_id, b_id),
    FOREIGN KEY (a_id) REFERENCES agents(id),
    FOREIGN KEY (b_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tick INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    type TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'unknown',
    target TEXT,
    payload TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE INDEX IF NOT EXISTS idx_actions_tick ON actions(tick);

CREATE TABLE IF NOT EXISTS world_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    tick INTEGER NOT NULL DEFAULT 0,
    json_blob TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tick_snapshots (
    tick INTEGER PRIMARY KEY,
    json_blob TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS world_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tick INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_world_events_tick ON world_events(tick);

CREATE TABLE IF NOT EXISTS llm_traces (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    prompt TEXT NOT NULL,
    response TEXT NOT NULL,
    thinking TEXT NOT NULL DEFAULT '',
    latency_ms REAL,
    token_usage INTEGER,
    action_type TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_llm_traces_agent_tick ON llm_traces(agent_id, tick);
