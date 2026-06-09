import { useState } from "react";

interface Trace {
  tick: number;
  action_type: string;
  latency_ms: number;
  thinking?: string;
  response?: string;
}

interface Props {
  agents: Array<{ id: string; name: string; role: string; stats: Record<string, number> }>;
  selectedId: string | null;
  detail: {
    agent?: Record<string, unknown>;
    relationships?: Array<Record<string, number | string>>;
    memories?: Array<{ tick: number; text: string; importance: number; emotion: string }>;
    traces?: Trace[];
  } | null;
  onSelect: (id: string) => void;
}

export default function AgentInspector({ agents, selectedId, detail, onSelect }: Props) {
  const [expandedTrace, setExpandedTrace] = useState<number | null>(null);
  const agent = detail?.agent as Record<string, unknown> | undefined;
  const personality = agent?.personality as Record<string, number> | undefined;
  const stats = agent?.stats as Record<string, number> | undefined;
  const traces = detail?.traces ?? [];

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

      {detail && agent && (
        <div className="detail">
          <h4>{String(agent.name)}</h4>
          <div className="detail-grid">
            <div>
              <strong>Stats</strong>
              <ul>
                {stats &&
                  Object.entries(stats).map(([k, v]) => (
                    <li key={k}>
                      {k}: {v}
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
                      {k}: {Number(v).toFixed(2)}
                    </li>
                  ))}
              </ul>
            </div>
          </div>

          <div className="section">
            <strong>Memories ({detail.memories?.length || 0})</strong>
            <div className="memories">
              {(detail.memories || []).slice(0, 8).map((m, i) => (
                <div key={i} className="memory">
                  <span className="mem-tick">T{m.tick}</span>
                  <span className={`emotion ${m.emotion}`}>{m.emotion}</span>
                  <span>{m.text}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="section">
            <strong>Relationships</strong>
            <ul>
              {(detail.relationships || []).slice(0, 6).map((r, i) => (
                <li key={i}>
                  trust={Number(r.trust).toFixed(2)} friendship=
                  {Number(r.friendship).toFixed(2)}
                </li>
              ))}
            </ul>
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
        .agent-list {
          display: flex;
          flex-wrap: wrap;
          gap: 0.35rem;
          margin-bottom: 1rem;
          max-height: 120px;
          overflow-y: auto;
        }
        .agent-btn {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          padding: 0.35rem 0.6rem;
          font-size: 0.75rem;
        }
        .agent-btn.active { border-color: var(--accent); background: #1e2d3d; }
        .name { font-weight: 600; }
        .role { color: var(--muted); font-size: 0.65rem; }
        .detail { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }
        .detail h4 { margin-bottom: 0.75rem; }
        .detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }
        .detail ul { list-style: none; font-size: 0.8rem; }
        .detail li { padding: 0.15rem 0; color: var(--muted); }
        .section { margin-top: 0.75rem; }
        .section strong { font-size: 0.8rem; display: block; margin-bottom: 0.35rem; }
        .memories { display: flex; flex-direction: column; gap: 0.25rem; }
        .memory { font-size: 0.75rem; display: grid; grid-template-columns: 2.5rem 4rem 1fr; gap: 0.35rem; }
        .mem-tick { color: var(--muted); font-family: monospace; }
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
          font-size: 0.6rem;
          text-transform: uppercase;
          color: var(--accent);
          background: rgba(100,180,255,0.1);
          padding: 0.1rem 0.35rem;
          border-radius: 3px;
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
      `}</style>
    </div>
  );
}
