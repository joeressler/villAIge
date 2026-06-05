import { useCallback, useEffect, useState } from "react";
import {
  connectWebSocket,
  fetchAgent,
  fetchEvents,
  fetchRelationships,
  fetchState,
  startSimulation,
  stepSimulation,
  stopSimulation,
} from "./api";
import AgentInspector from "./components/AgentInspector";
import Dashboard from "./components/Dashboard";
import RelationshipGraph from "./components/RelationshipGraph";
import Timeline from "./components/Timeline";

interface SimState {
  tick: number;
  population: number;
  chief_name?: string;
  resources: Record<string, number>;
  election_state: { active: boolean; candidates: string[]; days_remaining: number };
  running: boolean;
  agents: Array<{ id: string; name: string; role: string; stats: { wealth: number; reputation: number } }>;
}

export default function App() {
  const [state, setState] = useState<SimState | null>(null);
  const [events, setEvents] = useState<Array<{ id: number; tick: number; event_type: string; description: string }>>([]);
  const [liveActions, setLiveActions] = useState<Array<{ agent_name?: string; description?: string; action?: { type: string } }>>([]);
  const [relationships, setRelationships] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [agentDetail, setAgentDetail] = useState(null);

  const refresh = useCallback(async () => {
    const [s, ev, rel] = await Promise.all([
      fetchState(),
      fetchEvents(30),
      fetchRelationships(),
    ]);
    setState(s);
    setEvents(ev);
    setRelationships(rel);
  }, []);

  useEffect(() => {
    refresh();
    const ws = connectWebSocket((data: unknown) => {
      const msg = data as { type?: string; actions?: typeof liveActions };
      if (msg.type === "tick_update") {
        refresh();
        if (msg.actions) setLiveActions(msg.actions);
      }
      if (msg.type === "election") {
        refresh();
      }
    });
    const interval = setInterval(refresh, 5000);
    return () => {
      ws.close();
      clearInterval(interval);
    };
  }, [refresh]);

  useEffect(() => {
    if (selectedAgent) {
      fetchAgent(selectedAgent).then(setAgentDetail);
    }
  }, [selectedAgent, state?.tick]);

  const handleStart = async () => {
    await startSimulation();
    refresh();
  };
  const handleStop = async () => {
    await stopSimulation();
    refresh();
  };
  const handleStep = async () => {
    const result = await stepSimulation();
    if (result.actions) setLiveActions(result.actions);
    refresh();
  };

  if (!state) {
    return <div className="loading">Loading village simulation...</div>;
  }

  return (
    <div className="app">
      <header>
        <h1>🏘️ Emergent Village Simulation</h1>
        <p className="subtitle">SQLite + LangGraph multi-agent society</p>
      </header>

      <Dashboard
        state={state}
        onStart={handleStart}
        onStop={handleStop}
        onStep={handleStep}
      />

      <div className="main-grid">
        <RelationshipGraph agents={state.agents} relationships={relationships} />
        <Timeline events={events} liveActions={liveActions} currentTick={state.tick} />
      </div>

      <AgentInspector
        agents={state.agents}
        selectedId={selectedAgent}
        detail={agentDetail}
        onSelect={setSelectedAgent}
      />

      <style>{`
        .app { max-width: 1200px; margin: 0 auto; padding: 1.5rem; display: flex; flex-direction: column; gap: 1.25rem; }
        header h1 { font-size: 1.5rem; font-weight: 700; }
        .subtitle { color: var(--muted); font-size: 0.875rem; margin-top: 0.25rem; }
        .main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .loading { padding: 4rem; text-align: center; color: var(--muted); }
        @media (max-width: 900px) { .main-grid { grid-template-columns: 1fr; } }
      `}</style>
    </div>
  );
}
