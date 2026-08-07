from __future__ import annotations

import copy
from typing import Sequence

from .model import DelayedTrigger, StackItem


def materialize_delayed_trigger(
    trigger: DelayedTrigger,
    *,
    ref: str,
    stack_id: str,
    visibility: Sequence[str],
) -> StackItem:
    """Create the public stack incarnation of one waiting delayed trigger."""

    template = trigger.stack_template
    return StackItem(
        stack_id=stack_id,
        ref=ref,
        kind="triggered_ability",
        controller=trigger.controller,
        label=str(template.get("label") or trigger.label),
        source_object_id=trigger.source_object_id,
        semantic_key=template.get("semantic_key"),
        targets=list(template.get("targets") or []),
        notes=str(template.get("note") or ""),
        visibility=list(visibility),
        context={
            **copy.deepcopy(dict(template.get("context") or {})),
            "delayed_trigger_ref": trigger.ref,
        },
        referred_object_ids=list(trigger.referred_object_ids),
    )


__all__ = ["materialize_delayed_trigger"]
