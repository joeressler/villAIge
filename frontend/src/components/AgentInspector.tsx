interface Props {
  agents: Array<{ id: string; name: string; role: string; stats: Record<string, number> }>;
  selectedId: string | null;
  detail: {
    agent?: Record<string, unknown>;
    relationships?: Array<Record<string, number | string>>;
    memories?: Array<{ tick: number; text: string; importance: number; emotion: string }>;
    traces?: Array<{ tick: number; action_type: string; latency_ms: number }>;
  } | null;
  onSelect: (id: string) => void;
}

export default function AgentInspector({ agents, selectedId, detail, onSelect }: Props) {
  const agent = detail?.agent as Record<string, unknown> | undefined;
  const personality = agent?.personality as Record<string, number> | undefined;
  const stats = agent?.stats as Record<string, number> | undefined;

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
      `}</style>
    </div>
  );
}
