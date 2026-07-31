from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from .service import CommandEnvelope, CommandReceipt, GameService


class GameActorClosed(RuntimeError):
    pass


class GameActorUnavailable(RuntimeError):
    """Raised after an actor can no longer promise durable acknowledgements."""


class GamePersistence(Protocol):
    def save(self, service: GameService) -> None: ...


@dataclass(slots=True)
class _ActorMessage:
    kind: Literal["observe", "drop_cursor", "command", "poll", "stop"]
    future: asyncio.Future[Any]
    principal: str | None = None
    full: bool = False
    cursor_key: str | None = None
    envelope: CommandEnvelope | None = None


class GameActor:
    """One serialized mailbox and writer for one active game."""

    def __init__(
        self,
        service: GameService,
        *,
        persistence: GamePersistence | None = None,
        queue_limit: int = 256,
    ) -> None:
        if queue_limit < 1:
            raise ValueError("queue_limit must be positive")
        self.service = service
        self.game_id = service.session.state.game_id
        self.persistence = persistence
        self._mailbox: asyncio.Queue[_ActorMessage] = asyncio.Queue(
            maxsize=queue_limit
        )
        self._worker: asyncio.Task[None] | None = None
        self._closed = False
        self._failure: BaseException | None = None
        self.processed_messages = 0

    @property
    def queue_depth(self) -> int:
        return self._mailbox.qsize()

    async def start(self) -> None:
        if self._closed:
            raise GameActorClosed(f"Game actor {self.game_id} is closed")
        if self._failure is not None:
            raise GameActorUnavailable(
                f"Game actor {self.game_id} requires recovery"
            )
        if self._worker is None:
            self._worker = asyncio.create_task(
                self._run(), name=f"game-actor:{self.game_id}"
            )

    async def _request(self, message: _ActorMessage) -> Any:
        await self.start()
        await self._mailbox.put(message)
        return await message.future

    async def observe(
        self,
        principal: str,
        *,
        full: bool = False,
        cursor_key: str | None = None,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await self._request(
            _ActorMessage(
                kind="observe",
                future=loop.create_future(),
                principal=principal,
                full=full,
                cursor_key=cursor_key,
            )
        )

    async def drop_projection_cursor(self, cursor_key: str) -> None:
        loop = asyncio.get_running_loop()
        await self._request(
            _ActorMessage(
                kind="drop_cursor",
                future=loop.create_future(),
                cursor_key=cursor_key,
            )
        )

    async def command(
        self, principal: str, envelope: CommandEnvelope
    ) -> CommandReceipt:
        loop = asyncio.get_running_loop()
        return await self._request(
            _ActorMessage(
                kind="command",
                future=loop.create_future(),
                principal=principal,
                envelope=envelope,
            )
        )

    async def poll(self) -> list[str]:
        loop = asyncio.get_running_loop()
        return await self._request(
            _ActorMessage(kind="poll", future=loop.create_future())
        )

    async def _run(self) -> None:
        while True:
            message = await self._mailbox.get()
            try:
                if message.kind == "stop":
                    if not message.future.done():
                        message.future.set_result(None)
                    return
                if self._failure is not None:
                    raise GameActorUnavailable(
                        f"Game actor {self.game_id} requires recovery"
                    )
                if message.kind == "observe":
                    result = self.service.observe(
                        str(message.principal),
                        full=message.full,
                        cursor_key=message.cursor_key,
                    )
                elif message.kind == "drop_cursor":
                    if message.cursor_key is None:
                        raise RuntimeError("Projection cursor key is missing")
                    self.service.drop_projection_cursor(message.cursor_key)
                    result = None
                elif message.kind == "command":
                    if message.envelope is None:
                        raise RuntimeError("Command message is missing envelope")
                    result = self.service.command(
                        message.envelope,
                        principal=str(message.principal),
                        commit_idempotency=False,
                    )
                    if (
                        result.ok
                        and result.state_changed
                        and not result.replayed
                        and self.persistence is not None
                    ):
                        self.persistence.save(self.service)
                    if not result.replayed:
                        self.service.remember(
                            message.envelope,
                            str(message.principal),
                            result,
                        )
                elif message.kind == "poll":
                    result = self.service.poll()
                else:  # pragma: no cover - Literal and constructor guard this.
                    raise RuntimeError(f"Unknown actor message {message.kind}")
                self.processed_messages += 1
                if not message.future.done():
                    message.future.set_result(result)
            except BaseException as exc:
                response_exception = exc
                if message.kind == "command" and not isinstance(
                    exc, GameActorUnavailable
                ):
                    # A command exception can occur after in-memory mutation
                    # but before durable save/idempotency completion. Stop all
                    # further traffic until a fresh actor reloads durable state.
                    self._failure = exc
                    response_exception = GameActorUnavailable(
                        f"Game actor {self.game_id} failed durable command "
                        "commit and requires recovery"
                    )
                if not message.future.done():
                    message.future.set_exception(response_exception)
            finally:
                self._mailbox.task_done()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        worker = self._worker
        if worker is None:
            return
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        await self._mailbox.put(
            _ActorMessage(kind="stop", future=future)
        )
        await future
        await worker
        self._worker = None


class GameManager:
    """Own the unique actor route for every active in-process game."""

    def __init__(self) -> None:
        self._actors: dict[str, GameActor] = {}
        self._lock = asyncio.Lock()

    async def add(
        self,
        service: GameService,
        *,
        persistence: GamePersistence | None = None,
    ) -> GameActor:
        game_id = service.session.state.game_id
        async with self._lock:
            if game_id in self._actors:
                raise ValueError(f"Game {game_id} already has an actor")
            actor = GameActor(service, persistence=persistence)
            self._actors[game_id] = actor
        await actor.start()
        return actor

    def get(self, game_id: str) -> GameActor:
        try:
            return self._actors[game_id]
        except KeyError as exc:
            raise KeyError(f"Unknown active game {game_id}") from exc

    async def remove(self, game_id: str) -> None:
        async with self._lock:
            actor = self._actors.pop(game_id, None)
        if actor is not None:
            await actor.close()

    async def close(self) -> None:
        async with self._lock:
            actors = list(self._actors.values())
            self._actors.clear()
        await asyncio.gather(*(actor.close() for actor in actors))

    @property
    def game_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._actors))
