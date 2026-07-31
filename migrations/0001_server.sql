PRAGMA foreign_keys = ON;

CREATE TABLE server_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE guest_sessions (
    guest_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE TABLE rooms (
    room_id TEXT PRIMARY KEY,
    owner_guest_id TEXT NOT NULL,
    invite_code_hash TEXT NOT NULL UNIQUE,
    visibility TEXT NOT NULL,
    status TEXT NOT NULL,
    seat_count INTEGER NOT NULL,
    format_profile TEXT NOT NULL,
    seed INTEGER NOT NULL,
    game_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(owner_guest_id) REFERENCES guest_sessions(guest_id)
);

CREATE TABLE room_members (
    room_id TEXT NOT NULL,
    guest_id TEXT NOT NULL,
    spectator INTEGER NOT NULL DEFAULT 0,
    joined_at TEXT NOT NULL,
    PRIMARY KEY(room_id, guest_id),
    FOREIGN KEY(room_id) REFERENCES rooms(room_id) ON DELETE CASCADE,
    FOREIGN KEY(guest_id) REFERENCES guest_sessions(guest_id) ON DELETE CASCADE
);

CREATE TABLE decks (
    deck_id TEXT PRIMARY KEY,
    owner_guest_id TEXT NOT NULL,
    name TEXT NOT NULL,
    deck_list_fingerprint TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    preflight_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(owner_guest_id) REFERENCES guest_sessions(guest_id)
);

CREATE TABLE room_seats (
    room_id TEXT NOT NULL,
    seat TEXT NOT NULL,
    guest_id TEXT,
    deck_id TEXT,
    ready INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(room_id, seat),
    UNIQUE(room_id, guest_id),
    FOREIGN KEY(room_id) REFERENCES rooms(room_id) ON DELETE CASCADE,
    FOREIGN KEY(guest_id) REFERENCES guest_sessions(guest_id),
    FOREIGN KEY(deck_id) REFERENCES decks(deck_id)
);

CREATE TABLE games (
    game_id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    record_path TEXT NOT NULL,
    state_revision INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(room_id) REFERENCES rooms(room_id)
);

CREATE TABLE idempotency_records (
    game_id TEXT NOT NULL,
    principal TEXT NOT NULL,
    command_id TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(game_id, principal, command_id)
);

INSERT INTO server_schema_migrations(version) VALUES (1);
