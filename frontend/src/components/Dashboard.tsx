import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
  Legend,
} from "recharts";

interface AgentStanding {
  id: string;
  name: string;
  standing?: number;
  wealth_rank?: number;
  reputation_rank?: number;
  standing_wealth_contrib?: number;
  standing_reputation_contrib?: number;
  stats: { wealth: number; reputation: number };
}

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
    election_standing_weights?: { wealth: number; reputation: number };
    running: boolean;
    agents: AgentStanding[];
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

const WEALTH_COLOR = "#feca57";
const REPUTATION_COLOR = "#4ecdc4";

function pct(value: number | undefined): number {
  return Math.round((value ?? 0) * 100);
}

function selectLeadershipAgents(agents: AgentStanding[], candidateIds: string[]): AgentStanding[] {
  const sorted = [...agents].sort((a, b) => (b.standing ?? 0) - (a.standing ?? 0));
  const candidateSet = new Set(candidateIds);
  const seen = new Set<string>();
  const rows: AgentStanding[] = [];

  for (const agent of sorted) {
    if (candidateSet.has(agent.id) && !seen.has(agent.id)) {
      rows.push(agent);
      seen.add(agent.id);
    }
  }
  for (const agent of sorted) {
    if (rows.length >= 8) break;
    if (!seen.has(agent.id)) {
      rows.push(agent);
      seen.add(agent.id);
    }
  }
  return rows.sort((a, b) => (b.standing ?? 0) - (a.standing ?? 0));
}

function StandingTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: Record<string, unknown> }>;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as {
    name: string;
    standingPct: number;
    wealthRankPct: number;
    repRankPct: number;
    wealthScore: number;
    repScore: number;
    wealth: number;
    reputation: number;
    votes?: number;
    isChief?: boolean;
    isCandidate?: boolean;
  };
  return (
    <div className="standing-tooltip">
      <strong>{row.name}</strong>
      {row.isChief && <span className="standing-badge chief">Chief</span>}
      {row.isCandidate && <span className="standing-badge candidate">Candidate</span>}
      <div className="standing-tooltip-line">
        Election standing: <strong>{row.standingPct}%</strong>
      </div>
      <div className="standing-tooltip-line">
        Wealth rank {row.wealthRankPct}% → +{row.wealthScore}% ({row.wealth} gold)
      </div>
      <div className="standing-tooltip-line">
        Reputation rank {row.repRankPct}% → +{row.repScore}% ({row.reputation} rep)
      </div>
      {row.votes !== undefined && (
        <div className="standing-tooltip-line">Ballots cast: {row.votes}</div>
      )}
    </div>
  );
}

