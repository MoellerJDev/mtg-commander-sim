from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .aura import (
    AuraEntryChoiceRequired,
    AuraEntryOutcome,
    AuraRuleError,
    commit_aura_entry_attachment,
    is_aura_type_line,
    prepare_aura_entry,
)
from .model import CardInstance
from .replacement_effects import ReplacementChoiceRequired
from .semantic_runtime import (
    TokenCreationReplacementContext,
    default_token_creation_replacement_registry,
    resolve_token_creation_replacements,
)
from .trigger_processing import enqueue_trigger_batch


class TokenCreationError(ValueError):
    pass


class TokenCreationHost(Protocol):
    """Narrow mutation port for authoritative token creation."""

    state: Any
    card_db: Any
    semantics: Any

    @property
    def seats(self) -> list[str]: ...

    def _require_seat(self, seat: str, *, in_game: bool = False) -> Any: ...

    def _resolve_object(
        self, seat: str, ref: str, *, zones: set[str]
    ) -> Any: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def display_name(self, object_id: str) -> str: ...

    def semantic_program_is_current_trusted(self, program: Any) -> bool: ...

    def apnap_order(self, *, start: str | None = None) -> list[str]: ...

    def _next_zone_timestamp(self) -> int: ...

    def _next_ref(self, prefix: str) -> str: ...

    def _stable_runtime_id(self, namespace: str, value: str) -> str: ...

    def _initialize_intrinsic_entry_counters(self, card: CardInstance) -> None: ...

    def _refresh_world_supertype_timestamp(
        self, card: CardInstance, *, gained_at: int
    ) -> None: ...

    def _attack_target_details(
        self, attacker: str, target: str
    ) -> Mapping[str, Any] | None: ...

    def _log(
        self,
        actor: str | None,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
        *,
        visibility: Iterable[str] | None = None,
        importance: int = 1,
        changed_objects: Iterable[str] | None = None,
        changed_players: Iterable[str] | None = None,
    ) -> Any: ...

    def _dispatch_semantic_event(
        self,
        event_kind: str,
        context: Mapping[str, Any],
        *,
        trigger_batch: list[Any],
    ) -> Any: ...


_ATTACKING_FIELD = "attack" + "ing"
_REASON_FIELD = "rea" + "son"


def _creation_subject(
    host: TokenCreationHost,
    controller: str,
    *,
    name: str,
    quantity: int,
    copy_of: str | None,
    characteristics: Mapping[str, Any] | None,
) -> tuple[set[str], list[Any]]:
    if copy_of:
        copied_source = host._resolve_object(
            controller,
            str(copy_of),
            zones={"battlefield"},
        )
        created_types, _, _ = host._type_parts(
            str(
                host._effective_card_data(copied_source).get("type_line")
                or ""
            )
        )
    else:
        type_line = str(
            dict(characteristics or {}).get("type_line") or ""
        )
        if not type_line:
            try:
                type_line = host.card_db.lookup(name).type_line
            except KeyError:
                type_line = ""
        created_types, _, _ = host._type_parts(type_line)
    sources = (
        [
            host.state.cards[object_id]
            for object_id in list(
                host.state.players[controller].zones["battlefield"]
            )
            if host.state.cards[object_id].controller == controller
            and not host.state.cards[object_id].phased_out
        ]
        if quantity > 0
        else []
    )
    return created_types, sources


def _token_replacement_effects(
    host: TokenCreationHost,
    controller: str,
    created_types: set[str],
    sources: Sequence[Any],
) -> tuple[Any, ...]:
    registry = default_token_creation_replacement_registry()
    effects = []
    for source in sources:
        programs = host.semantics.runtime_handler_programs_for_oracle(
            source.oracle_id,
            active_zone="battlefield",
            event="token.create",
        )
        for program in programs:
            if not host.semantic_program_is_current_trusted(program):
                continue
            for descriptor_index, descriptor in enumerate(program.handlers):
                effects.append(
                    registry.replacement_effect(
                        descriptor,
                        TokenCreationReplacementContext(
                            source_ref=source.ref,
                            source_controller=source.controller,
                            event_controller=controller,
                            created_types=tuple(sorted(created_types)),
                            component_id=f"{program.key}:{descriptor_index}",
                        ),
                    )
                )
    return tuple(effects)


