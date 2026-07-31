import { FormEvent, useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  type GameLifecycle,
  type Guest,
  type LegalityConfirmationRequired,
  type Room,
  type SystemStatus,
  streamUrl,
} from "./api";
import { ChoiceFormView } from "./ChoiceForm";
import {
  executableChoices,
  initialChoices,
  validateChoices,
  type ChoiceValues,
} from "./choices";
import type { CommandEnvelope, DecisionPacket, JsonValue, LegalAction } from "./generated/protocol";
import { ingestPacket, type ProjectedView } from "./protocol";

type Screen = "loading" | "setup" | "welcome" | "lobby" | "room" | "game";

function asRecord(value: JsonValue | undefined): Record<string, JsonValue> {
  return value && !Array.isArray(value) && typeof value === "object" ? value : {};
}

function asList(value: JsonValue | undefined): JsonValue[] {
  return Array.isArray(value) ? value : [];
}

function cardName(value: JsonValue): string {
  const card = asRecord(value);
  return String(card.n ?? card.name ?? card.id ?? "Unknown card");
}

function readable(value: JsonValue | undefined, fallback = "Unknown"): string {
  const text = String(value ?? "").replaceAll("_", " ").trim();
  return text ? text.replace(/\b\w/g, (letter) => letter.toUpperCase()) : fallback;
}

function inviteStorageKey(roomId: string): string {
  return `commander-invite:${roomId}`;
}

function actionTone(action: LegalAction): string {
  const value = `${action.id} ${action.action} ${action.kind ?? ""}`.toLowerCase();
  if (value.includes("pass") || value.includes("decline") || value.includes("cancel")) return "quiet";
  if (value.includes("concede")) return "danger";
  return "primary";
}

function CardTile({ value, view, compact = false }: { value: JsonValue; view: ProjectedView; compact?: boolean }) {
  const card = asRecord(value);
  const cid = typeof card.cid === "string" ? card.cid : "";
  const definition = cid ? view.definitions[cid] : undefined;
  const [showImage, setShowImage] = useState(Boolean(cid));
  return (
    <article className={`card-tile${compact ? " compact" : " hand-card"}${showImage ? " has-image" : ""}${card.tap ? " tapped" : ""}`} title={String(definition?.o ?? cardName(value))}>
      {showImage && (
        <img
          src={`/api/v1/cards/${cid}/image?size=${compact ? "small" : "normal"}`}
          alt=""
          loading="lazy"
          onError={() => setShowImage(false)}
        />
      )}
      <div className="card-copy">
        <small>{String(definition?.m ?? card.id ?? "")}</small>
        <strong>{cardName(value)}</strong>
        {!compact && definition?.t && <span>{String(definition.t)}</span>}
        {card.ctr && <span>{Object.entries(asRecord(card.ctr)).map(([key, amount]) => `${key} ${amount}`).join(" · ")}</span>}
      </div>
    </article>
  );
}

function projectedLabels(view: ProjectedView): Map<string, string> {
  const labels = new Map<string, string>();
  function walk(value: JsonValue | undefined) {
    if (Array.isArray(value)) {
      value.forEach(walk);
      return;
    }
    if (!value || typeof value !== "object") return;
    const row = value as Record<string, JsonValue>;
    const id = row.id;
    if (typeof id === "string") {
      const label = row.label ?? row.n ?? row.name;
      if (typeof label === "string") labels.set(id, label);
    }
    Object.values(row).forEach(walk);
  }
  walk(view.state);
  walk(view.decision?.ctx);
  for (const seat of ["A", "B", "C", "D"]) labels.set(seat, `Seat ${seat}`);
  return labels;
}

function Welcome({ onReady }: { onReady: (guest: Guest) => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      setError("");
      const result = await api.guest(name.trim());
      onReady(result.guest);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }
  return (
    <main className="welcome-shell">
      <section className="hero-card">
        <div className="hero-copy">
          <div className="brand-mark" aria-hidden="true">CA</div>
          <div className="eyebrow">SERVER-AUTHORITATIVE COMMANDER</div>
          <h1>Four seats.<br />One source of truth.</h1>
          <p>
            Play multiplayer Commander through a deterministic rules engine.
            Your hand stays private, every accepted move is replayable, and each
            player sees only their own projected table.
          </p>
          <ul className="trust-list" aria-label="Platform guarantees">
            <li>Seat-private game views</li>
            <li>Server-validated actions</li>
            <li>Durable match recovery</li>
          </ul>
        </div>
        <form onSubmit={submit} className="stack-form entry-form">
          <div>
            <span className="step-kicker">01 · PLAYER IDENTITY</span>
            <h2>Enter the arena</h2>
            <p>Choose the name your pod will see. No account is required.</p>
          </div>
          <label>
            Display name
            <input
              data-testid="display-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={40}
              autoComplete="nickname"
              autoFocus
              required
            />
          </label>
          <button data-testid="create-guest" type="submit">Continue to tables <span aria-hidden="true">→</span></button>
          {error && <div className="error-banner" role="alert">{error}</div>}
        </form>
      </section>
    </main>
  );
}

