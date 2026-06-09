interface Event {
  id: number;
  tick: number;
  event_type: string;
  description: string;
}

interface Action {
  tick?: number;
  agent_name?: string;
  description?: string;
  type?: string;
  category?: string;
  action?: { type: string; category?: string; target?: string };
}

interface Props {
  events: Event[];
  liveActions: Action[];
  currentTick: number;
}

export default function Timeline({ events, liveActions, currentTick }: Props) {
  const feed = [
    ...liveActions.map((a, i) => {
      const actionType = a.type || a.action?.type || "unknown";
      const category = a.category || a.action?.category || "unknown";
      return {
        id: `live-${a.tick ?? currentTick}-${a.agent_name ?? i}-${i}`,
        tick: a.tick ?? currentTick,
        event_type: category,
        action_type: actionType,
        description: a.description || `${a.agent_name}: ${actionType}`,
      };
    }),
    ...events.map((e) => ({ ...e, action_type: undefined })),
  ].slice(0, 40);

  return (
    <div className="timeline">
      <h3>Event Feed</h3>
      <div className="feed">
        {feed.length === 0 && (
          <div className="empty">Start the simulation to see events</div>
        )}
        {feed.map((e) => (
          <div key={e.id} className={`event event-${e.event_type}`}>
            <span className="tick">T{e.tick}</span>
            <span className="type" title={e.action_type ? `action: ${e.action_type}` : undefined}>
              {e.action_type ? `${e.event_type} · ${e.action_type}` : e.event_type}
            </span>
            <span className="desc">{e.description}</span>
          </div>
        ))}
      </div>
      <style>{`
        .timeline h3 { font-size: 0.875rem; color: var(--muted); margin-bottom: 0.5rem; }
        .feed {
          max-height: 320px;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }
        .event {
          display: grid;
          grid-template-columns: 3rem 6rem 1fr;
          gap: 0.5rem;
          padding: 0.4rem 0.6rem;
          background: var(--surface);
          border-radius: 4px;
          font-size: 0.8rem;
          border-left: 3px solid var(--border);
        }
        .event-election_won, .event-election_started { border-left-color: var(--gold); }
        .event-economic { border-left-color: #feca57; }
        .event-social { border-left-color: #4ecdc4; }
        .event-political { border-left-color: var(--gold); }
        .event-hostile { border-left-color: #e74c3c; }
        .event-civic { border-left-color: #a29bfe; }
        .event-unknown { border-left-color: var(--muted); }
        .tick { color: var(--muted); font-family: monospace; }
        .type { color: var(--accent); text-transform: uppercase; font-size: 0.7rem; }
        .empty { color: var(--muted); padding: 1rem; text-align: center; }
      `}</style>
    </div>
  );
}
