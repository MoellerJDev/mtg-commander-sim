from __future__ import annotations

from functools import lru_cache

from .registry import SemanticChoiceRegistry
from .artifact_exchange import ARTIFACT_EXCHANGE_CHOICE_HANDLERS
from .object_selection import OBJECT_SELECTION_HANDLERS
from .library_and_hand import LIBRARY_AND_HAND_CHOICE_HANDLERS
from .ordering import ORDERING_CHOICE_HANDLERS
from .payments import PAYMENT_CHOICE_HANDLERS
from .public_selection import PUBLIC_SELECTION_CHOICE_HANDLERS
from .scalar import SCALAR_CHOICE_HANDLERS
from .stack_targets import STACK_TARGET_CHOICE_HANDLERS
from .token_and_copy import TOKEN_AND_COPY_CHOICE_HANDLERS
from .damage_prevention import DAMAGE_PREVENTION_CHOICE_HANDLERS
from .conditional_draw import CONDITIONAL_DRAW_CHOICE_HANDLERS


@lru_cache(maxsize=1)
def default_semantic_choice_registry() -> SemanticChoiceRegistry:
    return SemanticChoiceRegistry(
        (
            *ARTIFACT_EXCHANGE_CHOICE_HANDLERS,
            *SCALAR_CHOICE_HANDLERS,
            *OBJECT_SELECTION_HANDLERS,
            *LIBRARY_AND_HAND_CHOICE_HANDLERS,
            *ORDERING_CHOICE_HANDLERS,
            *PAYMENT_CHOICE_HANDLERS,
            *PUBLIC_SELECTION_CHOICE_HANDLERS,
            *STACK_TARGET_CHOICE_HANDLERS,
            *TOKEN_AND_COPY_CHOICE_HANDLERS,
            *DAMAGE_PREVENTION_CHOICE_HANDLERS,
            *CONDITIONAL_DRAW_CHOICE_HANDLERS,
        )
    ).freeze()
