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
