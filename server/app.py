from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import hmac
import os
from pathlib import Path
import secrets
from typing import Any, AsyncIterator
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from mtg_commander_sim import (
    CardDatabase,
    CommandEnvelope,
    CommanderSession,
    DeckLoader,
    DirectoryGamePersistence,
    GameConfig,
    GameManager,
    GameService,
    SqliteIdempotencyRepository,
    deck_list_fingerprint,
    parse_deck_text,
)
from mtg_commander_sim.preflight import semantic_preflight
from mtg_commander_sim.runtime import (
    GameActor,
    GameLifecycleConflict,
    GamePersistence,
)
from mtg_commander_sim.deck import MoxfieldFetchError, is_moxfield_source

from .store import (
    ServerStore,
    StoreConflict,
    StoreForbidden,
    StoreNotFound,
)


COOKIE_NAME = "commander_guest"
CSRF_COOKIE_NAME = "commander_csrf"


@dataclass(frozen=True, slots=True)
class ServerSettings:
    card_db: Path
    database: Path
    game_root: Path
    allowed_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    secure_cookies: bool = False

    @classmethod
    def from_environment(cls) -> "ServerSettings":
        data_root = Path(os.environ.get("MTG_SERVER_DATA", "local/server"))
        return cls(
            card_db=Path(os.environ.get("MTG_CARD_DB", "data/test-ci.sqlite3")),
            database=data_root / "server.sqlite3",
            game_root=data_root / "games",
            allowed_origins=tuple(
                origin.strip()
                for origin in os.environ.get(
                    "MTG_ALLOWED_ORIGINS",
                    "http://localhost:5173,http://127.0.0.1:5173",
                ).split(",")
                if origin.strip()
            ),
            secure_cookies=os.environ.get("MTG_SECURE_COOKIES") == "1",
        )


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GuestRequest(StrictModel):
    display_name: str = Field(min_length=1, max_length=40, pattern=r"^[^\x00-\x1f]+$")

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name cannot be blank")
        return normalized


class RoomRequest(StrictModel):
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)


class JoinRoomRequest(StrictModel):
    invite_code: str = Field(min_length=20, max_length=64)
    seat: str = Field(pattern=r"^[A-Da-d]$")


