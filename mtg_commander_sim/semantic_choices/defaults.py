from __future__ import annotations

from functools import lru_cache

from .registry import SemanticChoiceRegistry
from .object_selection import OBJECT_SELECTION_HANDLERS
from .ordering import ORDERING_CHOICE_HANDLERS
from .payments import PAYMENT_CHOICE_HANDLERS
from .scalar import SCALAR_CHOICE_HANDLERS
from .stack_targets import STACK_TARGET_CHOICE_HANDLERS
from .token_and_copy import TOKEN_AND_COPY_CHOICE_HANDLERS


@lru_cache(maxsize=1)
def default_semantic_choice_registry() -> SemanticChoiceRegistry:
    return SemanticChoiceRegistry(
        (
            *SCALAR_CHOICE_HANDLERS,
            *OBJECT_SELECTION_HANDLERS,
            *ORDERING_CHOICE_HANDLERS,
            *PAYMENT_CHOICE_HANDLERS,
            *STACK_TARGET_CHOICE_HANDLERS,
            *TOKEN_AND_COPY_CHOICE_HANDLERS,
        )
    ).freeze()