function Lobby({ guest, system, onRoom }: { guest: Guest; system: SystemStatus | null; onRoom: (room: Room, invite?: string) => void }) {
  const [invite, setInvite] = useState("");
  const [seat, setSeat] = useState("B");
  const [error, setError] = useState("");
  async function create() {
    try {
      setError("");
      const result = await api.createRoom();
      onRoom(result.room, result.invite_code);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }
  async function join(event: FormEvent) {
    event.preventDefault();
    try {
      setError("");
      const result = await api.joinRoom(invite.trim(), seat);
      onRoom(result.room);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }
  return (
    <main className="page-shell narrow">
      <header className="page-header">
        <div className="session-line">
          <span className="status-dot" /> Session ready · {guest.display_name}
          {system?.card_data.database && <> · {system.card_data.database.cards.toLocaleString()} local cards</>}
        </div>
        <div className="eyebrow">COMMANDER ARENA</div>
        <h1>Find your table</h1>
        <p className="page-lede">Host a private four-player pod or join a seat with an invite code.</p>
      </header>
      <div className="lobby-grid">
        <section className="panel">
          <div className="panel-number">01</div>
          <h2>Host a pod</h2>
          <p>Create an invite-only four-player Commander room.</p>
          <button data-testid="create-room" onClick={create}>Create room</button>
        </section>
        <section className="panel">
          <div className="panel-number">02</div>
          <h2>Join a pod</h2>
          <form onSubmit={join} className="stack-form">
            <label>
              Invite code
              <input data-testid="invite-code" value={invite} onChange={(event) => setInvite(event.target.value)} required />
            </label>
            <label>
              Seat
              <select data-testid="seat-select" value={seat} onChange={(event) => setSeat(event.target.value)}>
                {"ABCD".split("").map((value) => <option key={value}>{value}</option>)}
              </select>
            </label>
            <button data-testid="join-room" type="submit">Take seat</button>
          </form>
        </section>
      </div>
      {error && <div className="error-banner" role="alert">{error}</div>}
    </main>
  );
}

function RoomView({
  guest,
  initial,
  invite,
  onGame,
}: {
  guest: Guest;
  initial: Room;
  invite: string;
  onGame: (gameId: string) => void;
}) {
  const [room, setRoom] = useState(initial);
  const [currentInvite, setCurrentInvite] = useState(invite);
  const [name, setName] = useState("My Commander deck");
  const [commander, setCommander] = useState("");
  const [decklist, setDecklist] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "warning" | "error">("success");
  const [busy, setBusy] = useState(false);
  const [legalityReview, setLegalityReview] = useState<LegalityConfirmationRequired | null>(null);
  const mine = room.seats.find((seat) => seat.mine);
  const owner = room.owner_guest_id === guest.guest_id;
  const readyCount = room.seats.filter((seat) => seat.ready).length;

  async function copyInvite() {
    try {
      await navigator.clipboard.writeText(currentInvite);
      setMessageKind("success");
      setMessage("Invite code copied to clipboard.");
    } catch {
      setMessageKind("error");
      setMessage("Could not copy automatically. Select the invite code and copy it manually.");
    }
  }

  async function replaceInvite() {
    setBusy(true);
    try {
      const result = await api.rotateInvite(room.room_id);
      setCurrentInvite(result.invite_code);
      sessionStorage.setItem(inviteStorageKey(room.room_id), result.invite_code);
      setMessageKind("success");
      setMessage("A new invite code was created. The previous code no longer works.");
    } catch (caught) {
      setMessageKind("error");
      setMessage(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const result = await api.room(room.room_id);
        setRoom(result.room);
        if (result.room.game_id) onGame(result.room.game_id);
      } catch (caught) {
        setMessageKind("error");
        setMessage(caught instanceof Error ? caught.message : String(caught));
      }
    }, 750);
    return () => window.clearInterval(timer);
  }, [room.room_id, onGame]);

  async function submitDeck(legalityConfirmation?: string) {
    setBusy(true);
    if (!legalityConfirmation) setLegalityReview(null);
    try {
      const result = await api.deck(
        room.room_id,
        name,
        commander,
        sourceUrl.trim() ? "" : decklist,
        sourceUrl.trim() || undefined,
        legalityConfirmation,
      );
      setLegalityReview(null);
      const preview = result.format_legality.status === "preview_override_confirmed";
      if (!result.preflight.trusted_only_ready) {
        setMessage("Deck accepted with semantic fidelity warnings. Unsupported card behavior will still fail closed during play.");
        setMessageKind("warning");
      } else if (preview) {
        setMessage("Preview-card legality warning confirmed. The exact override is recorded with this list.");
        setMessageKind("warning");
      } else {
        setMessage("Deck validated: trusted-only semantic gate passes.");
        setMessageKind("success");
      }
      setRoom((await api.room(room.room_id)).room);
    } catch (caught) {
      const detail = caught instanceof ApiError ? caught.detail : null;
      if (
        detail
        && typeof detail === "object"
        && "code" in detail
        && detail.code === "legality_confirmation_required"
      ) {
        setLegalityReview(detail as LegalityConfirmationRequired);
        setMessageKind("warning");
        setMessage("Review and confirm the preview-card legality warning to continue.");
        return;
      }
      setMessageKind("error");
      setMessage(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    await submitDeck();
  }

  async function unready() {
    setBusy(true);
    try {
      const result = await api.clearDeck(room.room_id);
      setRoom(result.room);
      setLegalityReview(null);
      setMessageKind("success");
      setMessage("You are unready. Update or replace your deck, then validate it again.");
    } catch (caught) {
      setMessageKind("error");
      setMessage(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    setBusy(true);
    try {
      const result = await api.start(room.room_id);
      onGame(result.game_id);
    } catch (caught) {
      setMessageKind("error");
      setMessage(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page-shell">
      <header className="room-header">
        <div>
          <div className="eyebrow">COMMANDER MULTIPLAYER · 40 LIFE</div>
          <h1>Room {room.room_id.slice(0, 8)}</h1>
        </div>
        {owner && currentInvite && (
          <div className="invite-chip">
            <div><span>Invite code</span><strong data-testid="room-invite">{currentInvite}</strong></div>
            <div className="invite-actions">
              <button type="button" className="icon-button" aria-label="Copy invite code" onClick={copyInvite}>Copy</button>
              <button type="button" className="quiet-button" data-testid="replace-invite" disabled={busy} onClick={replaceInvite}>Replace</button>
            </div>
          </div>
        )}
        {owner && !currentInvite && (
          <button type="button" data-testid="replace-invite" disabled={busy} onClick={replaceInvite}>Generate new invite</button>
        )}
      </header>
      <section className="seat-row">
        {room.seats.map((seat) => (
          <article key={seat.seat} className={`seat-card ${seat.mine ? "mine" : ""}`} data-testid={`seat-${seat.seat}`}>
            <div className="seat-letter">{seat.seat}</div>
            <div>
              <strong>{seat.display_name ?? "Open seat"}</strong>
              <small>{seat.deck?.name ?? "No deck submitted"}</small>
            </div>
            <span className={`seat-state ${seat.ready ? "ready" : "waiting"}`}><i aria-hidden="true" />{seat.ready ? "READY" : "WAITING"}</span>
          </article>
        ))}
      </section>
      {mine?.ready && mine.deck && (
        <section className="deck-ready-card" data-testid="deck-ready-summary">
          <div className="deck-ready-icon" aria-hidden="true">✓</div>
          <div>
            <div className="eyebrow">YOUR DECK · SEAT {mine.seat}</div>
            <h2>{mine.deck.name}</h2>
            {mine.deck.format_legality.status === "preview_override_confirmed" ? (
              <p><span className="preview-chip">PREVIEW OVERRIDE</span> {mine.deck.format_legality.issue_count} not-yet-legal card{mine.deck.format_legality.issue_count === 1 ? "" : "s"} explicitly confirmed. Images are cached locally.</p>
            ) : (
              <p>Validated, fingerprinted, and ready. Card images are cached locally in the background.</p>
            )}
          </div>
          <div className="deck-ready-actions">
            <code title="Exact deck-list fingerprint">{mine.deck.deck_list_fingerprint.slice(0, 12)}</code>
            <button type="button" className="quiet-button" data-testid="unready-deck" disabled={busy} onClick={unready}>Change deck / Unready</button>
          </div>
        </section>
      )}
      {!mine?.ready && (
        <section className="panel deck-panel">
          <div>
            <div className="eyebrow">SEAT {mine?.seat}</div>
            <h2>Validate your deck</h2>
            <p>The server resolves names against the pinned card database, checks Commander legality, and runs semantic preflight before marking you ready.</p>
          </div>
          <form onSubmit={upload} className="deck-form">
            <label>Deck name<input data-testid="deck-name" value={name} onChange={(event) => setName(event.target.value)} required /></label>
            <label>Commander (required for pasted text)<input data-testid="commander-name" value={commander} onChange={(event) => setCommander(event.target.value)} required={!sourceUrl.trim()} /></label>
            <label className="wide">Public Moxfield URL<input data-testid="deck-source-url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://moxfield.com/decks/…" /></label>
            <div className="import-divider wide"><span>or paste a list</span></div>
            <label className="wide">Deck list<textarea data-testid="deck-list" value={decklist} onChange={(event) => setDecklist(event.target.value)} rows={12} required={!sourceUrl.trim()} /></label>
            <button data-testid="submit-deck" disabled={busy} type="submit">{busy ? "Validating…" : "Validate and ready"}</button>
          </form>
        </section>
      )}
      {!mine?.ready && legalityReview && (
        <section className="preview-review" role="alert" data-testid="legality-confirmation">
          <div>
            <div className="eyebrow">PREVIEW CARD WARNING</div>
            <h2>These cards are not Commander-legal yet.</h2>
            <p>They exist in the current Scryfall snapshot but have future release dates. Confirming records an override for this exact deck fingerprint; it does not waive rules-semantic failures.</p>
          </div>
          <ul>
            {legalityReview.issues.map((issue) => (
              <li key={`${issue.card}:${issue.board}`}>
                <strong>{issue.card}</strong>
                <span>{readable(issue.legality)} · releases {issue.released_at ?? "unknown"}</span>
              </li>
            ))}
          </ul>
          <button
            type="button"
            data-testid="confirm-preview-legality"
            disabled={busy}
            onClick={() => void submitDeck(legalityReview.confirmation)}
          >
            {busy ? "Confirming…" : "I understand — use this preview list"}
          </button>
        </section>
      )}
      {owner && (
        <div className="start-bar">
          <div className="readiness-copy">
            <strong>{readyCount}/4 decks ready</strong>
            <span>{readyCount === 4 ? "Your pod is ready to begin." : "Waiting for every seat to validate a deck."}</span>
          </div>
          <div className="readiness-meter" aria-label={`${readyCount} of 4 decks ready`}><span style={{ width: `${readyCount * 25}%` }} /></div>
          <button data-testid="start-game" disabled={busy || !room.seats.every((seat) => seat.ready)} onClick={start}>Start game</button>
        </div>
      )}
      {message && <div className={`${messageKind}-banner`} role={messageKind === "error" ? "alert" : "status"}>{message}</div>}
    </main>
  );
}

function PlayerBoard({
  seat,
  player,
  active,
  priority,
  mine,
  view,
}: {
  seat: string;
  player: Record<string, JsonValue>;
  active: boolean;
  priority: boolean;
  mine: boolean;
  view: ProjectedView;
}) {
  const battlefield = asList(player.bf);
  const command = asList(player.cmd);
  const graveyard = asList(player.gy);
  const exile = asList(player.ex);
  const mana = asRecord(player.mana);
  return (
    <article className={`player-board${active ? " active-player" : ""}${priority ? " has-priority" : ""}${mine ? " own-board" : ""}`} data-testid={`player-${seat}`}>
      <header>
        <span className="seat-letter small">{seat}</span>
        <div>
          <div className="player-name"><strong>Seat {seat}</strong>{mine && <span className="you-chip">You</span>}</div>
          <small>{String(player.hand_n ?? 0)} hand · {String(player.lib_n ?? 0)} library</small>
        </div>
        <div className="life" aria-label={`${String(player.life ?? 0)} life`}><span>{String(player.life ?? 0)}</span><small>LIFE</small></div>
      </header>
      {(active || priority) && <div className="turn-flags">{active && <span>Active player</span>}{priority && <span>Priority</span>}</div>}
      <div className="zone-label">COMMAND</div>
      <div className="card-strip command-zone">{command.length ? command.map((card, index) => <CardTile key={String(asRecord(card).id ?? index)} value={card} view={view} compact />) : <em>Empty</em>}</div>
      <div className="zone-label">BATTLEFIELD</div>
      <div className="card-strip battlefield">{battlefield.length ? battlefield.map((card, index) => <CardTile key={String(asRecord(card).id ?? index)} value={card} view={view} compact />) : <em>Empty battlefield</em>}</div>
      <footer className="zone-summary">
        <span>GY <strong>{graveyard.length}</strong></span>
        <span>EXILE <strong>{exile.length}</strong></span>
        <span>LAND <strong>{String(player.lands ?? 0)}</strong></span>
        <span>MANA <strong>{Object.entries(mana).map(([color, amount]) => `${color}${amount}`).join(" ") || "—"}</strong></span>
      </footer>
    </article>
  );
}

function SetupScreen({ initial, onReady }: { initial: SystemStatus; onReady: () => void }) {
  const [status, setStatus] = useState(initial);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const next = await api.system();
        if (stopped) return;
        setStatus(next);
        if (next.card_data.ready) onReady();
      } catch {
        // Keep the last actionable setup status visible while the server restarts.
      }
    };
    const timer = window.setInterval(poll, 1000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [onReady]);

  async function retry() {
    setRetrying(true);
    try {
      await api.refreshSystem();
      setStatus(await api.system());
    } catch {
      // Polling keeps the last server-provided failure visible.
    } finally {
      setRetrying(false);
    }
  }

  const data = status.card_data;
  const progress = data.phase === "building" ? 72 : data.phase === "downloading" ? 38 : data.phase === "checking" ? 18 : 8;
  return (
    <main className="setup-shell" data-testid="setup-screen">
      <section className="setup-card" aria-live="polite">
        <div className="brand-mark" aria-hidden="true">CA</div>
        <div>
          <div className="eyebrow">FIRST-RUN SETUP</div>
          <h1>Preparing your card library.</h1>
          <p>{data.detail}</p>
        </div>
        <div className="setup-progress" role="progressbar" aria-label="Card library setup" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
          <span style={{ width: `${progress}%` }} />
        </div>
        <dl className="setup-facts">
          <div><dt>Server</dt><dd><span className="status-dot" /> Running</dd></div>
          <div><dt>Card data</dt><dd>{readable(data.phase)}</dd></div>
          <div><dt>Images</dt><dd>Local cache · {status.images.downloaded}</dd></div>
        </dl>
        {data.last_error && <div className="error-banner" role="alert">{data.last_error}</div>}
        {data.phase === "error" && data.automatic_updates && (
          <button type="button" onClick={retry} disabled={retrying}>{retrying ? "Retrying…" : "Retry setup"}</button>
        )}
        <small>Initial setup downloads compressed Scryfall bulk data once. Future checks run every 24 hours.</small>
      </section>
    </main>
  );
}

function GameView({ gameId }: { gameId: string }) {
  const [view, setView] = useState<ProjectedView | null>(null);
  const viewRef = useRef<ProjectedView | null>(null);
  const ingestChain = useRef(Promise.resolve());
  const [connection, setConnection] = useState("CONNECTING");
  const [reconnectNonce, setReconnectNonce] = useState(0);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [notice, setNotice] = useState("");
  const [selectedAction, setSelectedAction] = useState<LegalAction | null>(null);
  const [choiceValues, setChoiceValues] = useState<ChoiceValues>({});
  const [choiceErrors, setChoiceErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [lifecycle, setLifecycle] = useState<GameLifecycle | null>(null);
  const [stopReason, setStopReason] = useState("Pause for a table break");
  const [showInspection, setShowInspection] = useState(false);
  const [controlling, setControlling] = useState(false);
  const [pendingRetry, setPendingRetry] = useState<{ envelope: CommandEnvelope; label: string } | null>(null);
  const choiceDialogRef = useRef<HTMLFormElement | null>(null);

  useEffect(() => {
    let stopped = false;
    let socket: WebSocket | null = null;
    let retry = 250;
    let timer = 0;
    function connect() {
      if (stopped) return;
      setConnection("CONNECTING");
      socket = new WebSocket(streamUrl(gameId));
      socket.onopen = () => {
        retry = 250;
        setReconnectAttempts(0);
        setConnection("LIVE");
      };
      socket.onmessage = (event) => {
        const message = JSON.parse(String(event.data)) as {
          type: string;
          packet?: DecisionPacket;
          game?: GameLifecycle;
        };
        if (message.game) setLifecycle(message.game);
        if (message.type !== "projection" || !message.packet) return;
        ingestChain.current = ingestChain.current
          .then(async () => {
            const next = await ingestPacket(viewRef.current, message.packet!);
            viewRef.current = next;
            setView(next);
          })
          .catch((error) => {
            setNotice(error instanceof Error ? error.message : String(error));
            socket?.close();
          });
      };
      socket.onclose = () => {
        if (stopped) return;
        setConnection("RECONNECTING");
        setReconnectAttempts((value) => value + 1);
        timer = window.setTimeout(connect, retry);
        retry = Math.min(retry * 2, 5000);
      };
    }
    api.game(gameId)
      .then((result) => setLifecycle(result.game))
      .catch((caught) => setNotice(caught instanceof Error ? caught.message : String(caught)));
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      socket?.close();
      viewRef.current = null;
    };
  }, [gameId, reconnectNonce]);

  useEffect(() => {
    setSelectedAction(null);
    setChoiceValues({});
    setChoiceErrors([]);
  }, [view?.decision?.id]);

  useEffect(() => {
    if (pendingRetry && view?.decision?.id !== pendingRetry.envelope.decision_id) {
      setPendingRetry(null);
    }
  }, [pendingRetry, view?.decision?.id]);

  useEffect(() => {
    if (!selectedAction) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.requestAnimationFrame(() => {
      choiceDialogRef.current?.querySelector<HTMLElement>("input:not(:disabled), select:not(:disabled), button:not(:disabled)")?.focus();
    });
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setSelectedAction(null);
        return;
      }
      if (event.key !== "Tab" || !choiceDialogRef.current) return;
      const controls = [...choiceDialogRef.current.querySelectorAll<HTMLElement>("input:not(:disabled), select:not(:disabled), textarea:not(:disabled), button:not(:disabled), [tabindex]:not([tabindex='-1'])")];
      if (!controls.length) return;
      const first = controls[0];
      const last = controls.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("keydown", keydown);
      document.body.style.overflow = oldOverflow;
      previous?.focus();
    };
  }, [selectedAction]);

  async function submitEnvelope(envelope: CommandEnvelope, label: string) {
    setSubmitting(true);
    try {
      const result = await api.command(gameId, envelope);
      setPendingRetry(null);
      setNotice(result.receipt.summary);
      if (!result.receipt.ok) {
        setNotice(`${result.receipt.code}: ${result.receipt.summary}`);
      } else {
        setSelectedAction(null);
        setChoiceValues({});
        setChoiceErrors([]);
      }
    } catch (caught) {
      setPendingRetry({ envelope, label });
      setNotice(`Delivery uncertain: ${caught instanceof Error ? caught.message : String(caught)}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function act(action: LegalAction, choices: ChoiceValues = {}) {
    if (!view?.decision || lifecycle?.status !== "active" || pendingRetry) return;
    await submitEnvelope(
      {
        protocol_version: "3.0",
        game_id: gameId,
        command_id: `web-${crypto.randomUUID()}`,
        decision_id: view.decision.id,
        action_id: action.id,
        capability: view.decision.cap,
        expected_view_revision: view.viewRevision,
        choices,
      },
      action.label ?? action.action,
    );
  }

  async function stopMatch() {
    setControlling(true);
    try {
      const result = await api.stop(gameId, stopReason.trim());
      setLifecycle(result.game);
      setNotice("Match stopped. The authoritative record is saved and resumable.");
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setControlling(false);
    }
  }

  async function resumeMatch() {
    setControlling(true);
    try {
      const result = await api.resume(gameId);
      setLifecycle(result.game);
      setNotice("Match resumed from the preserved decision boundary.");
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setControlling(false);
    }
  }

  function chooseAction(action: LegalAction) {
    if (!action.form) {
      void act(action);
      return;
    }
    setSelectedAction(action);
    setChoiceValues(initialChoices(action.form));
    setChoiceErrors([]);
  }

  function submitChoice(event: FormEvent) {
    event.preventDefault();
    if (!selectedAction?.form) return;
    const errors = validateChoices(selectedAction.form, choiceValues);
    setChoiceErrors(errors);
    if (errors.length) return;
    void act(
      selectedAction,
      executableChoices(selectedAction.form, choiceValues),
    );
  }

  if (!view) return <main className="loading-screen"><div className="spinner" /><p>Opening your projected table…</p>{notice && <div className="error-banner">{notice}</div>}</main>;
  const state = view.state;
  const game = asRecord(state.game);
  const turn = asRecord(state.turn);
  const players = asRecord(state.players);
  const ownSeat = view.principal.split(":").at(-1) ?? "?";
  const ownPlayer = asRecord(players[ownSeat]);
  const hand = asList(ownPlayer.hand);
  const stack = asList(state.stack);
  const labels = projectedLabels(view);
  const labelFor = (value: string) => labels.get(value) ?? value;
  const activeSeat = String(turn.active ?? "");
  const prioritySeat = String(turn.priority ?? "");
  return (
    <main className="game-shell" data-view-revision={view.viewRevision}>
      <a className="skip-link" href="#decision-tray">Skip to current actions</a>
      <header className="game-topbar">
        <div className="connection-group">
          <span className={`connection ${connection.toLowerCase()}`} />
          <span>{connection}</span>
          {connection !== "LIVE" && <button type="button" className="link-button" onClick={() => setReconnectNonce((value) => value + 1)}>Retry now</button>}
        </div>
        <div className="game-identity"><small>COMMANDER POD</small><strong>{String(game.id ?? gameId).slice(0, 8)}</strong></div>
        <div className="game-status-line">
          <span data-testid="game-status" className={`game-status ${lifecycle?.status ?? "loading"}`}>
            {(lifecycle?.status ?? "loading").toUpperCase()}
          </span>
          <span>Turn {String(turn.seq ?? 0)} · {readable(turn.phase, "Setup")} {readable(turn.step, "")}</span>
        </div>
      </header>
      {connection !== "LIVE" && (
        <div className="connection-banner" role="status">
          <div><strong>Restoring your seat projection</strong><span>No actions are sent while the live table connection is unavailable.</span></div>
          <span>Attempt {Math.max(1, reconnectAttempts)}</span>
        </div>
      )}
      <section className="operations-panel" aria-label="Match operations">
        <div className="operations-heading"><span className="eyebrow">TABLE CONTROLS</span><strong>Seat {ownSeat}</strong></div>
        <button
          type="button"
          className="secondary-button"
          data-testid="inspect-game"
          aria-expanded={showInspection}
          onClick={() => setShowInspection((value) => !value)}
        >Inspect match</button>
        {lifecycle?.owner && lifecycle.can_stop && (
          <label className="stop-control">
            Stop reason
            <input
              data-testid="stop-reason"
              value={stopReason}
              maxLength={500}
              onChange={(event) => setStopReason(event.target.value)}
            />
            <button
              type="button"
              data-testid="stop-game"
              disabled={controlling || !stopReason.trim()}
              onClick={stopMatch}
            >Stop match</button>
          </label>
        )}
        {lifecycle?.owner && lifecycle.can_resume && (
          <button
            type="button"
            data-testid="resume-game"
            disabled={controlling}
            onClick={resumeMatch}
          >Resume match</button>
        )}
      </section>
      {showInspection && lifecycle && (
        <section className="inspection-panel" data-testid="game-inspection">
          <h2>Match record</h2>
          <dl>
            <div><dt>Status</dt><dd>{lifecycle.status}</dd></div>
            <div><dt>Revision</dt><dd>{lifecycle.state_revision}</dd></div>
            <div><dt>Commands</dt><dd>{lifecycle.commands}</dd></div>
            <div><dt>Decisions</dt><dd>{lifecycle.decisions}</dd></div>
            <div><dt>Events</dt><dd>{lifecycle.events}</dd></div>
            <div><dt>Pending seats</dt><dd>{lifecycle.pending_principals.map((value) => value.split(":").at(-1)).join(", ") || "None"}</dd></div>
          </dl>
        </section>
      )}
      {lifecycle?.status === "paused" && (
        <div className="paused-banner" role="status" data-testid="paused-banner">
          <strong>Match stopped</strong>
          <span>{lifecycle.pause_reason?.label ?? "Waiting for the room owner to resume."}</span>
        </div>
      )}
      <div className="table-workspace">
        <section className="boards-grid" aria-label="Four-player battlefield">
          {Object.entries(players).map(([seat, player]) => (
            <PlayerBoard
              key={seat}
              seat={seat}
              player={asRecord(player)}
              active={activeSeat === seat}
              priority={prioritySeat === seat}
              mine={ownSeat === seat}
              view={view}
            />
          ))}
        </section>
        <aside className="table-sidebar" aria-label="Stack and recent game activity">
          <section className="stack-panel">
            <header><div className="zone-label">STACK</div><strong>{stack.length}</strong></header>
            <div className="stack-items">
              {stack.length ? stack.map((item, index) => <CardTile key={String(asRecord(item).id ?? index)} value={item} view={view} compact />) : <em>The stack is empty</em>}
            </div>
          </section>
          <section className="activity-panel">
            <header><div className="zone-label">RECENT ACTIVITY</div></header>
            <ol>
              {view.events.slice(-5).reverse().map((event, index) => <li key={String(event.id ?? index)}><span>{event.a ? `Seat ${event.a}` : "Game"}</span>{String(event.s ?? event.c ?? "State updated")}</li>)}
              {!view.events.length && <li className="empty-activity">Game events will appear here.</li>}
            </ol>
          </section>
        </aside>
      </div>
      <section className="hand-panel">
        <header><div><span className="eyebrow">YOUR PRIVATE ZONE · SEAT {ownSeat}</span><h2>Your hand</h2></div><span className="zone-count">{hand.length} cards</span></header>
        <div className="hand-cards" data-testid="own-hand">
          {hand.map((card, index) => <CardTile key={String(asRecord(card).id ?? index)} value={card} view={view} />)}
        </div>
      </section>
      {pendingRetry && (
        <section className="retry-panel" role="alert" data-testid="command-retry">
          <div><strong>Command delivery is uncertain</strong><span>Retrying “{pendingRetry.label}” will reuse command {pendingRetry.envelope.command_id} exactly.</span></div>
          <button type="button" disabled={submitting} onClick={() => void submitEnvelope(pendingRetry.envelope, pendingRetry.label)}>{submitting ? "Checking…" : "Retry exact command"}</button>
        </section>
      )}
      <section id="decision-tray" className="decision-panel" data-testid="decision-panel" aria-live="polite">
        {view.decision ? (
          <>
            <div className="decision-copy"><span className="eyebrow">YOUR DECISION · {view.decision.id}</span><h2>{readable(view.decision.kind)}</h2><small>{view.decision.legal_actions.length} legal {view.decision.legal_actions.length === 1 ? "action" : "actions"}</small></div>
            <div className="action-row">
              {view.decision.legal_actions.map((action) => (
                <button className={`action-button ${actionTone(action)}`} key={action.id} data-testid={`action-${action.id}`} disabled={submitting || Boolean(pendingRetry) || connection !== "LIVE" || lifecycle?.status !== "active"} onClick={() => chooseAction(action)}>{action.label ?? action.kind ?? action.action}</button>
              ))}
            </div>
          </>
        ) : <div className="waiting-decision"><span className="status-dot muted" /><div><strong>Waiting for the table</strong><p>Waiting for another player’s decision.</p></div></div>}
      </section>
      {selectedAction?.form && (
        <div className="choice-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedAction(null); }}>
          <form ref={choiceDialogRef} className="choice-dialog" role="dialog" aria-modal="true" aria-labelledby="choice-dialog-title" aria-describedby="choice-dialog-description" data-testid="choice-dialog" onSubmit={submitChoice}>
            <header>
              <div>
                <span className="eyebrow">SERVER-ISSUED CHOICES</span>
                <h2 id="choice-dialog-title">{selectedAction.label ?? selectedAction.action}</h2>
                <p id="choice-dialog-description">Choose from the legal values supplied for your seat. The server validates the final action.</p>
              </div>
              <button
                type="button"
                className="secondary-button"
                data-testid="cancel-choice"
                onClick={() => setSelectedAction(null)}
              >Cancel</button>
            </header>
            <ChoiceFormView
              form={selectedAction.form}
              values={choiceValues}
              onChange={(values) => {
                setChoiceValues(values);
                setChoiceErrors([]);
              }}
              labelFor={labelFor}
            />
            {choiceErrors.length > 0 && (
              <ul className="choice-errors" data-testid="choice-errors">
                {choiceErrors.map((error) => <li key={error}>{error}</li>)}
              </ul>
            )}
            <button type="submit" data-testid="submit-choice" disabled={submitting || connection !== "LIVE"}>
              {submitting ? "Submitting…" : selectedAction.form.submit_label}
            </button>
          </form>
        </div>
      )}
      {notice && <div className="toast" role="status" aria-live="polite">{notice}</div>}
    </main>
  );
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("loading");
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [bootNonce, setBootNonce] = useState(0);
  const [guest, setGuest] = useState<Guest | null>(null);
  const [room, setRoom] = useState<Room | null>(null);
  const [invite, setInvite] = useState("");
  const [gameId, setGameId] = useState("");

  useEffect(() => {
    let stopped = false;
    async function boot() {
      try {
        const nextSystem = await api.system();
        if (stopped) return;
        setSystem(nextSystem);
        if (!nextSystem.card_data.ready) {
          setScreen("setup");
          return;
        }
        try {
          const result = await api.me();
          if (stopped) return;
          setGuest(result.guest);
          const roomId = localStorage.getItem("commander-room");
          if (!roomId) {
            setScreen("lobby");
            return;
          }
          try {
            const saved = (await api.room(roomId)).room;
            if (stopped) return;
            setRoom(saved);
            setInvite(sessionStorage.getItem(inviteStorageKey(saved.room_id)) ?? "");
            if (saved.game_id) {
              setGameId(saved.game_id);
              setScreen("game");
            } else {
              setScreen("room");
            }
          } catch {
            localStorage.removeItem("commander-room");
            sessionStorage.removeItem(inviteStorageKey(roomId));
            setScreen("lobby");
          }
        } catch {
          setScreen("welcome");
        }
      } catch {
        setScreen("loading");
      }
    }
    void boot();
    return () => { stopped = true; };
  }, [bootNonce]);

  function enterRoom(next: Room, code = "") {
    setRoom(next);
    setInvite(code);
    localStorage.setItem("commander-room", next.room_id);
    if (code) sessionStorage.setItem(inviteStorageKey(next.room_id), code);
    setScreen("room");
  }

  function enterGame(id: string) {
    setGameId(id);
    setScreen("game");
  }

  if (screen === "loading") return <main className="loading-screen"><div className="spinner" /></main>;
  if (screen === "setup" && system) return <SetupScreen initial={system} onReady={() => { setScreen("loading"); setBootNonce((value) => value + 1); }} />;
  if (screen === "welcome") return <Welcome onReady={(value) => { setGuest(value); setScreen("lobby"); }} />;
  if (!guest) return null;
  if (screen === "lobby") return <Lobby guest={guest} system={system} onRoom={enterRoom} />;
  if (screen === "room" && room) return <RoomView guest={guest} initial={room} invite={invite} onGame={enterGame} />;
  if (screen === "game" && gameId) return <GameView gameId={gameId} />;
  return null;
}
