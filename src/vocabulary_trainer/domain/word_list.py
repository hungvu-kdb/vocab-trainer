"""Splitting a comma-separated entry into individual words (FR-2.12).

Pure text handling, so it lives here and is exhaustively testable without a UI.

The rules are deliberately forgiving, because this input is typed quickly while the
user is mid-task: empty fragments from a trailing or doubled comma are dropped
rather than rejected, and a repeat inside one entry collapses instead of raising.
Refusing the whole batch over a stray comma would cost the user everything they had
just typed.
"""

from __future__ import annotations

from vocabulary_trainer.domain.natural_key import normalize_word

__all__ = ["SEPARATOR", "parse_word_list"]

SEPARATOR = ","
"""What separates words in a multi-word entry.

Comma only, as specified. Newlines and semicolons are *not* treated as separators:
the input is a single-line field, and guessing at other delimiters would make
"e.g. this; that" ambiguous.
"""


def parse_word_list(text: str) -> list[str]:
    """Split ``text`` on commas into trimmed, lowercased, de-duplicated words.

    Each fragment is stripped of surrounding whitespace, has internal whitespace
    runs collapsed, and is lowercased -- so ``"Hello,  GIVE  UP ,hello"`` yields
    ``["hello", "give up"]``.

    Lowercasing is applied on purpose (the user asked for it) and is worth knowing
    about: it means proper nouns entered in a batch lose their capitals. Phrases keep
    their internal single spaces, since the app stores phrases as first-class
    entries.

    Order is the order typed, with each word's *first* occurrence kept. That matters
    for a reviewable result: the confirmation the user sees should list words in the
    order they wrote them, not in an arbitrary set order.

    De-duplication uses :func:`normalize_word`, the app's one definition of word
    identity, so ``"Hello"`` and ``"hello  "`` collapse for exactly the same reason
    they would be treated as duplicates in the workbook.
    """
    seen: set[str] = set()
    words: list[str] = []

    for fragment in text.split(SEPARATOR):
        # normalize_word already strips, collapses internal whitespace and casefolds.
        # Reusing it rather than hand-rolling the same three operations keeps this
        # consistent with duplicate detection, which is the whole point of matching
        # its behaviour here.
        cleaned = normalize_word(fragment)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        words.append(cleaned)

    return words


def looks_like_multiple(text: str) -> bool:
    """Whether ``text`` contains more than one word once parsed.

    Used to decide whether a confirmation is worth showing. A single word typed into
    the multi-word field should behave exactly like the normal single-word flow, with
    no extra ceremony.
    """
    return len(parse_word_list(text)) > 1
