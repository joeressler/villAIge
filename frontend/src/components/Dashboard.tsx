import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

interface Props {
  state: {
    tick: number;
    population: number;
    chief_name?: string;
    resources: Record<string, number>;
    election_state: { active: boolean; candidates: string[]; days_remaining: number };
    running: boolean;
    agents: Array<{ id: string; name: string; stats: { wealth: number; reputation: number } }>;
  };
  onStart: () => void;
  onStop: () => void;
  onStep: () => void;
}

export default function Dashboard({ state, onStart, onStop, onStep }: Props) {
  const resourceData = Object.entries(state.resources || {}).map(([name, value]) => ({
    name,
    value,
  }));

  const wealthData = (state.agents || [])
    .sort((a, b) => b.stats.wealth - a.stats.wealth)
    .slice(0, 8)
    .map((a) => ({ name: a.name, wealth: a.stats.wealth, reputation: a.stats.reputation }));

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
      </div>

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
          <h3>Wealth & Reputation (Top 8)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={wealthData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3a4f" />
              <XAxis dataKey="name" stroke="#8b9cb3" tick={{ fontSize: 10 }} />
              <YAxis stroke="#8b9cb3" />
              <Tooltip
                contentStyle={{ background: "#1a2332", border: "1px solid #2d3a4f" }}
              />
              <Bar dataKey="wealth" fill="#feca57" radius={[4, 4, 0, 0]} />
              <Bar dataKey="reputation" fill="#4ecdc4" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <style>{`
        .dashboard { display: flex; flex-direction: column; gap: 1rem; }
        .controls { display: flex; gap: 0.5rem; align-items: center; }
        .status { margin-left: auto; font-size: 0.8rem; color: var(--muted); }
        .status.live { color: var(--accent); }
        .stats-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 0.75rem;
        }
        .stat-card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 1rem;
        }
        .stat-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; }
        .stat-value { font-size: 1.5rem; font-weight: 700; margin-top: 0.25rem; }
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
