"""Word and collection identity.

This module is the single definition of when two vocabulary entries refer to the
same thing. Duplicate detection (FR-4.1), repository lookups (FR-8.9), and
practice answer matching (FR-6.4) all route through here, so the rule cannot
drift between code paths.
"""

from __future__ import annotations

__all__ = [
    "names_conflict",
    "natural_key",
    "normalize",
    "normalize_collection",
    "normalize_word",
]


def normalize(value: str) -> str:
    """Reduce a string to its identity form for caseless, space-tolerant matching.

    Three transformations are applied:

    1. Surrounding whitespace is stripped.
    2. Internal whitespace runs collapse to a single space, because the app
       stores phrases as well as single words -- ``"give  up"`` and ``"give up"``
       are the same phrase, and typing two spaces does not create a new entry.
    3. The result is case-folded. ``str.casefold`` rather than ``str.lower`` is
       used because it is the Unicode-correct operation for caseless comparison.

    Punctuation is deliberately preserved: ``"well"`` and ``"well,"`` remain
    distinct. Stripping it would be a guess about user intent, and the
    requirements specify only case and whitespace tolerance.
    """
    return " ".join(value.split()).casefold()


def normalize_word(value: str) -> str:
    """Identity form of a word or phrase."""
    return normalize(value)


def normalize_collection(value: str) -> str:
    """Identity form of a collection name."""
    return normalize(value)


def natural_key(word: str, collection_name: str) -> tuple[str, str]:
    """The composite identity of a vocabulary entry.

    ``(word, collection)`` is the natural key: the same word filed under two
    different collections is two legitimate entries, not a duplicate.
    """
    return (normalize_word(word), normalize_collection(collection_name))


def names_conflict(candidate: str, existing: str) -> bool:
    """Whether two collection names collide for uniqueness purposes.

    Callers compare a candidate against *other* collections, never against the
    collection being renamed. That is what makes recasing a collection's own name
    (for example ``"ielts"`` to ``"IELTS"``) permissible while still rejecting a
    collision with a different collection.
    """
    return normalize_collection(candidate) == normalize_collection(existing)