class DeckRequest(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    commander: str = Field(default="", max_length=200)
    decklist: str = Field(default="", max_length=100_000)
    source_url: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_source(self) -> "DeckRequest":
        has_text = bool(self.decklist.strip())
        has_url = bool((self.source_url or "").strip())
        if has_text == has_url:
            raise ValueError("Supply exactly one of decklist or source_url")
        if has_text and not self.commander.strip():
            raise ValueError("Text deck imports require a commander")
        return self


class StopGameRequest(StrictModel):
    reason: str = Field(
        default="Match stopped by the room owner",
        min_length=1,
        max_length=500,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Stop reason cannot be blank")
        return normalized


class ResumeGameRequest(StrictModel):
    pass


def _server_game_status(service: GameService) -> str:
    session = service.session
    if session.state.game_over:
        return "complete"
    if session.record_status in {"created", "in_progress"}:
        return "active"
    return session.record_status


class _StoreGamePersistence(GamePersistence):
    def __init__(
        self, records: DirectoryGamePersistence, store: ServerStore
    ) -> None:
        self.records = records
        self.store = store

    def save(self, service: GameService) -> None:
        self.records.save(service)
        self.store.update_game_state(
            service.session.state.game_id,
            service.session.state.revision,
            _server_game_status(service),
        )


class ProjectionHub:
    def __init__(self) -> None:
        self._versions: dict[str, int] = {}
        self._conditions: dict[str, asyncio.Condition] = {}

    def version(self, game_id: str) -> int:
        return self._versions.get(game_id, 0)

    async def notify(self, game_id: str) -> None:
        condition = self._conditions.setdefault(game_id, asyncio.Condition())
        async with condition:
            self._versions[game_id] = self.version(game_id) + 1
            condition.notify_all()

    async def wait(self, game_id: str, after: int, timeout: float = 15) -> int:
        condition = self._conditions.setdefault(game_id, asyncio.Condition())
        async with condition:
            await asyncio.wait_for(
                condition.wait_for(lambda: self.version(game_id) > after),
                timeout=timeout,
            )
        return self.version(game_id)


class ServerRuntime:
    def __init__(self, settings: ServerSettings) -> None:
        self.settings = settings
        self.store = ServerStore(settings.database)
        self.card_db = CardDatabase(settings.card_db)
        self.records = DirectoryGamePersistence(settings.game_root)
        self.idempotency = SqliteIdempotencyRepository(settings.database)
        self.persistence = _StoreGamePersistence(self.records, self.store)
        self.manager = GameManager()
        self.hub = ProjectionHub()
        self._load_lock = asyncio.Lock()

    async def actor(self, game_id: str) -> GameActor:
        try:
            return self.manager.get(game_id)
        except KeyError:
            pass
        async with self._load_lock:
            try:
                return self.manager.get(game_id)
            except KeyError:
                service = self.records.load(
                    self.card_db,
                    game_id,
                    idempotency=self.idempotency,
                )
                self.store.update_game_state(
                    game_id,
                    service.session.state.revision,
                    _server_game_status(service),
                )
                return await self.manager.add(
                    service, persistence=self.persistence
                )

    async def game_summary(
        self, game_id: str, guest_id: str
    ) -> dict[str, Any]:
        # Authorize before a request can cause a persisted game to be loaded.
        self.store.game_access(game_id, guest_id)
        actor = await self.actor(game_id)
        control = self.store.game_summary(game_id, guest_id)
        lifecycle = await actor.inspect()
        return {
            **control,
            **lifecycle,
            "can_stop": bool(
                control["owner"] and lifecycle["status"] == "active"
            ),
            "can_resume": bool(
                control["owner"]
                and lifecycle["status"] == "paused"
                and (lifecycle.get("pause_reason") or {}).get("kind")
                == "administrative_stop"
            ),
        }

    async def close(self) -> None:
        await self.manager.close()
        self.card_db.close()


def _bearer(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return request.cookies.get(COOKIE_NAME)


def _runtime(request: Request) -> ServerRuntime:
    return request.app.state.runtime


def _guest(
    request: Request,
    runtime: ServerRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        return runtime.store.authenticate(_bearer(request) or "")
    except StoreForbidden as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _csrf(
    request: Request,
    x_csrf_token: str | None = Header(default=None),
) -> None:
    if request.headers.get("authorization", "").startswith("Bearer "):
        return
    cookie = request.cookies.get(CSRF_COOKIE_NAME)
    if (
        not cookie
        or not x_csrf_token
        or not hmac.compare_digest(cookie, x_csrf_token)
    ):
        raise HTTPException(status_code=403, detail="CSRF token mismatch")


def _translate_store_error(exc: BaseException) -> HTTPException:
    if isinstance(exc, StoreForbidden):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, StoreNotFound):
        return HTTPException(status_code=404, detail=str(exc.args[0]))
    if isinstance(exc, StoreConflict):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


def _compact_preflight(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "trusted_only_ready": bool(report.get("trusted_only_ready")),
        "deck_review_eligible_possible": bool(
            report.get("deck_review_eligible_possible")
        ),
        "fully_playable_cards": report.get("fully_playable_cards"),
        "partial_cards": report.get("partial_cards"),
        "unresolved_cards": report.get("unresolved_cards"),
        "oracle_residual_gate_pass": bool(
            report.get("oracle_residual_gate_pass")
        ),
    }


def create_app(settings: ServerSettings | None = None) -> FastAPI:
    resolved = settings or ServerSettings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = ServerRuntime(resolved)
        app.state.runtime = runtime
        try:
            yield
        finally:
            await runtime.close()

    app = FastAPI(
        title="Commander Arena Server",
        version="0.8.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "authority": "server", "protocol": "3.0"}

    @app.post("/api/v1/guests", status_code=201)
    async def create_guest(
        body: GuestRequest,
        response: Response,
        runtime: ServerRuntime = Depends(_runtime),
    ) -> dict[str, Any]:
        guest, token = runtime.store.create_guest(body.display_name)
        csrf = secrets.token_urlsafe(24)
        response.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            secure=resolved.secure_cookies,
            samesite="strict",
            max_age=7 * 24 * 60 * 60,
            path="/",
        )
        response.set_cookie(
            CSRF_COOKIE_NAME,
            csrf,
            httponly=False,
            secure=resolved.secure_cookies,
            samesite="strict",
            max_age=7 * 24 * 60 * 60,
            path="/",
        )
        return {"guest": guest, "csrf_token": csrf, "access_token": token}

    @app.get("/api/v1/me")
    async def me(guest: dict[str, Any] = Depends(_guest)) -> dict[str, Any]:
        return {"guest": guest}

    @app.post("/api/v1/rooms", status_code=201, dependencies=[Depends(_csrf)])
    async def create_room(
        body: RoomRequest,
        guest: dict[str, Any] = Depends(_guest),
        runtime: ServerRuntime = Depends(_runtime),
    ) -> dict[str, Any]:
        seed = body.seed if body.seed is not None else secrets.randbits(63)
        room, invite = runtime.store.create_room(guest["guest_id"], seed=seed)
        return {"room": room, "invite_code": invite}

    @app.post("/api/v1/rooms/join", dependencies=[Depends(_csrf)])
    async def join_room(
        body: JoinRoomRequest,
        guest: dict[str, Any] = Depends(_guest),
        runtime: ServerRuntime = Depends(_runtime),
    ) -> dict[str, Any]:
        try:
            room = runtime.store.join_room(
                guest["guest_id"],
                invite_code=body.invite_code,
                seat=body.seat,
            )
        except (StoreForbidden, StoreNotFound, StoreConflict) as exc:
            raise _translate_store_error(exc) from exc
        return {"room": room}

    @app.get("/api/v1/rooms/{room_id}")
    async def get_room(
        room_id: str,
        guest: dict[str, Any] = Depends(_guest),
        runtime: ServerRuntime = Depends(_runtime),
    ) -> dict[str, Any]:
        try:
            return {"room": runtime.store.room(room_id, guest["guest_id"])}
        except (StoreForbidden, StoreNotFound) as exc:
            raise _translate_store_error(exc) from exc

    @app.put(
        "/api/v1/rooms/{room_id}/deck",
        dependencies=[Depends(_csrf)],
    )
    async def upload_deck(
        room_id: str,
        body: DeckRequest,
        guest: dict[str, Any] = Depends(_guest),
        runtime: ServerRuntime = Depends(_runtime),
    ) -> dict[str, Any]:
        try:
            loader = DeckLoader(
                runtime.card_db,
                cache_dir=runtime.settings.game_root.parent / "deck-cache",
            )
            if body.source_url:
                if not is_moxfield_source(body.source_url.strip()):
                    raise ValueError("source_url must be a public Moxfield deck URL")
                deck = loader.load(
                    body.source_url.strip(),
                    commander=body.commander.strip() or None,
                    deck_name=body.name.strip(),
                )
            else:
                deck = parse_deck_text(
                    body.decklist,
                    name=body.name.strip(),
                    commander=body.commander.strip(),
                    source="browser-upload",
                )
                loader.resolve_names(deck)
            issues = loader.validate_commander_deck(deck)
            if issues:
                raise StoreConflict("; ".join(issues))
            preflight = semantic_preflight(runtime.card_db, deck)
            saved = runtime.store.save_deck(
                guest["guest_id"],
                room_id,
                deck,
                fingerprint=deck_list_fingerprint(deck),
                preflight=preflight,
            )
        except (StoreForbidden, StoreNotFound, StoreConflict) as exc:
            raise _translate_store_error(exc) from exc
        except (KeyError, ValueError, MoxfieldFetchError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"deck": saved, "preflight": _compact_preflight(preflight)}

    @app.post(
        "/api/v1/rooms/{room_id}/start",
        dependencies=[Depends(_csrf)],
    )
    async def start_game(
        room_id: str,
        guest: dict[str, Any] = Depends(_guest),
        runtime: ServerRuntime = Depends(_runtime),
    ) -> dict[str, Any]:
        try:
            seed, decks = runtime.store.start_spec(room_id, guest["guest_id"])
            session = CommanderSession.create(
                runtime.card_db,
                decks,
                first_player="A",
                seed=seed,
                config=GameConfig(
                    seed=seed,
                    profile="commander_multiplayer",
                    review_profile="commander_review",
                ),
            )
            service = GameService(session, idempotency=runtime.idempotency)
            runtime.records.save(service)
            runtime.store.commit_started_game(
                room_id,
                session.state.game_id,
                str(runtime.records.game_directory(session.state.game_id)),
                session.state.revision,
            )
            await runtime.manager.add(service, persistence=runtime.persistence)
        except (StoreForbidden, StoreNotFound, StoreConflict) as exc:
            raise _translate_store_error(exc) from exc
        return {
            "game_id": session.state.game_id,
            "room_id": room_id,
            "profile": "commander_multiplayer",
            "state_revision": session.state.revision,
        }

    async def game_principal(
        game_id: str,
        guest: dict[str, Any],
        runtime: ServerRuntime,
    ) -> str:
        try:
            _, seat = runtime.store.game_access(game_id, guest["guest_id"])
        except (StoreForbidden, StoreNotFound) as exc:
            raise _translate_store_error(exc) from exc
        return f"pilot:{seat}"

    @app.get("/api/v1/games/{game_id}/state")
    async def game_state(
        game_id: str,
        full: bool = False,
        guest: dict[str, Any] = Depends(_guest),
        runtime: ServerRuntime = Depends(_runtime),
    ) -> dict[str, Any]:
        principal = await game_principal(game_id, guest, runtime)
        try:
            actor = await runtime.actor(game_id)
            return {
                "packet": await actor.observe(principal, full=full),
                "game": await runtime.game_summary(
                    game_id, guest["guest_id"]
                ),
            }
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/games/{game_id}")
    async def inspect_game(
        game_id: str,
        guest: dict[str, Any] = Depends(_guest),
        runtime: ServerRuntime = Depends(_runtime),
    ) -> dict[str, Any]:
        try:
            return {
                "game": await runtime.game_summary(
                    game_id, guest["guest_id"]
                )
            }
        except (StoreForbidden, StoreNotFound) as exc:
            raise _translate_store_error(exc) from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/games/{game_id}/stop",
        dependencies=[Depends(_csrf)],
    )
    async def stop_game(
        game_id: str,
        body: StopGameRequest,
        guest: dict[str, Any] = Depends(_guest),
        runtime: ServerRuntime = Depends(_runtime),
    ) -> dict[str, Any]:
        try:
            runtime.store.require_game_owner(game_id, guest["guest_id"])
            actor = await runtime.actor(game_id)
            result = await actor.pause(body.reason)
            if result["changed"]:
                await runtime.hub.notify(game_id)
            return {
                "game": await runtime.game_summary(
                    game_id, guest["guest_id"]
                )
            }
        except (StoreForbidden, StoreNotFound) as exc:
            raise _translate_store_error(exc) from exc
        except GameLifecycleConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/v1/games/{game_id}/resume",
        dependencies=[Depends(_csrf)],
    )
    async def resume_game(
        game_id: str,
        body: ResumeGameRequest,
        guest: dict[str, Any] = Depends(_guest),
        runtime: ServerRuntime = Depends(_runtime),
    ) -> dict[str, Any]:
        try:
            runtime.store.require_game_owner(game_id, guest["guest_id"])
            actor = await runtime.actor(game_id)
            result = await actor.resume()
            if result["changed"]:
                await runtime.hub.notify(game_id)
            return {
                "game": await runtime.game_summary(
                    game_id, guest["guest_id"]
                )
            }
        except (StoreForbidden, StoreNotFound) as exc:
            raise _translate_store_error(exc) from exc
        except GameLifecycleConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/v1/games/{game_id}/commands",
        dependencies=[Depends(_csrf)],
    )
    async def submit_command(
        game_id: str,
        request: Request,
        guest: dict[str, Any] = Depends(_guest),
        runtime: ServerRuntime = Depends(_runtime),
    ) -> dict[str, Any]:
        principal = await game_principal(game_id, guest, runtime)
        try:
            raw = await request.json()
            if not isinstance(raw, dict):
                raise ValueError("Command envelope must be an object")
            envelope = CommandEnvelope.from_mapping(raw)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        actor = await runtime.actor(game_id)
        receipt = await actor.command(principal, envelope)
        if receipt.ok and receipt.state_changed and not receipt.replayed:
            await runtime.hub.notify(game_id)
        return {"receipt": receipt.to_dict()}

    @app.websocket("/api/v1/games/{game_id}/stream")
    async def game_stream(websocket: WebSocket, game_id: str) -> None:
        runtime: ServerRuntime = websocket.app.state.runtime
        origin = websocket.headers.get("origin")
        if origin and origin not in resolved.allowed_origins:
            await websocket.close(code=1008, reason="Origin not allowed")
            return
        token = websocket.cookies.get(COOKIE_NAME) or ""
        try:
            guest = runtime.store.authenticate(token)
            _, seat = runtime.store.game_access(game_id, guest["guest_id"])
            actor = await runtime.actor(game_id)
        except (StoreForbidden, StoreNotFound, KeyError, ValueError):
            await websocket.close(code=1008, reason="Unauthorized")
            return
        principal = f"pilot:{seat}"
        cursor_key = f"network:{principal}:{uuid.uuid4().hex}"
        await websocket.accept()
        version = runtime.hub.version(game_id)
        try:
            packet = await actor.observe(
                principal, full=True, cursor_key=cursor_key
            )
            await websocket.send_json(
                {
                    "type": "projection",
                    "packet": packet,
                    "game": await runtime.game_summary(
                        game_id, guest["guest_id"]
                    ),
                }
            )
            receive_task = asyncio.create_task(websocket.receive())
            while True:
                hub_task = asyncio.create_task(
                    runtime.hub.wait(game_id, version)
                )
                try:
                    done, _ = await asyncio.wait(
                        {receive_task, hub_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if receive_task in done:
                        hub_task.cancel()
                        message = receive_task.result()
                        if message["type"] == "websocket.disconnect":
                            return
                        receive_task = asyncio.create_task(
                            websocket.receive()
                        )
                        continue
                    version = hub_task.result()
                    packet = await actor.observe(
                        principal, cursor_key=cursor_key
                    )
                    await websocket.send_json(
                        {
                            "type": "projection",
                            "packet": packet,
                            "game": await runtime.game_summary(
                                game_id, guest["guest_id"]
                            ),
                        },
                    )
                except TimeoutError:
                    await websocket.send_json(
                        {"type": "ping", "view_revision": packet["view_revision"]}
                    )
        except WebSocketDisconnect:
            return
        finally:
            for task in (locals().get("receive_task"), locals().get("hub_task")):
                if isinstance(task, asyncio.Task) and not task.done():
                    task.cancel()
            await actor.drop_projection_cursor(cursor_key)

    return app
