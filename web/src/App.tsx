import { FormEvent, useEffect, useRef, useState } from "react";
import { api, type GameLifecycle, type Guest, type Room, streamUrl } from "./api";
import { ChoiceFormView } from "./ChoiceForm";
import {
  executableChoices,
  initialChoices,
  validateChoices,
  type ChoiceValues,
} from "./choices";
import type { CommandEnvelope, DecisionPacket, JsonValue, LegalAction } from "./generated/protocol";
import { ingestPacket, type ProjectedView } from "./protocol";

type Screen = "loading" | "welcome" | "lobby" | "room" | "game";

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
        <div className="eyebrow">SERVER-AUTHORITATIVE COMMANDER</div>
        <h1>Four seats. One rules engine.</h1>
        <p>
          Every hand is private, every command is replayable, and the battlefield
          is projected independently for each player.
        </p>
        <form onSubmit={submit} className="stack-form">
          <label>
            Display name
            <input
              data-testid="display-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={40}
              autoFocus
              required
            />
          </label>
          <button data-testid="create-guest" type="submit">Enter the arena</button>
        </form>
        {error && <div className="error-banner">{error}</div>}
      </section>
    </main>
  );
}

function Lobby({ guest, onRoom }: { guest: Guest; onRoom: (room: Room, invite?: string) => void }) {
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
        <div><span className="status-dot" /> Signed in as {guest.display_name}</div>
        <h1>Find your table</h1>
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
      {error && <div className="error-banner">{error}</div>}
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
  const [name, setName] = useState("My Commander deck");
  const [commander, setCommander] = useState("");
  const [decklist, setDecklist] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const mine = room.seats.find((seat) => seat.mine);
  const owner = room.owner_guest_id === guest.guest_id;

  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const result = await api.room(room.room_id);
        setRoom(result.room);
        if (result.room.game_id) onGame(result.room.game_id);
      } catch (caught) {
        setMessage(caught instanceof Error ? caught.message : String(caught));
      }
    }, 750);
    return () => window.clearInterval(timer);
  }, [room.room_id, onGame]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api.deck(
        room.room_id,
        name,
        commander,
        sourceUrl.trim() ? "" : decklist,
        sourceUrl.trim() || undefined,
      );
      setMessage(
        result.preflight.trusted_only_ready
          ? "Deck validated: trusted-only semantic gate passes."
          : "Deck accepted with semantic fidelity warnings.",
      );
      setRoom((await api.room(room.room_id)).room);
    } catch (caught) {
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
        {invite && (
          <div className="invite-chip">
            <span>Invite code</span>
            <strong data-testid="room-invite">{invite}</strong>
          </div>
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
            <span className={seat.ready ? "ready" : "waiting"}>{seat.ready ? "READY" : "WAITING"}</span>
          </article>
        ))}
      </section>
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
      {owner && (
        <div className="start-bar">
          <span>{room.seats.filter((seat) => seat.ready).length}/4 decks ready</span>
          <button data-testid="start-game" disabled={busy || !room.seats.every((seat) => seat.ready)} onClick={start}>Start game</button>
        </div>
      )}
      {message && <div className={message.includes("passes") ? "success-banner" : "error-banner"}>{message}</div>}
    </main>
  );
}

function PlayerBoard({ seat, player }: { seat: string; player: Record<string, JsonValue> }) {
  const battlefield = asList(player.bf);
  const command = asList(player.cmd);
  return (
    <article className="player-board" data-testid={`player-${seat}`}>
      <header>
        <span className="seat-letter small">{seat}</span>
        <div><strong>Seat {seat}</strong><small>{String(player.hand_n ?? 0)} cards · {String(player.lib_n ?? 0)} library</small></div>
        <div className="life">{String(player.life ?? 0)}</div>
      </header>
      <div className="zone-label">COMMAND</div>
      <div className="card-strip command-zone">{command.map((card, index) => <span key={index}>{cardName(card)}</span>)}</div>
      <div className="zone-label">BATTLEFIELD</div>
      <div className="card-strip battlefield">{battlefield.length ? battlefield.map((card, index) => <span key={index}>{cardName(card)}</span>) : <em>Empty</em>}</div>
    </article>
  );
}

