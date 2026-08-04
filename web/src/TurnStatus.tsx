import { useState } from "react";

import {
  presentTurn,
  type MacroPhase,
  type TurnPresentationInput,
} from "./tablePresentation";


export function TurnStatus({ value, compact }: {
  value: TurnPresentationInput;
  compact: boolean;
}) {
  const presentation = presentTurn(value);
  const [expanded, setExpanded] = useState<MacroPhase | null>(null);
  if (presentation.terminal) {
    return (
      <section className="turn-status terminal" data-testid="turn-status-terminal" aria-live="polite">
        <div><span className="eyebrow">MATCH STATUS</span><strong>{presentation.headline}</strong></div>
        <span>{presentation.priority}. Live turn controls are closed.</span>
      </section>
    );
  }
  return (
    <section className={`turn-status${compact ? " compact" : ""}`} data-testid="turn-status" aria-label="Current turn and priority">
      <div className="turn-status-copy">
        <span className="eyebrow">AUTHORITATIVE TURN STATE</span>
        <strong data-testid="active-turn-label">{presentation.headline}</strong>
        <span className="priority-holder" data-testid="priority-label"><span aria-hidden="true">◎</span>{presentation.priority}</span>
        <span className="exact-step" data-testid="exact-step-label">{presentation.exactStep}</span>
      </div>
      <ol className="phase-rail" data-testid="phase-rail" aria-label="Turn phases">
        {presentation.rail.map((entry) => (
          <li key={entry.id} className={entry.state}>
            <button
              type="button"
              aria-current={entry.state === "current" ? "step" : undefined}
              aria-expanded={expanded === entry.id}
              onClick={() => setExpanded((current) => current === entry.id ? null : entry.id)}
            >
              <span className="phase-marker" aria-hidden="true">{entry.state === "past" ? "✓" : entry.state === "current" ? "●" : "○"}</span>
              {entry.label}
            </button>
            {expanded === entry.id && (
              <span className="phase-detail" role="status">
                {entry.state === "current" ? presentation.exactStep : entry.state === "past" ? "Completed this turn" : "Upcoming this turn"}
              </span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
