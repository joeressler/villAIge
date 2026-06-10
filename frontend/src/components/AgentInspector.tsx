import { useMemo, useState } from "react";
import RelationshipHistoryChart from "./RelationshipHistoryChart";

interface Trace {
  tick: number;
  action_type: string;
  latency_ms: number;
  thinking?: string;
  response?: string;
  response_path?: string;
}

interface RelationshipRow {
  other_id?: string;
  other_name?: string;
  other_role?: string;
  trust: number;
  respect: number;
  fear: number;
  friendship: number;
}

interface Props {
  agents: Array<{ id: string; name: string; role: string; stats: Record<string, number> }>;
  selectedId: string | null;
  chiefId?: string | null;
  currentTick: number;
  detail: {
    agent?: Record<string, unknown>;
    relationships?: RelationshipRow[];
    memories?: Array<{ tick: number; text: string; importance: number; emotion: string }>;
    traces?: Trace[];
  } | null;
  onSelect: (id: string) => void;
}

function formatLabel(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatGoal(goal: string): string {
  return goal.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function metricBar(value: number, tone: "positive" | "neutral" | "negative" = "neutral") {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <span className={`metric-bar tone-${tone}`}>
      <span className="metric-bar-fill" style={{ width: `${pct}%` }} />
      <span className="metric-bar-value">{value.toFixed(2)}</span>
    </span>
  );
}

export default function AgentInspector({
  agents,
  selectedId,
  chiefId,
  currentTick,
  detail,
  onSelect,
}: Props) {
  const [expandedTrace, setExpandedTrace] = useState<number | null>(null);
  const agent = detail?.agent as Record<string, unknown> | undefined;
  const personality = agent?.personality as Record<string, number> | undefined;
  const stats = agent?.stats as Record<string, number> | undefined;
  const goals = agent?.goals as { primary?: string; secondary?: string[] } | undefined;
  const traces = detail?.traces ?? [];

  const relationships = useMemo(() => {
    const rows = detail?.relationships ?? [];
    return [...rows].sort((a, b) => b.friendship - a.friendship || b.trust - a.trust);
  }, [detail?.relationships]);

  const resolveOtherName = (row: RelationshipRow, index: number) => {
    if (row.other_name) return row.other_name;
    if (row.other_id) {
      const match = agents.find((a) => a.id === row.other_id);
      if (match) return match.name;
      return row.other_id;
    }
    return `Villager ${index + 1}`;
  };

  const chartNeighbors = useMemo(
    () =>
      relationships.map((r) => ({
        other_id: r.other_id,
        other_name: r.other_name,
        trust: r.trust,
        respect: r.respect,
        fear: r.fear,
        friendship: r.friendship,
      })),
    [relationships]
  );

  return (
    <div className="inspector">
      <h3>Agent Inspector</h3>
      <div className="agent-list">
        {agents.map((a) => (
          <button
            key={a.id}
            className={`agent-btn ${selectedId === a.id ? "active" : ""}`}
            onClick={() => onSelect(a.id)}
          >
            <span className="name">{a.name}</span>
            <span className="role">{a.role}</span>
          </button>
        ))}
      </div>

      {!selectedId && (
        <p className="inspector-hint">Select an agent above to view stats, relationships, and traces.</p>
      )}

      {detail && agent && (
        <div className="detail">
          <div className="detail-header">
            <div>
              <h4>{String(agent.name)}</h4>
              <p className="detail-subtitle">
                {String(agent.role)}
                {goals?.primary ? ` · Goal: ${formatGoal(goals.primary)}` : ""}
              </p>
            </div>
            {chiefId && agent.id === chiefId && <span className="chief-badge">Chief</span>}
          </div>

          <div className="detail-grid">
            <div>
              <strong>Stats</strong>
              <ul>
                {stats &&
                  Object.entries(stats).map(([k, v]) => (
                    <li key={k}>
                      <span className="stat-label">{formatLabel(k)}</span>
                      <span className="stat-value">{v}</span>
                    </li>
                  ))}
              </ul>
            </div>
            <div>
              <strong>Personality</strong>
              <ul>
                {personality &&
                  Object.entries(personality).map(([k, v]) => (
                    <li key={k}>
                      <span className="stat-label">{formatLabel(k)}</span>
                      <span className="stat-value">{Number(v).toFixed(2)}</span>
                    </li>
                  ))}
              </ul>
            </div>
          </div>

          <div className="section">
            <strong>Relationship over time</strong>
            {selectedId && (
              <RelationshipHistoryChart
                agentId={selectedId}
                neighbors={chartNeighbors}
                currentTick={currentTick}
              />
            )}
          </div>

          <div className="section">
            <strong>Relationships ({relationships.length})</strong>
            {relationships.length === 0 ? (
              <p className="section-empty">No relationships recorded yet.</p>
            ) : (
              <ul className="relationship-list">
                {relationships.map((r, i) => (
                  <li key={r.other_id ?? i} className="relationship-row">
                    <div className="relationship-name">
                      <span className="other-name">{resolveOtherName(r, i)}</span>
                      {r.other_role && <span className="other-role">{r.other_role}</span>}
                    </div>
                    <div className="relationship-metrics">
                      <div className="relationship-metric">
                        <span className="metric-label">Trust</span>
                        {metricBar(r.trust, "positive")}
                      </div>
                      <div className="relationship-metric">
                        <span className="metric-label">Friendship</span>
                        {metricBar(r.friendship, "positive")}
                      </div>
                      <div className="relationship-metric">
                        <span className="metric-label">Respect</span>
                        {metricBar(r.respect, "neutral")}
                      </div>
                      <div className="relationship-metric">
                        <span className="metric-label">Fear</span>
                        {metricBar(r.fear, "negative")}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="section">
            <strong>Memories ({detail.memories?.length || 0})</strong>
            {(detail.memories?.length || 0) === 0 ? (
              <p className="section-empty">No memories yet.</p>
            ) : (
              <div className="memories">
                {(detail.memories || []).slice(0, 8).map((m, i) => (
                  <div key={i} className="memory">
                    <span className="mem-tick">T{m.tick}</span>
                    <span className={`emotion ${m.emotion}`}>{m.emotion}</span>
                    <span className="mem-importance" title={`Importance ${m.importance.toFixed(2)}`}>
                      {(m.importance * 100).toFixed(0)}%
                    </span>
                    <span className="mem-text">{m.text}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="section">
            <strong>Decision Traces ({traces.length})</strong>
            <div className="traces">
              {traces.length === 0 && (
                <p className="trace-empty">No decision traces yet.</p>
              )}
              {traces.slice(0, 10).map((t, i) => {
                const isOpen = expandedTrace === i;
                const hasThinking = Boolean(t.thinking?.trim());
                const pathLabel =
                  t.response_path === "structured"
                    ? "structured"
                    : t.response_path === "structured_fallback"
                      ? "fallback"
                      : null;
                return (
                  <div key={i} className="trace">
                    <button
                      className="trace-header"
                      onClick={() => setExpandedTrace(isOpen ? null : i)}
                    >
                      <span className="trace-tick">T{t.tick}</span>
                      <span className="trace-action">{t.action_type || "—"}</span>
                      <span className="trace-latency">
                        {t.latency_ms != null ? `${Math.round(t.latency_ms)}ms` : "—"}
                      </span>
                      {hasThinking && <span className="trace-badge">reasoning</span>}
                      {pathLabel && (
                        <span className={`trace-badge path-${pathLabel}`}>{pathLabel}</span>
                      )}
                      <span className="trace-chevron">{isOpen ? "▾" : "▸"}</span>
                    </button>
                    {isOpen && (
                      <div className="trace-body">
                        {hasThinking && (
                          <div className="trace-thinking">
                            <span className="trace-label">Thinking</span>
                            <pre>{t.thinking}</pre>
                          </div>
                        )}
                        {t.response && (
                          <div className="trace-response">
                            <span className="trace-label">Response</span>
                            <pre>{t.response.length > 400 ? `${t.response.slice(0, 400)}…` : t.response}</pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <style>{`
        .inspector h3 { font-size: 0.875rem; color: var(--muted); margin-bottom: 0.5rem; }
        .inspector-hint {
          font-size: 0.8rem;
          color: var(--muted);
          margin: 0 0 0.5rem;
          padding: 0.75rem 1rem;
          background: var(--surface);
          border: 1px dashed var(--border);
          border-radius: 8px;
        }
        .agent-list {
          display: flex;
          flex-wrap: wrap;
          gap: 0.5rem;
          margin-bottom: 1rem;
          max-height: 160px;
          overflow-y: auto;
        }
        .agent-btn {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          gap: 0.15rem;
          padding: 0.55rem 0.85rem;
          font-size: 0.875rem;
          line-height: 1.25;
          min-height: 2.75rem;
        }
        .agent-btn.active { border-color: var(--accent); background: #1e2d3d; }
        .name { font-weight: 600; font-size: 0.9rem; }
        .role { color: var(--muted); font-size: 0.78rem; }
        .detail { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }
        .detail-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 0.75rem;
          margin-bottom: 0.75rem;
        }
        .detail h4 { margin: 0; }
        .detail-subtitle { color: var(--muted); font-size: 0.75rem; margin-top: 0.2rem; }
        .chief-badge {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: #feca57;
          background: rgba(254, 202, 87, 0.12);
          border: 1px solid rgba(254, 202, 87, 0.35);
          border-radius: 999px;
          padding: 0.3rem 0.65rem;
          white-space: nowrap;
        }
        .detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }
        .detail ul { list-style: none; font-size: 0.8rem; }
        .detail li {
          display: flex;
          justify-content: space-between;
          gap: 0.5rem;
          padding: 0.15rem 0;
          color: var(--muted);
        }
        .stat-label { color: var(--text); }
        .stat-value { font-family: monospace; }
        .section { margin-top: 0.75rem; }
        .section strong { font-size: 0.8rem; display: block; margin-bottom: 0.35rem; }
        .section-empty {
          font-size: 0.75rem;
          color: var(--muted);
          margin: 0;
        }
        .relationship-list { list-style: none; display: flex; flex-direction: column; gap: 0.5rem; }
        .relationship-row {
          padding: 0.55rem 0.65rem;
          border: 1px solid var(--border);
          border-radius: 8px;
          background: rgba(0,0,0,0.12);
        }
        .relationship-name {
          display: flex;
          align-items: baseline;
          gap: 0.45rem;
          margin-bottom: 0.45rem;
        }
        .other-name { font-weight: 600; font-size: 0.82rem; }
        .other-role {
          font-size: 0.65rem;
          color: var(--muted);
          text-transform: capitalize;
        }
        .relationship-metrics {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.35rem 0.75rem;
        }
        .relationship-metric {
          display: grid;
          grid-template-columns: 4.5rem 1fr;
          gap: 0.35rem;
          align-items: center;
        }
        .metric-label {
          font-size: 0.72rem;
          color: var(--muted);
          text-transform: uppercase;
        }
        .metric-bar {
          position: relative;
          height: 1.25rem;
          border-radius: 999px;
          background: rgba(255,255,255,0.06);
          overflow: hidden;
        }
        .metric-bar-fill {
          position: absolute;
          inset: 0 auto 0 0;
          border-radius: 999px;
        }
        .metric-bar.tone-positive .metric-bar-fill { background: rgba(78, 205, 196, 0.55); }
        .metric-bar.tone-neutral .metric-bar-fill { background: rgba(116, 185, 255, 0.45); }
        .metric-bar.tone-negative .metric-bar-fill { background: rgba(231, 76, 60, 0.45); }
        .metric-bar-value {
          position: relative;
          z-index: 1;
          display: block;
          font-size: 0.72rem;
          line-height: 1.25rem;
          text-align: center;
          font-family: monospace;
        }
        .memories { display: flex; flex-direction: column; gap: 0.25rem; }
        .memory {
          font-size: 0.75rem;
          display: grid;
          grid-template-columns: 2.5rem 4rem 2.5rem 1fr;
          gap: 0.35rem;
          align-items: start;
        }
        .mem-tick { color: var(--muted); font-family: monospace; }
        .mem-importance { color: var(--muted); font-size: 0.65rem; font-family: monospace; }
        .mem-text { line-height: 1.35; }
        .emotion { font-size: 0.65rem; text-transform: uppercase; }
        .emotion.fear, .emotion.anger { color: var(--accent2); }
        .emotion.joy, .emotion.hope { color: var(--accent); }
        .traces { display: flex; flex-direction: column; gap: 0.25rem; }
        .trace-empty { font-size: 0.75rem; color: var(--muted); margin: 0; }
        .trace { border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
        .trace-header {
          display: grid;
          grid-template-columns: 2.5rem 1fr 3.5rem auto 1rem;
          gap: 0.35rem;
          align-items: center;
          width: 100%;
          padding: 0.35rem 0.5rem;
          font-size: 0.75rem;
          background: transparent;
          border: none;
          text-align: left;
          cursor: pointer;
        }
        .trace-header:hover { background: rgba(255,255,255,0.03); }
        .trace-tick { color: var(--muted); font-family: monospace; }
        .trace-action { font-weight: 600; text-transform: uppercase; font-size: 0.7rem; }
        .trace-latency { color: var(--muted); font-size: 0.65rem; text-align: right; }
        .trace-badge {
          font-size: 0.72rem;
          text-transform: uppercase;
          color: var(--accent);
          background: rgba(100,180,255,0.1);
          padding: 0.2rem 0.45rem;
          border-radius: 999px;
        }
        .trace-badge.path-structured {
          color: #6d9;
          background: rgba(100, 220, 150, 0.12);
        }
        .trace-badge.path-fallback {
          color: #da8;
          background: rgba(220, 170, 100, 0.12);
        }
        .trace-chevron { color: var(--muted); text-align: center; }
        .trace-body { padding: 0.5rem; border-top: 1px solid var(--border); background: rgba(0,0,0,0.15); }
        .trace-label {
          display: block;
          font-size: 0.65rem;
          text-transform: uppercase;
          color: var(--muted);
          margin-bottom: 0.25rem;
        }
        .trace-thinking, .trace-response { margin-bottom: 0.5rem; }
        .trace-thinking pre, .trace-response pre {
          margin: 0;
          font-size: 0.7rem;
          font-family: monospace;
          white-space: pre-wrap;
          word-break: break-word;
          color: var(--muted);
          max-height: 120px;
          overflow-y: auto;
        }
        .trace-thinking pre { color: #9ab; }
        @media (max-width: 700px) {
          .detail-grid, .relationship-metrics { grid-template-columns: 1fr; }
          .memory { grid-template-columns: 2.5rem 1fr; }
          .mem-importance, .emotion { display: none; }
        }
      `}</style>
    </div>
  );
}
