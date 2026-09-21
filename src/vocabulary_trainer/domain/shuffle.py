"""Practice pool ordering.

The pool is consumed from the front, so **index 0 is the next word drawn**. That
convention is what makes the reinsertion rule below meaningful.

Randomness is injected rather than sourced internally so tests are deterministic
with a seeded generator.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import TypeVar

__all__ = ["reinsert_avoiding_next", "shuffled"]

T = TypeVar("T")

_default_rng = random.Random()


def shuffled(pool: Sequence[T], rng: random.Random | None = None) -> list[T]:
    """Return a random permutation of ``pool`` (FR-5.9).

    The caller's sequence is never mutated. The result is always a true
    permutation -- same elements, same multiplicity -- so no word can be lost or
    duplicated by shuffling. Empty and single-element pools are valid inputs.
    """
    generator = rng if rng is not None else _default_rng
    result = list(pool)
    generator.shuffle(result)
    return result


def reinsert_avoiding_next(
    pool: list[T],
    item: T,
    rng: random.Random | None = None,
) -> None:
    """Put a not-yet-mastered word back into the pool, in place (FR-6.7).

    The word must not become the next one drawn, or the user would simply retype
    what they saw a second ago -- which teaches nothing. Valid positions are
    therefore ``1`` through ``len(pool)`` inclusive; the upper bound allows
    appending to the end.

    When the pool is empty the word is the only one left, so index 0 is
    unavoidable and it does repeat immediately. FR-6.7 scopes the rule to
    "provided at least one other word remains", and a single-word session must
    keep drawing that word rather than stalling.
    """
    if not pool:
        pool.append(item)
        return

    generator = rng if rng is not None else _default_rng
    pool.insert(generator.randint(1, len(pool)), item)
