const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function fetchState() {
  const res = await fetch(`${API_BASE}/simulation/state`);
  return res.json();
}

export async function startSimulation() {
  const res = await fetch(`${API_BASE}/simulation/start`, { method: "POST" });
  return res.json();
}

export async function stopSimulation() {
  const res = await fetch(`${API_BASE}/simulation/stop`, { method: "POST" });
  return res.json();
}

export async function resetSimulation() {
  const res = await fetch(`${API_BASE}/simulation/reset`, { method: "POST" });
  return res.json();
}

export async function stepSimulation() {
  const res = await fetch(`${API_BASE}/simulation/step`, { method: "POST" });
  return res.json();
}

export async function fetchAgent(id: string) {
  const res = await fetch(`${API_BASE}/agent/${id}`);
  return res.json();
}

export async function fetchTick(tick: number) {
  const res = await fetch(`${API_BASE}/tick/${tick}`);
  return res.json();
}

export async function fetchEvents(limit = 50) {
  const res = await fetch(`${API_BASE}/events?limit=${limit}`);
  return res.json();
}

export async function fetchRelationships() {
  const res = await fetch(`${API_BASE}/relationships`);
  return res.json();
}

export async function fetchErrors(limit = 100) {
  const res = await fetch(`${API_BASE}/observability/errors?limit=${limit}`);
  return res.json();
}

export async function fetchLogs(limit = 100, minLevel = "INFO") {
  const res = await fetch(
    `${API_BASE}/observability/logs?limit=${limit}&min_level=${minLevel}`
  );
  return res.json();
}

export interface MetricsDashboard {
  enabled: boolean;
  from: string;
  to: string;
  summary: {
    llm_calls: number;
    avg_latency_ms: number;
    total_tokens: number;
    total_cost_usd: number;
    decision_errors: number;
  };
  llm_volume: Array<{ hour: string; count: number }>;
  latency_by_model: Array<{ model: string; p50_ms: number; p95_ms: number }>;
  tokens_cost_by_model: Array<{ model: string; tokens: number; cost_usd: number }>;
  errors_over_time: Array<{ hour: string; count: number }>;
  activity_by_observation: Array<{ name: string; count: number }>;
  action_mix: Array<{ action_type: string; count: number; pct: number }>;
  top_agents_by_action: Record<
    string,
    Array<{ agent_id: string; agent_name: string; count: number }>
  >;
  error: string | null;
}

export async function fetchMetricsDashboard(hours = 24): Promise<MetricsDashboard> {
  const res = await fetch(`${API_BASE}/observability/metrics/dashboard?hours=${hours}`);
  return res.json();
}

export interface TickProfileResponse {
  summary: {
    enabled: boolean;
    ticks_sampled: number;
    avg_total_ms: number;
    avg_phases_ms: Record<string, number>;
    avg_phases_pct?: Record<string, number>;
    avg_per_agent_ms: Record<string, number>;
  };
  recent_ticks: Array<{
    tick: number;
    total_ms: number;
    population: number;
    phases_ms: Record<string, number>;
    phases_pct: Record<string, number>;
    per_agent_avg_ms: Record<string, number>;
    agents: Array<{
      agent_id: string;
      total_ms: number;
      phases_ms: Record<string, number>;
    }>;
  }>;
}

export async function fetchTickProfile(limit = 10): Promise<TickProfileResponse> {
  const res = await fetch(`${API_BASE}/observability/profile?limit=${limit}`);
  return res.json();
}

export function connectWebSocket(onMessage: (data: unknown) => void) {
  const wsUrl = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws/live";
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch {
      /* ignore */
    }
  };
  ws.onopen = () => {
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 30000);
    ws.onclose = () => clearInterval(ping);
  };
  return ws;
}
