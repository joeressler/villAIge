import { useCallback, useEffect, useRef, useState } from "react";
import {
  connectWebSocket,
  fetchAgent,
  fetchEvents,
  fetchRelationships,
  fetchState,
  resetSimulation,
  startSimulation,
  stepSimulation,
  stopSimulation,
} from "./api";
import AgentInspector from "./components/AgentInspector";
import Dashboard from "./components/Dashboard";
import ErrorFeedLogs from "./components/ErrorFeedLogs";
import RelationshipGraph from "./components/RelationshipGraph";
import Timeline from "./components/Timeline";

interface SimState {
  tick: number;
  population: number;
  chief?: string;
  chief_name?: string;
  resources: Record<string, number>;
  threat?: { level: string; message: string; food_days_remaining: number };
  election_state: { active: boolean; candidates: string[]; days_remaining: number };
  election_ballot_tally?: Record<string, number>;
  election_candidate_names?: Record<string, string>;
  election_standing_weights?: { wealth: number; reputation: number };
  running: boolean;
  agents: Array<{
    id: string;
    name: string;
    role: string;
    standing?: number;
    wealth_rank?: number;
    reputation_rank?: number;
    standing_wealth_contrib?: number;
    standing_reputation_contrib?: number;
    stats: { wealth: number; reputation: number };
  }>;
}

export default function App() {
  const [state, setState] = useState<SimState | null>(null);
  const [events, setEvents] = useState<Array<{ id: number; tick: number; event_type: string; description: string }>>([]);
  const [liveActions, setLiveActions] = useState<
    Array<{
      tick?: number;
      agent_id?: string;
      agent_name?: string;
      description?: string;
      type?: string;
      category?: string;
      action?: { type: string; category?: string };
    }>
  >([]);
  const [tickProgress, setTickProgress] = useState<{
    tick: number;
    index: number;
    total: number;
    agentName?: string;
    phase?: "deciding" | "done";
  } | null>(null);
  const [relationships, setRelationships] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const selectedAgentRef = useRef<string | null>(null);
  selectedAgentRef.current = selectedAgent;
  const [agentDetail, setAgentDetail] = useState(null);
  const [activeTab, setActiveTab] = useState<"simulation" | "errors">("simulation");
  const [liveErrors, setLiveErrors] = useState<
    Array<{
      id: number;
      timestamp: string;
      source: string;
      error_type: string;
      message: string;
      tick?: number;
    }>
  >([]);

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
      const msg = data as {
        type?: string;
        actions?: typeof liveActions;
        action?: (typeof liveActions)[number];
        tick?: number;
        index?: number;
        total?: number;
        agent_id?: string;
        agent_name?: string;
        error_type?: string;
        message?: string;
        total_agents?: number;
      };
      if (msg.type === "tick_started" && msg.tick != null) {
        setLiveActions([]);
        setTickProgress({
          tick: msg.tick,
          index: 0,
          total: msg.total_agents ?? 0,
          phase: "deciding",
        });
      }
      if (msg.type === "agent_deciding" && msg.tick != null) {
        setTickProgress({
          tick: msg.tick,
          index: msg.index ?? 0,
          total: msg.total ?? 0,
          agentName: msg.agent_name,
          phase: "deciding",
        });
      }
      if (msg.type === "action_taken" && msg.action) {
        setLiveActions((prev) => [msg.action!, ...prev].slice(0, 40));
        setTickProgress((prev) =>
          prev && msg.tick != null
            ? {
                ...prev,
                tick: msg.tick,
                index: msg.index ?? prev.index,
                total: msg.total ?? prev.total,
                agentName: msg.action?.agent_name,
                phase: "done",
              }
            : prev
        );
        refresh();
        const activeAgent = selectedAgentRef.current;
        if (activeAgent && msg.action.agent_id === activeAgent) {
          fetchAgent(activeAgent).then(setAgentDetail);
        }
      }
      if (msg.type === "tick_update") {
        refresh();
        if (msg.actions) setLiveActions(msg.actions);
        setTickProgress(null);
      }
      if (msg.type === "election" || msg.type === "simulation_reset") {
        refresh();
      }
      if (msg.type === "simulation_error") {
        setLiveErrors((prev) => [
          {
            id: Date.now(),
            timestamp: new Date().toISOString(),
            source: "simulation",
            error_type: msg.error_type ?? "Error",
            message: msg.message ?? "Simulation tick failed",
            tick: msg.tick,
          },
          ...prev,
        ].slice(0, 20));
      }
      if (msg.type === "simulation_reset") {
        setLiveErrors([]);
        setTickProgress(null);
        setLiveActions([]);
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
  const handleReset = async () => {
    if (!window.confirm("Reset the simulation? All agents, history, and memories will be cleared.")) {
      return;
    }
    await resetSimulation();
    setLiveActions([]);
    setLiveErrors([]);
    setSelectedAgent(null);
    setAgentDetail(null);
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
        tickProgress={tickProgress}
        onStart={handleStart}
        onStop={handleStop}
        onStep={handleStep}
        onReset={handleReset}
      />

      <nav className="main-tabs">
        <button
          className={activeTab === "simulation" ? "active" : ""}
          onClick={() => setActiveTab("simulation")}
        >
          Simulation
        </button>
        <button
          className={activeTab === "errors" ? "active" : ""}
          onClick={() => setActiveTab("errors")}
        >
          Errors & Logs
          {liveErrors.length > 0 && <span className="badge">{liveErrors.length}</span>}
        </button>
      </nav>

      {activeTab === "simulation" ? (
        <>
          <div className="main-grid">
            <RelationshipGraph agents={state.agents} relationships={relationships} />
            <Timeline events={events} liveActions={liveActions} currentTick={state.tick} />
          </div>

          <AgentInspector
            agents={state.agents}
            selectedId={selectedAgent}
            chiefId={state.chief}
            currentTick={state.tick}
            detail={agentDetail}
            onSelect={setSelectedAgent}
          />
        </>
      ) : (
        <ErrorFeedLogs liveErrors={liveErrors} />
      )}

      <style>{`
        .app { max-width: 1200px; margin: 0 auto; padding: 1.5rem; display: flex; flex-direction: column; gap: 1.25rem; }
        header h1 { font-size: 1.5rem; font-weight: 700; }
        .subtitle { color: var(--muted); font-size: 0.875rem; margin-top: 0.25rem; }
        .main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .main-tabs {
          display: flex;
          gap: 0.5rem;
          border-bottom: 1px solid var(--border);
          padding-bottom: 0.5rem;
        }
        .main-tabs button {
          background: transparent;
          border: none;
          border-bottom: 2px solid transparent;
          border-radius: 0;
          padding: 0.5rem 1rem;
          color: var(--muted);
          font-weight: 500;
        }
        .main-tabs button:hover { color: var(--text); }
        .main-tabs button.active {
          color: var(--accent);
          border-bottom-color: var(--accent);
        }
        .main-tabs .badge {
          margin-left: 0.35rem;
          background: #e74c3c;
          color: white;
          font-size: 0.65rem;
          padding: 0.1rem 0.4rem;
          border-radius: 999px;
          font-weight: 700;
        }
        .loading { padding: 4rem; text-align: center; color: var(--muted); }
        @media (max-width: 900px) { .main-grid { grid-template-columns: 1fr; } }
      `}</style>
    </div>
  );
}
