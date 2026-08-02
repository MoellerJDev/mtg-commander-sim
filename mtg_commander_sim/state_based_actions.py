from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable, Mapping

from .commander import commander_damage_losers
from .model import GameState


_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_COUNTER_MAXIMUM_PATTERN = re.compile(
    r"\bcan['’]t have more than "
    r"(?P<count>\d+|zero|one|two|three|four|five|six|seven|eight|"
    r"nine|ten) "
    r"(?P<kind>[a-z0-9+/\- ]+?) counters? on (?:it|him|her)\b",
    re.IGNORECASE,
)


def counter_maximums_from_oracle(
    oracle_text: str,
) -> dict[str, int]:
    """Extract the reviewed CR 704.5r maximum-counter sentence family."""

    maximums: dict[str, int] = {}
    for match in _COUNTER_MAXIMUM_PATTERN.finditer(str(oracle_text or "")):
        raw_count = match.group("count").casefold()
        count = (
            int(raw_count)
            if raw_count.isdigit()
            else _NUMBER_WORDS[raw_count]
        )
        kind = " ".join(
            match.group("kind").casefold().split()
        )
        if kind:
            maximums[kind] = min(
                maximums.get(kind, count),
                count,
            )
    return maximums


def player_loss_seats(
    state: GameState,
    active_seats: Iterable[str],
) -> tuple[str, ...]:
    """Evaluate the implemented CR 704 player-loss conditions together."""

    commander_losers = set(commander_damage_losers(state))
    return tuple(
        seat
        for seat in active_seats
        if (
            state.players[seat].life <= 0
            or state.players[seat].poison >= state.config.poison_to_lose
            or state.players[seat].attempted_empty_draw
            or seat in commander_losers
        )
    )


@dataclass(frozen=True, slots=True)
class PermanentSnapshot:
    """The derived public state needed for one CR 704.5 check.

    Callers must construct every snapshot from the same game state.  The
    evaluator is deliberately pure so detection cannot depend on battlefield
    iteration order or on mutations made while another state-based action is
    being discovered.
    """

    object_id: str
    card_types: frozenset[str] = frozenset()
    subtypes: frozenset[str] = frozenset()
    toughness: int | None = None
    marked_damage: int = 0
    deathtouch_damage: bool = False
    indestructible: bool = False
    loyalty: int | None = None
    defense: int | None = None
    battle_trigger_pending: bool = False
    world: bool = False
    world_timestamp: int | None = None
    attached_to: str | None = None
    attachment_legal: bool | None = None
    counters: Mapping[str, int] = field(default_factory=dict)
    counter_maximums: Mapping[str, int] = field(
        default_factory=dict
    )


@dataclass(frozen=True, slots=True)
class ObjectSnapshot:
    """The object-kind and zone facts needed for CR 704.5d-e."""

    object_id: str
    zone: str
    is_token: bool = False
    is_spell_copy: bool = False
    is_card_copy: bool = False


@dataclass(frozen=True, slots=True)
class StateBasedActionBatch:
    """All deterministic permanent actions found in one CR 704.3 check."""

    put_in_graveyard: tuple[str, ...] = ()
    destroy: tuple[str, ...] = ()
    detach: tuple[str, ...] = ()
    counter_pairs_to_remove: tuple[tuple[str, int], ...] = ()
    counter_maximums_to_remove: tuple[
        tuple[str, str, int], ...
    ] = ()
    cease: tuple[str, ...] = ()
    world_rule: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(
            self.put_in_graveyard
            or self.destroy
            or self.detach
            or self.counter_pairs_to_remove
            or self.counter_maximums_to_remove
            or self.cease
            or self.world_rule
        )


