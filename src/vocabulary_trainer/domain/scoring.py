"""Practice scoring and answer judgement.

Every rule here is pure arithmetic or a string comparison, which makes the
session's behaviour fully testable without a window, a pool, or a clock.
"""

from __future__ import annotations

from vocabulary_trainer.domain.natural_key import normalize

__all__ = [
    "answer_matches",
    "compute_score",
    "remaining_repetitions",
    "total_required_attempts",
]


def answer_matches(submitted: str, target: str) -> bool:
    """Judge a typed answer against the target word (FR-6.4).

    Reuses the natural-key normalizer, so answer matching and duplicate detection
    cannot drift apart. Case differences, surrounding padding, and collapsed
    internal whitespace all pass; a misspelling fails, which is the point of the
    drill.

    An empty submission normalizes to an empty string and so matches nothing. The
    drill screen additionally discards empty submissions before they reach here,
    so a stray Enter never costs a penalty.
    """
    return normalize(submitted) == normalize(target)


def compute_score(correct_attempts: int, penalties: int) -> int:
    """Session score: correct attempts minus penalties (FR-6.10).

    Negative results are returned as-is rather than clamped at zero. A user who
    has made more mistakes than correct answers is genuinely at a negative score,
    and the drill screen is required to display that honestly.
    """
    return correct_attempts - penalties


def remaining_repetitions(
    required_correct: int, correct_count: int, wrong_count: int
) -> int:
    """Correct answers still owed for one word, given its history so far.

    This is the "Number Of Repetitions" (NOR) rule: every wrong answer adds one
    more correct answer to the target, and every correct answer pays one off.
    Unlike the older streak-based mastery rule, a mistake's cost is not limited to
    score -- it also pushes the word's own finish line back by one, permanently
    (until a correct answer pays it down again). This applies while the word is
    still active in the pool; once the word is mastered its target is fixed and
    later attempts (there are none, since it left the pool) cannot reopen it.

    Uses running totals, not a consecutive streak: correct-wrong-correct-correct
    reaches the same remaining count as correct-correct-wrong-correct, because
    every correct answer counts toward the target regardless of what happened
    right before it. (The older streak rule cared about *consecutive* correct
    answers; this rule cares only about the running totals.)

    Floored at zero rather than allowed to go negative, so a lucky run of correct
    answers before any mistake cannot bank "credit" against future mistakes -- the
    word is simply mastered (see :func:`is_mastered`) the moment the count would
    reach zero, and mastery is a one-way gate exactly as it was before.
    """
    return max(0, required_correct + wrong_count - correct_count)


def is_mastered(required_correct: int, correct_count: int, wrong_count: int) -> bool:
    """Whether a word has satisfied the NOR rule and should leave the pool."""
    return remaining_repetitions(required_correct, correct_count, wrong_count) <= 0


def total_required_attempts(pool_size: int, required_correct: int) -> int:
    """Minimum correct attempts needed to master an entire pool (FR-6.3).

    This is the progress bar's denominator, computed once when the session starts
    and never recomputed. The pool shrinks as words are mastered; a live
    denominator would make the bar jump backwards.

    Because mistakes add attempts without adding progress, the number of attempts
    actually made can exceed this value. Clamping the displayed fraction to 100%
    is the presentation layer's job -- the raw counts are what the summary
    reports.
    """
    return pool_size * required_correct