function GameView({ gameId }: { gameId: string }) {
  const [view, setView] = useState<ProjectedView | null>(null);
  const viewRef = useRef<ProjectedView | null>(null);
  const ingestChain = useRef(Promise.resolve());
  const [connection, setConnection] = useState("CONNECTING");
  const [notice, setNotice] = useState("");
  const [selectedAction, setSelectedAction] = useState<LegalAction | null>(null);
  const [choiceValues, setChoiceValues] = useState<ChoiceValues>({});
  const [choiceErrors, setChoiceErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [lifecycle, setLifecycle] = useState<GameLifecycle | null>(null);
  const [stopReason, setStopReason] = useState("Pause for a table break");
  const [showInspection, setShowInspection] = useState(false);
  const [controlling, setControlling] = useState(false);

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
  }, [gameId]);

  useEffect(() => {
    setSelectedAction(null);
    setChoiceValues({});
    setChoiceErrors([]);
  }, [view?.decision?.id]);

  async function act(action: LegalAction, choices: ChoiceValues = {}) {
    if (!view?.decision || lifecycle?.status !== "active") return;
    const envelope: CommandEnvelope = {
      protocol_version: "3.0",
      game_id: gameId,
      command_id: `web-${crypto.randomUUID()}`,
      decision_id: view.decision.id,
      action_id: action.id,
      capability: view.decision.cap,
      expected_view_revision: view.viewRevision,
      choices,
    };
    setSubmitting(true);
    try {
      const result = await api.command(gameId, envelope);
      setNotice(result.receipt.summary);
      if (!result.receipt.ok) {
        setNotice(`${result.receipt.code}: ${result.receipt.summary}`);
      } else {
        setSelectedAction(null);
        setChoiceValues({});
        setChoiceErrors([]);
      }
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
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
  return (
    <main className="game-shell" data-view-revision={view.viewRevision}>
      <header className="game-topbar">
        <div><span className={`connection ${connection.toLowerCase()}`} /> {connection}</div>
        <strong>GAME {String(game.id ?? gameId).slice(0, 8)}</strong>
        <div className="game-status-line">
          <span data-testid="game-status" className={`game-status ${lifecycle?.status ?? "loading"}`}>
            {(lifecycle?.status ?? "loading").toUpperCase()}
          </span>
          Turn {String(turn.n ?? turn.turn ?? 0)} · {String(turn.phase ?? "setup")} {String(turn.step ?? "")}
        </div>
      </header>
      <section className="operations-panel" aria-label="Match operations">
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
      <section className="boards-grid">
        {Object.entries(players).map(([seat, player]) => <PlayerBoard key={seat} seat={seat} player={asRecord(player)} />)}
      </section>
      <aside className="stack-panel">
        <div className="zone-label">STACK</div>
        {stack.length ? stack.map((item, index) => <span key={index}>{cardName(item)}</span>) : <em>Empty</em>}
      </aside>
      <section className="hand-panel">
        <header><div><span className="eyebrow">YOUR PRIVATE ZONE · SEAT {ownSeat}</span><h2>Hand</h2></div><strong>{hand.length}</strong></header>
        <div className="hand-cards" data-testid="own-hand">
          {hand.map((card, index) => <article key={index} className="hand-card"><small>{String(asRecord(card).id ?? "")}</small><strong>{cardName(card)}</strong></article>)}
        </div>
      </section>
      <section className="decision-panel" data-testid="decision-panel">
        {view.decision ? (
          <>
            <div><span className="eyebrow">DECISION {view.decision.id}</span><h2>{view.decision.kind}</h2></div>
            <div className="action-row">
              {view.decision.legal_actions.map((action) => (
                <button key={action.id} data-testid={`action-${action.id}`} disabled={submitting || lifecycle?.status !== "active"} onClick={() => chooseAction(action)}>{action.label ?? action.kind ?? action.action}</button>
              ))}
            </div>
          </>
        ) : <p>Waiting for another player’s decision.</p>}
      </section>
      {selectedAction?.form && (
        <div className="choice-overlay" role="presentation">
          <form className="choice-dialog" role="dialog" aria-modal="true" aria-labelledby="choice-dialog-title" data-testid="choice-dialog" onSubmit={submitChoice}>
            <header>
              <div>
                <span className="eyebrow">SERVER-ISSUED CHOICES</span>
                <h2 id="choice-dialog-title">{selectedAction.label ?? selectedAction.action}</h2>
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
            <button type="submit" data-testid="submit-choice" disabled={submitting}>
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
  const [guest, setGuest] = useState<Guest | null>(null);
  const [room, setRoom] = useState<Room | null>(null);
  const [invite, setInvite] = useState("");
  const [gameId, setGameId] = useState("");

  useEffect(() => {
    api.me().then(async (result) => {
      setGuest(result.guest);
      const roomId = localStorage.getItem("commander-room");
      if (!roomId) {
        setScreen("lobby");
        return;
      }
      try {
        const saved = (await api.room(roomId)).room;
        setRoom(saved);
        if (saved.game_id) {
          setGameId(saved.game_id);
          setScreen("game");
        } else {
          setScreen("room");
        }
      } catch {
        localStorage.removeItem("commander-room");
        setScreen("lobby");
      }
    }).catch(() => setScreen("welcome"));
  }, []);

  function enterRoom(next: Room, code = "") {
    setRoom(next);
    setInvite(code);
    localStorage.setItem("commander-room", next.room_id);
    setScreen("room");
  }

  function enterGame(id: string) {
    setGameId(id);
    setScreen("game");
  }

  if (screen === "loading") return <main className="loading-screen"><div className="spinner" /></main>;
  if (screen === "welcome") return <Welcome onReady={(value) => { setGuest(value); setScreen("lobby"); }} />;
  if (!guest) return null;
  if (screen === "lobby") return <Lobby guest={guest} onRoom={enterRoom} />;
  if (screen === "room" && room) return <RoomView guest={guest} initial={room} invite={invite} onGame={enterGame} />;
  if (screen === "game" && gameId) return <GameView gameId={gameId} />;
  return null;
}
