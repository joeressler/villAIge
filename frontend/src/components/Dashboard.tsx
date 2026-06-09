import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from "recharts";

interface Props {
  tickProgress?: {
    tick: number;
    index: number;
    total: number;
    agentName?: string;
    phase?: "deciding" | "done";
  } | null;
  state: {
    tick: number;
    population: number;
    chief?: string;
    chief_name?: string;
    resources: Record<string, number>;
    threat?: { level: string; message: string; food_days_remaining: number };
    election_state: {
      active: boolean;
      candidates: string[];
      days_remaining: number;
    };
    election_candidate_names?: Record<string, string>;
    election_ballot_tally?: Record<string, number>;
    running: boolean;
    agents: Array<{
      id: string;
      name: string;
      standing?: number;
      stats: { wealth: number; reputation: number };
    }>;
  };
  onStart: () => void;
  onStop: () => void;
  onStep: () => void;
  onReset: () => void;
}

const THREAT_COLORS: Record<string, string> = {
  stable: "#4ecdc4",
  strained: "#feca57",
  critical: "#ff9f43",
  crisis: "#e74c3c",
};

export default function Dashboard({ state, tickProgress, onStart, onStop, onStep, onReset }: Props) {
  const resourceData = Object.entries(state.resources || {}).map(([name, value]) => ({
    name,
    value,
  }));

  const leadershipData = (state.agents || [])
    .sort((a, b) => (b.standing ?? 0) - (a.standing ?? 0))
    .slice(0, 8)
    .map((a) => ({
      name: a.name,
      standing: Math.round((a.standing ?? 0) * 100),
      wealth: a.stats.wealth,
      reputation: a.stats.reputation,
      isChief: a.id === state.chief,
      isCandidate: state.election_state?.candidates?.includes(a.id),
    }));

  const threat = state.threat ?? { level: "stable", message: "Unknown", food_days_remaining: 0 };
  const threatColor = THREAT_COLORS[threat.level] ?? "#8b9cb3";

  const tallyEntries = Object.entries(state.election_ballot_tally ?? {}).map(
    ([candidateId, votes]) => ({
      name: state.election_candidate_names?.[candidateId] ?? candidateId.slice(0, 6),
      votes,
    })
  );

  return (
    <div className="dashboard">
      <div className="controls">
        <button className="primary" onClick={onStart} disabled={state.running}>
          Start
        </button>
        <button className="danger" onClick={onStop} disabled={!state.running}>
          Stop
        </button>
        <button onClick={onStep}>Step</button>
        <button className="reset" onClick={onReset} disabled={state.running}>
          Reset
        </button>
        {tickProgress && (
          <span className="tick-progress">
            T{tickProgress.tick} ·{" "}
            {tickProgress.phase === "deciding" && tickProgress.agentName
              ? `${tickProgress.agentName} deciding (${tickProgress.index}/${tickProgress.total})…`
              : `Action ${tickProgress.index}/${tickProgress.total}`}
          </span>
        )}
        <span className={`status ${state.running ? "live" : ""}`}>
          {state.running ? "● LIVE" : "○ STOPPED"}
        </span>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Tick</div>
          <div className="stat-value">{state.tick}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Population</div>
          <div className="stat-value">{state.population}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Chief</div>
          <div className="stat-value">{state.chief_name || "None"}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Election</div>
          <div className="stat-value">
            {state.election_state?.active
              ? `Day ${state.election_state.days_remaining}`
              : "—"}
          </div>
        </div>
        <div className="stat-card threat-card" style={{ borderColor: threatColor }}>
          <div className="stat-label">Threat</div>
          <div className="stat-value" style={{ color: threatColor, fontSize: "1.1rem" }}>
            {threat.level.toUpperCase()}
          </div>
          <div className="stat-sub">{threat.message}</div>
        </div>
      </div>

      {tallyEntries.length > 0 && (
        <div className="chart-card tally-card">
          <h3>Election Ballots</h3>
          <div className="tally-row">
            {tallyEntries.map((entry) => (
              <span key={entry.name} className="tally-chip">
                {entry.name}: {entry.votes}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="charts-row">
        <div className="chart-card">
          <h3>Village Resources</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={resourceData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3a4f" />
              <XAxis dataKey="name" stroke="#8b9cb3" />
              <YAxis stroke="#8b9cb3" />
              <Tooltip
                contentStyle={{ background: "#1a2332", border: "1px solid #2d3a4f" }}
              />
              <Bar dataKey="value" fill="#4ecdc4" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-card">
          <h3>Leadership Standings (Top 8)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={leadershipData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3a4f" />
              <XAxis dataKey="name" stroke="#8b9cb3" tick={{ fontSize: 10 }} />
              <YAxis stroke="#8b9cb3" />
              <Tooltip
                contentStyle={{ background: "#1a2332", border: "1px solid #2d3a4f" }}
              />
              <Bar dataKey="standing" name="Standing %" radius={[4, 4, 0, 0]}>
                {leadershipData.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={entry.isChief ? "#feca57" : entry.isCandidate ? "#4ecdc4" : "#6c7a89"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <style>{`
        .dashboard { display: flex; flex-direction: column; gap: 1rem; }
        .controls { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
        .controls button.reset { border-color: var(--muted); color: var(--muted); }
        .controls button.reset:hover:not(:disabled) { border-color: #e74c3c; color: #e74c3c; }
        .status { margin-left: auto; font-size: 0.8rem; color: var(--muted); }
        .status.live { color: var(--accent); }
        .stats-grid {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 0.75rem;
        }
        .stat-card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 1rem;
        }
        .tick-progress {
          font-size: 0.8rem;
          color: var(--accent);
          font-family: monospace;
          padding: 0.35rem 0.75rem;
          background: rgba(78, 205, 196, 0.08);
          border: 1px solid rgba(78, 205, 196, 0.25);
          border-radius: 6px;
        }
        .stat-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; }
        .stat-value { font-size: 1.5rem; font-weight: 700; margin-top: 0.25rem; }
        .stat-sub { font-size: 0.7rem; color: var(--muted); margin-top: 0.35rem; line-height: 1.3; }
        .tally-card { padding: 0.75rem 1rem; }
        .tally-row { display: flex; flex-wrap: wrap; gap: 0.5rem; }
        .tally-chip {
          background: #1a2332;
          border: 1px solid var(--border);
          border-radius: 999px;
          padding: 0.25rem 0.75rem;
          font-size: 0.8rem;
        }
        .charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .chart-card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 1rem;
        }
        .chart-card h3 { font-size: 0.875rem; color: var(--muted); margin-bottom: 0.5rem; }
        @media (max-width: 900px) {
          .stats-grid { grid-template-columns: repeat(2, 1fr); }
          .charts-row { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}
