import type { CommandEnvelope, CommandReceipt } from "./generated/protocol";

function csrfToken(): string {
  const row = document.cookie
    .split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith("commander_csrf="));
  return row ? decodeURIComponent(row.split("=", 2)[1]) : "";
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" ? { "X-CSRF-Token": csrfToken() } : {}),
      ...(init.headers ?? {}),
    },
  });
  const payload = (await response.json()) as { detail?: unknown };
  if (!response.ok) {
    const detail = payload.detail;
    const message = typeof detail === "string"
      ? detail
      : detail && typeof detail === "object" && "message" in detail
        ? String((detail as { message: unknown }).message)
        : `Request failed: ${response.status}`;
    throw new ApiError(message, response.status, detail);
  }
  return payload as T;
}

export interface Guest {
  guest_id: string;
  display_name: string;
  expires_at: string;
}

export interface Seat {
  seat: string;
  guest_id: string | null;
  display_name: string | null;
  ready: boolean;
  mine: boolean;
  deck: {
    deck_id: string;
    name: string;
    deck_list_fingerprint: string;
    format_legality: {
      status: string;
      issue_count: number;
      issues: LegalityIssue[];
    };
  } | null;
}

export interface LegalityIssue {
  code: string;
  message: string;
  card: string;
  board: string;
  legality: string;
  released_at: string | null;
  confirmable: boolean;
}

export interface LegalityConfirmationRequired {
  code: "legality_confirmation_required";
  message: string;
  confirmation: string;
  deck_list_fingerprint: string;
  issues: LegalityIssue[];
}

export interface Room {
  room_id: string;
  owner_guest_id: string;
  status: string;
  game_id: string | null;
  format_profile: string;
  seats: Seat[];
}

export interface GameLifecycle {
  game_id: string;
  room_id: string;
  status: "active" | "paused" | "complete" | "aborted";
  state_revision: number;
  format_profile: string;
  seat: string;
  owner: boolean;
  can_stop: boolean;
  can_resume: boolean;
  created_at: string;
  updated_at: string;
  turn_sequence: number;
  active_player: string;
  phase: string;
  step: string;
  pending_principals: string[];
  game_over: boolean;
  winner: string | null;
  pause_reason: { kind?: string; label?: string } | null;
  commands: number;
  decisions: number;
  events: number;
}

export interface SystemStatus {
  server: string;
  protocol: string;
  card_data: {
    ready: boolean;
    phase: string;
    detail: string;
    updating: boolean;
    automatic_updates: boolean;
    update_interval_hours: number;
    restart_required: boolean;
    last_checked_at: string | null;
    next_check_at: string | null;
    last_error: string | null;
    database: {
      cards: number;
      rulings: number;
      image_references: number;
      retained_game_snapshots: number;
      oracle_updated_at: string | null;
      rulings_updated_at: string | null;
    };
  };
  images: {
    mode: string;
    downloaded: number;
    ready: boolean;
  };
  browser: { served_by_server: boolean };
}

export const api = {
  system: () => request<SystemStatus>("/api/v1/system"),
  refreshSystem: () =>
    request<{ accepted: boolean; card_data: SystemStatus["card_data"] }>(
      "/api/v1/system/refresh",
      { method: "POST", body: JSON.stringify({}) },
    ),
  me: () => request<{ guest: Guest }>("/api/v1/me"),
  guest: (display_name: string) =>
    request<{ guest: Guest }>("/api/v1/guests", {
      method: "POST",
      body: JSON.stringify({ display_name }),
    }),
  createRoom: () =>
    request<{ room: Room; invite_code: string }>("/api/v1/rooms", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  joinRoom: (invite_code: string, seat: string) =>
    request<{ room: Room }>("/api/v1/rooms/join", {
      method: "POST",
      body: JSON.stringify({ invite_code, seat }),
    }),
  room: (roomId: string) => request<{ room: Room }>(`/api/v1/rooms/${roomId}`),
  rotateInvite: (roomId: string) =>
    request<{ invite_code: string }>(`/api/v1/rooms/${roomId}/invite`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  deck: (
    roomId: string,
    name: string,
    commander: string,
    decklist: string,
    source_url?: string,
    legality_confirmation?: string,
  ) =>
    request<{
      deck: unknown;
      preflight: { trusted_only_ready: boolean };
      format_legality: { status: string; issues: LegalityIssue[] };
    }>(
      `/api/v1/rooms/${roomId}/deck`,
      {
        method: "PUT",
        body: JSON.stringify({
          name,
          commander,
          decklist,
          source_url: source_url || null,
          legality_confirmation: legality_confirmation || null,
        }),
      },
    ),
  clearDeck: (roomId: string) =>
    request<{ room: Room }>(`/api/v1/rooms/${roomId}/deck`, {
      method: "DELETE",
    }),
  start: (roomId: string) =>
    request<{ game_id: string }>(`/api/v1/rooms/${roomId}/start`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  game: (gameId: string) =>
    request<{ game: GameLifecycle }>(`/api/v1/games/${gameId}`),
  stop: (gameId: string, reason: string) =>
    request<{ game: GameLifecycle }>(`/api/v1/games/${gameId}/stop`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  resume: (gameId: string) =>
    request<{ game: GameLifecycle }>(`/api/v1/games/${gameId}/resume`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  command: (gameId: string, envelope: CommandEnvelope) =>
    request<{ receipt: CommandReceipt }>(`/api/v1/games/${gameId}/commands`, {
      method: "POST",
      body: JSON.stringify(envelope),
    }),
};

export function streamUrl(gameId: string): string {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}/api/v1/games/${gameId}/stream`;
}