def _resolved_token_specs(
    host: TokenCreationHost,
    controller: str,
    *,
    quantity: int,
    token_specs: tuple[Mapping[str, Any], ...],
    created_types: set[str],
    replacement_effects: Sequence[Any],
    replacement_selections: Sequence[str | None],
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Any, ...]]:
    if quantity > 0 and replacement_effects:
        resolution = resolve_token_creation_replacements(
            event_id=(
                f"token.create:{host.state.revision}:"
                f"{host.state.event_sequence + 1}"
            ),
            controller=controller,
            tokens=token_specs,
            created_types=tuple(sorted(created_types)),
            effects=tuple(replacement_effects),
            apnap_order=host.apnap_order(),
            selections=tuple(replacement_selections),
        )
        if resolution.pending is not None:
            raise ReplacementChoiceRequired(
                batch=resolution.batch,
                effects=tuple(replacement_effects),
                pending=resolution.pending,
            )
        return resolution.tokens, resolution.journal
    if replacement_selections:
        raise TokenCreationError(
            "Replacement selections were supplied without an applicable "
            "token replacement"
        )
    return token_specs, ()


def _copied_token_identity(
    host: TokenCreationHost,
    controller: str,
    *,
    copy_of: Any,
    name: str,
    characteristics: Mapping[str, Any],
) -> tuple[str, str, str, dict[str, Any]]:
    original = host._resolve_object(
        controller,
        str(copy_of),
        zones={"battlefield"},
    )
    ref = host._next_ref("T")
    annotations = copy.deepcopy(original.annotations)
    annotations["copied_from"] = original.object_id
    overrides = dict(annotations.get("copy_overrides") or {})
    if name:
        overrides["name"] = name
    overrides.update(characteristics)
    annotations["copy_overrides"] = overrides
    return (
        ref,
        original.oracle_id,
        name or host.display_name(original.object_id),
        annotations,
    )


def _new_token_identity(
    host: TokenCreationHost,
    *,
    name: str,
    characteristics: Mapping[str, Any],
) -> tuple[str, str, str, dict[str, Any]]:
    ref = host._next_ref("T")
    try:
        record = host.card_db.lookup(name)
        oracle_id = record.oracle_id
        printed_name = record.name
    except KeyError:
        oracle_id = (
            "custom-token:"
            + host._stable_runtime_id("token-oracle", ref)
        )
        printed_name = name
    annotations = {
        "token_characteristics": copy.deepcopy(dict(characteristics))
    }
    if characteristics:
        annotations["copy_overrides"] = copy.deepcopy(
            dict(characteristics)
        )
    return ref, oracle_id, printed_name, annotations


def _preview_token_object(
    host: TokenCreationHost,
    controller: str,
    token_spec: Mapping[str, Any],
) -> CardInstance:
    """Build a nonauthoritative token object for entry preflight.

    No runtime IDs or refs are allocated here.  In particular, an Aura token
    prohibited by CR 303.4g must not consume object identity before the engine
    knows whether it can legally enter attached.
    """

    spec = dict(token_spec)
    characteristics = dict(spec.get("characteristics") or {})
    copy_of = spec.get("copy_of")
    raw_name = spec.get("name")
    name = str(raw_name) if raw_name is not None else ""
    if copy_of:
        original = host._resolve_object(
            controller,
            str(copy_of),
            zones={"battlefield"},
        )
        oracle_id = original.oracle_id
        printed_name = name or host.display_name(original.object_id)
        annotations = copy.deepcopy(original.annotations)
        overrides = dict(annotations.get("copy_overrides") or {})
        if name:
            overrides["name"] = name
        overrides.update(characteristics)
        annotations["copy_overrides"] = overrides
    else:
        if not name:
            name = "Token"
        try:
            record = host.card_db.lookup(name)
            oracle_id = record.oracle_id
            printed_name = record.name
        except KeyError:
            oracle_id = "custom-token:aura-entry-preview"
            printed_name = name
        annotations = {
            "token_characteristics": copy.deepcopy(characteristics),
        }
        if characteristics:
            annotations["copy_overrides"] = copy.deepcopy(
                characteristics
            )
    return CardInstance(
        object_id="aura-entry-preview",
        ref="aura-entry-preview",
        oracle_id=oracle_id,
        printed_name=printed_name,
        owner=controller,
        controller=controller,
        zone="outside",
        is_token=True,
        annotations=annotations,
        known_to=list(host.seats),
        revealed_to=list(host.seats),
    )