export default function Dashboard({ state, tickProgress, onStart, onStop, onStep, onReset }: Props) {
  const resourceData = Object.entries(state.resources || {}).map(([name, value]) => ({
    name,
    value,
  }));

  const weights = state.election_standing_weights ?? { wealth: 0.5, reputation: 0.5 };
  const wealthWeightPct = Math.round(weights.wealth * 100);
  const repWeightPct = Math.round(weights.reputation * 100);
  const candidateIds = state.election_state?.candidates ?? [];
  const ballotTally = state.election_ballot_tally ?? {};

  const leadershipData = selectLeadershipAgents(state.agents || [], candidateIds).map((agent) => ({
    name: agent.name,
    standingPct: pct(agent.standing),
    wealthRankPct: pct(agent.wealth_rank),
    repRankPct: pct(agent.reputation_rank),
    wealthScore: pct(agent.standing_wealth_contrib),
    repScore: pct(agent.standing_reputation_contrib),
    wealth: agent.stats.wealth,
    reputation: agent.stats.reputation,
    votes: ballotTally[agent.id],
    isChief: agent.id === state.chief,
    isCandidate: candidateIds.includes(agent.id),
  }));

  const threat = state.threat ?? { level: "stable", message: "Unknown", food_days_remaining: 0 };
  const threatColor = THREAT_COLORS[threat.level] ?? "#8b9cb3";

  const tallyEntries = Object.entries(ballotTally).map(([candidateId, votes]) => ({
    name: state.election_candidate_names?.[candidateId] ?? candidateId.slice(0, 6),
    votes,
  }));

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
        <div className="chart-card leadership-card">
          <h3>Election Standing</h3>
          <p className="chart-caption">
            Standing = {wealthWeightPct}% wealth rank + {repWeightPct}% reputation rank
            (village percentiles). Picks top candidates, breaks ties, and weights abstainer
            votes (60% standing + 40% trust).
          </p>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={leadershipData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3a4f" />
              <XAxis dataKey="name" stroke="#8b9cb3" tick={{ fontSize: 10 }} />
              <YAxis
                stroke="#8b9cb3"
                domain={[0, 100]}
                tickFormatter={(value) => `${value}%`}
              />
              <Tooltip content={<StandingTooltip />} />
              <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
              <Bar
                dataKey="wealthScore"
                name={`Wealth (${wealthWeightPct}%)`}
                stackId="standing"
                fill={WEALTH_COLOR}
                radius={[0, 0, 0, 0]}
              >
                {leadershipData.map((entry) => (
                  <Cell
                    key={`${entry.name}-wealth`}
                    fill={entry.isChief ? "#e6b800" : entry.isCandidate ? "#d4a017" : WEALTH_COLOR}
                    opacity={entry.isCandidate || entry.isChief ? 1 : 0.75}
                  />
                ))}
              </Bar>
              <Bar
                dataKey="repScore"
                name={`Reputation (${repWeightPct}%)`}
                stackId="standing"
                fill={REPUTATION_COLOR}
                radius={[4, 4, 0, 0]}
              >
                {leadershipData.map((entry) => (
                  <Cell
                    key={`${entry.name}-rep`}
                    fill={entry.isChief ? "#3dbdb5" : entry.isCandidate ? "#45a29e" : REPUTATION_COLOR}
                    opacity={entry.isCandidate || entry.isChief ? 1 : 0.75}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="standing-legend-row">
            <span className="standing-legend-item">
              <span className="dot chief" /> Chief
            </span>
            <span className="standing-legend-item">
              <span className="dot candidate" /> Candidate
            </span>
            {state.election_state?.active && (
              <span className="standing-legend-item muted">
                Candidates always shown during elections
              </span>
            )}
          </div>
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
        .chart-caption {
          font-size: 0.72rem;
          color: var(--muted);
          line-height: 1.4;
          margin: -0.25rem 0 0.75rem;
        }
        .standing-legend-row {
          display: flex;
          flex-wrap: wrap;
          gap: 0.75rem;
          margin-top: 0.5rem;
          font-size: 0.72rem;
          color: var(--muted);
        }
        .standing-legend-item { display: inline-flex; align-items: center; gap: 0.35rem; }
        .standing-legend-item .dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          display: inline-block;
        }
        .standing-legend-item .dot.chief { background: #feca57; }
        .standing-legend-item .dot.candidate { background: #4ecdc4; }
        .standing-legend-item.muted { opacity: 0.85; }
        .standing-tooltip {
          background: #1a2332;
          border: 1px solid #2d3a4f;
          border-radius: 6px;
          padding: 0.6rem 0.75rem;
          font-size: 0.75rem;
          line-height: 1.45;
          max-width: 260px;
        }
        .standing-tooltip strong { color: #e8eef5; }
        .standing-tooltip-line { color: #8b9cb3; margin-top: 0.25rem; }
        .standing-badge {
          display: inline-block;
          margin-left: 0.35rem;
          padding: 0.05rem 0.35rem;
          border-radius: 4px;
          font-size: 0.65rem;
          text-transform: uppercase;
        }
        .standing-badge.chief { background: rgba(254, 202, 87, 0.2); color: #feca57; }
        .standing-badge.candidate { background: rgba(78, 205, 196, 0.2); color: #4ecdc4; }
        @media (max-width: 900px) {
          .stats-grid { grid-template-columns: repeat(2, 1fr); }
          .charts-row { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}