def evaluate_permanent_state_based_actions(
    permanents: Iterable[PermanentSnapshot],
) -> StateBasedActionBatch:
    """Evaluate the deterministic battlefield subset of CR 704.5.

    The result distinguishes non-destruction graveyard moves from destruction
    so the engine can eventually route regeneration and other replacements
    correctly.  Unknown attachment legality is intentionally not guessed.
    """

    put_in_graveyard: set[str] = set()
    destroy: set[str] = set()
    detach: set[str] = set()
    counter_pairs: dict[str, int] = {}
    counter_maximums: dict[tuple[str, str], int] = {}
    world_permanents: list[PermanentSnapshot] = []

    for permanent in permanents:
        card_types = {
            str(value).casefold() for value in permanent.card_types
        }
        subtypes = {
            str(value).casefold() for value in permanent.subtypes
        }
        is_creature = "creature" in card_types
        is_battle = "battle" in card_types
        is_aura = "aura" in subtypes
        is_equipment = "equipment" in subtypes
        is_fortification = "fortification" in subtypes
        if permanent.world:
            if permanent.world_timestamp is None:
                raise ValueError(
                    "World permanent requires a World-since timestamp"
                )
            world_permanents.append(permanent)

        if is_creature and permanent.toughness is not None:
            if permanent.toughness <= 0:
                put_in_graveyard.add(permanent.object_id)
            elif (
                permanent.marked_damage >= permanent.toughness
                or permanent.deathtouch_damage
            ) and not permanent.indestructible:
                destroy.add(permanent.object_id)

        if (
            "planeswalker" in card_types
            and permanent.loyalty is not None
            and permanent.loyalty <= 0
        ):
            put_in_graveyard.add(permanent.object_id)

        if (
            is_battle
            and permanent.defense is not None
            and permanent.defense <= 0
            and not permanent.battle_trigger_pending
        ):
            put_in_graveyard.add(permanent.object_id)

        # A creature or battle cannot legally remain attached.  If that
        # permanent is also an Aura, CR 704.5m and 704.5p apply together; the
        # Aura graveyard action wins over emitting a redundant detach.
        self_cannot_be_attached = is_battle or is_creature
        if is_aura and (
            permanent.attached_to is None
            or permanent.attachment_legal is False
            or self_cannot_be_attached
        ):
            put_in_graveyard.add(permanent.object_id)

        if permanent.attached_to is not None:
            if (is_equipment or is_fortification) and (
                permanent.attachment_legal is False
            ):
                detach.add(permanent.object_id)
            if is_battle or is_creature or not (
                is_aura or is_equipment or is_fortification
            ):
                detach.add(permanent.object_id)

        positive = max(
            0, int(permanent.counters.get("+1/+1", 0))
        )
        negative = max(
            0, int(permanent.counters.get("-1/-1", 0))
        )
        if positive and negative:
            counter_pairs[permanent.object_id] = min(
                positive, negative
            )
        for raw_kind, raw_maximum in permanent.counter_maximums.items():
            kind = " ".join(str(raw_kind).casefold().split())
            maximum = int(raw_maximum)
            if not kind or maximum < 0:
                raise ValueError(
                    "Counter maximums require a kind and "
                    "nonnegative value"
                )
            current = max(
                0, int(permanent.counters.get(kind, 0))
            )
            if current > maximum:
                counter_maximums[
                    (permanent.object_id, kind)
                ] = current - maximum

    world_rule: set[str] = set()
    if len(world_permanents) >= 2:
        newest_timestamp = max(
            int(permanent.world_timestamp)
            for permanent in world_permanents
        )
        newest = [
            permanent
            for permanent in world_permanents
            if int(permanent.world_timestamp) == newest_timestamp
        ]
        if len(newest) == 1:
            world_rule.update(
                permanent.object_id
                for permanent in world_permanents
                if permanent is not newest[0]
            )
        else:
            # CR 704.5k: if the shortest-held duration is tied, every World
            # permanent goes to its owner's graveyard.
            world_rule.update(
                permanent.object_id
                for permanent in world_permanents
            )

    # A permanent moving zones is detached as part of that zone change.  Do
    # not emit a second independent detach operation for the same object.
    moving = put_in_graveyard | destroy | world_rule
    return StateBasedActionBatch(
        put_in_graveyard=tuple(sorted(put_in_graveyard)),
        destroy=tuple(sorted(destroy - put_in_graveyard)),
        detach=tuple(sorted(detach - moving)),
        counter_pairs_to_remove=tuple(sorted(counter_pairs.items())),
        counter_maximums_to_remove=tuple(
            (
                object_id,
                kind,
                count,
            )
            for (object_id, kind), count in sorted(
                counter_maximums.items()
            )
        ),
        world_rule=tuple(sorted(world_rule)),
    )


def evaluate_state_based_actions(
    *,
    permanents: Iterable[PermanentSnapshot],
    objects: Iterable[ObjectSnapshot],
) -> StateBasedActionBatch:
    """Evaluate the implemented CR 704 object and permanent subset.

    Every input must be captured from the same authoritative state.  Tokens
    and noncard copies cease to exist; they do not move to ``outside`` as a
    second zone-change event.
    """

    permanent_batch = evaluate_permanent_state_based_actions(permanents)
    cease: set[str] = set()
    for value in objects:
        zone = str(value.zone).casefold()
        if zone == "outside":
            continue
        if value.is_token and zone != "battlefield":
            cease.add(value.object_id)
        if value.is_spell_copy and zone != "stack":
            cease.add(value.object_id)
        if (
            value.is_card_copy
            and zone not in {"stack", "battlefield"}
        ):
            cease.add(value.object_id)
    return StateBasedActionBatch(
        put_in_graveyard=permanent_batch.put_in_graveyard,
        destroy=permanent_batch.destroy,
        detach=permanent_batch.detach,
        counter_pairs_to_remove=(
            permanent_batch.counter_pairs_to_remove
        ),
        counter_maximums_to_remove=(
            permanent_batch.counter_maximums_to_remove
        ),
        cease=tuple(sorted(cease)),
        world_rule=permanent_batch.world_rule,
    )