def _preflight_aura_token_specs(
    host: TokenCreationHost,
    controller: str,
    token_specs: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    prepared: list[Mapping[str, Any]] = []
    for raw_spec in token_specs:
        spec = dict(raw_spec)
        if int(spec.get("quantity", 1)) <= 0:
            prepared.append(spec)
            continue
        preview = _preview_token_object(host, controller, spec)
        data = host._effective_card_data(preview)
        if not is_aura_type_line(str(data.get("type_line") or "")):
            prepared.append(spec)
            continue
        try:
            plan = prepare_aura_entry(
                host,
                preview,
                oracle_text=str(data.get("oracle_text") or ""),
                controller=controller,
                target_ref=(
                    str(spec["aura_target_ref"])
                    if spec.get("aura_target_ref") is not None
                    else None
                ),
                resolving_as_spell=False,
            )
        except AuraEntryChoiceRequired as exc:
            raise TokenCreationError(
                "Aura token creation requires a legal attachment choice "
                "before any token is committed"
            ) from exc
        except AuraRuleError as exc:
            raise TokenCreationError(str(exc)) from exc
        if plan.outcome is AuraEntryOutcome.REMAIN_IN_ZONE:
            # Tokens are created directly on the battlefield.  If the Aura
            # cannot enter attached, CR 303.4g says it is not created.
            continue
        if plan.outcome is not AuraEntryOutcome.ENTER_ATTACHED:
            raise TokenCreationError(
                "Aura token entry produced an invalid preflight outcome"
            )
        spec["aura_target_ref"] = plan.target_ref
        prepared.append(spec)
    return tuple(prepared)


def _commit_token_object(
    host: TokenCreationHost,
    controller: str,
    *,
    ref: str,
    oracle_id: str,
    printed_name: str,
    annotations: Mapping[str, Any],
    zone_timestamp: int,
    tapped: bool,
    attacking: str | None,
    battle_protector: str | None,
    temporary_keywords: Sequence[str],
) -> str:
    object_id = host._stable_runtime_id("token-object", ref)
    card = CardInstance(
        object_id=object_id,
        ref=ref,
        oracle_id=oracle_id,
        printed_name=printed_name,
        owner=controller,
        controller=controller,
        zone="battlefield",
        is_token=True,
        zone_timestamp=zone_timestamp,
        tapped=tapped,
        temporary_keywords=list(temporary_keywords),
        annotations=copy.deepcopy(dict(annotations)),
        acquired_control_turn_count=host.state.players[
            controller
        ].turns_begun,
        entered_battlefield_turn_sequence=host.state.turn_sequence,
        known_to=list(host.seats),
        revealed_to=list(host.seats),
        attacking=attacking,
        battle_protector=battle_protector,
    )
    host.state.cards[object_id] = card
    host.state.players[controller].zones["battlefield"].append(object_id)
    host._initialize_intrinsic_entry_counters(card)
    host._refresh_world_supertype_timestamp(
        card,
        gained_at=card.zone_timestamp,
    )
    if attacking:
        host.state.combat.attackers[object_id] = attacking
        target_details = host._attack_target_details(controller, attacking)
        if target_details is not None:
            host.state.combat.attack_target_context[object_id] = target_details
    return object_id


def _commit_token_specs(
    host: TokenCreationHost,
    controller: str,
    token_specs: Sequence[Mapping[str, Any]],
    *,
    creation_timestamp: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    created: list[str] = []
    applied_components: list[dict[str, Any]] = []
    for token_spec in token_specs:
        spec = dict(token_spec)
        spec_quantity = int(spec.get("quantity", 1))
        if spec_quantity < 0:
            raise TokenCreationError(
                "Replacement token quantity cannot be negative"
            )
        characteristics = dict(spec.get("characteristics") or {})
        copy_of = spec.get("copy_of")
        raw_name = spec.get("name")
        name = str(raw_name) if raw_name is not None else ""
        if not copy_of and not name:
            name = "Token"
        tapped = bool(spec.get("tapped", False))
        attacking = spec.get(_ATTACKING_FIELD)
        battle_protector = spec.get("battle_protector")
        keywords = list(spec.get("temporary_keywords", ()))
        component = spec.get("replacement_component")
        if isinstance(component, Mapping):
            applied_components.append(dict(component))
        for _ in range(spec_quantity):
            if copy_of:
                identity = _copied_token_identity(
                    host,
                    controller,
                    copy_of=copy_of,
                    name=name,
                    characteristics=characteristics,
                )
            else:
                identity = _new_token_identity(
                    host,
                    name=name,
                    characteristics=characteristics,
                )
            object_id = _commit_token_object(
                host,
                controller,
                ref=identity[0],
                oracle_id=identity[1],
                printed_name=identity[2],
                annotations=identity[3],
                zone_timestamp=creation_timestamp,
                tapped=tapped,
                attacking=attacking,
                battle_protector=battle_protector,
                temporary_keywords=keywords,
            )
            created.append(object_id)
            aura_target_ref = spec.get("aura_target_ref")
            if aura_target_ref is not None:
                token = host.state.cards[object_id]
                data = host._effective_card_data(token)
                try:
                    plan = prepare_aura_entry(
                        host,
                        token,
                        oracle_text=str(data.get("oracle_text") or ""),
                        controller=controller,
                        target_ref=str(aura_target_ref),
                        resolving_as_spell=False,
                    )
                    commit_aura_entry_attachment(host, token, plan)
                except AuraRuleError as exc:
                    raise TokenCreationError(str(exc)) from exc
    return created, applied_components


def _record_and_dispatch_token_creation(
    host: TokenCreationHost,
    controller: str,
    created: Sequence[str],
    *,
    name: str,
    base_quantity: int,
    replacement_components: Sequence[Mapping[str, Any]],
    replacement_journal: Sequence[Any],
    reason: str,
) -> None:
    tracker = host.state.players[controller].stats.setdefault(
        "tokens_created_by_turn", {}
    )
    turn_key = str(host.state.turn_sequence)
    tracker[turn_key] = int(tracker.get(turn_key, 0)) + len(created)
    host._log(
        controller,
        "token.create",
        f"{controller} created {len(created)} token(s).",
        {
            "objects": [
                host.state.cards[object_id].ref for object_id in created
            ],
            "base_name": name,
            "base_quantity": base_quantity,
            "replacement_count": len(created) - base_quantity,
            "replacement_components": [
                dict(value) for value in replacement_components
            ],
            "replacement_order": [
                selection.effect_id for selection in replacement_journal
            ],
            _REASON_FIELD: reason,
        },
        importance=1,
        changed_objects=created,
        changed_players=[controller],
    )
    trigger_batch: list[Any] = []
    for object_id in created:
        card = host.state.cards[object_id]
        data = host._effective_card_data(card)
        types, _, _ = host._type_parts(str(data.get("type_line") or ""))
        context = {
            "card": card.ref,
            "controller": controller,
            "owner": controller,
            "from": "outside",
            "to": "battlefield",
            "types": sorted(types),
            "mana_value": float(data.get("mana_value", 0) or 0),
            "token": True,
            "tapped": card.tapped,
            _REASON_FIELD: reason,
        }
        host._dispatch_semantic_event(
            "token.created", context, trigger_batch=trigger_batch
        )
        host._dispatch_semantic_event(
            "permanent.enter", context, trigger_batch=trigger_batch
        )
        for card_type in ("artifact", "creature", "land", "enchantment"):
            if card_type in types:
                host._dispatch_semantic_event(
                    f"{card_type}.enter",
                    context,
                    trigger_batch=trigger_batch,
                )
    enqueue_trigger_batch(host, trigger_batch)


def create_tokens(
    host: TokenCreationHost,
    controller: str,
    *,
    name: str,
    quantity: int = 1,
    tapped: bool = False,
    attacking: str | None = None,
    battle_protector: str | None = None,
    copy_of: str | None = None,
    characteristics: Mapping[str, Any] | None = None,
    temporary_keywords: Sequence[str] = (),
    aura_target_ref: str | None = None,
    reason: str = "token effect",
    replacement_selections: Sequence[str | None] = (),
) -> list[str]:
    """Resolve creation replacements, commit tokens, and emit enter events."""

    host._require_seat(controller, in_game=True)
    if quantity < 0:
        raise TokenCreationError("Token quantity cannot be negative")
    created_types, sources = _creation_subject(
        host,
        controller,
        name=name,
        quantity=quantity,
        copy_of=copy_of,
        characteristics=characteristics,
    )
    replacement_effects = _token_replacement_effects(
        host,
        controller,
        created_types,
        sources,
    )
    token_specs, replacement_journal = _resolved_token_specs(
        host,
        controller,
        quantity=quantity,
        token_specs=(
            {
                "name": name,
                "quantity": quantity,
                "tapped": tapped,
                _ATTACKING_FIELD: attacking,
                "battle_protector": battle_protector,
                "copy_of": copy_of,
                "characteristics": copy.deepcopy(
                    dict(characteristics or {})
                ),
                "temporary_keywords": list(temporary_keywords),
                "aura_target_ref": aura_target_ref,
            },
        ),
        created_types=created_types,
        replacement_effects=replacement_effects,
        replacement_selections=replacement_selections,
    )
    token_specs = _preflight_aura_token_specs(
        host,
        controller,
        token_specs,
    )
    creation_timestamp = (
        host._next_zone_timestamp() if token_specs else 0
    )
    created, applied_components = _commit_token_specs(
        host,
        controller,
        token_specs,
        creation_timestamp=creation_timestamp,
    )
    _record_and_dispatch_token_creation(
        host,
        controller,
        created,
        name=name,
        base_quantity=quantity,
        replacement_components=applied_components,
        replacement_journal=replacement_journal,
        reason=reason,
    )
    return [host.state.cards[object_id].ref for object_id in created]
