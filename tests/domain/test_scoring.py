"""Tests for answer judgement and scoring (FR-6.3, FR-6.4, FR-6.10)."""

from __future__ import annotations

import pytest

from vocabulary_trainer.domain.scoring import (
    answer_matches,
    compute_score,
    is_mastered,
    remaining_repetitions,
    total_required_attempts,
)


class TestAnswerMatches:
    def test_exact_match(self) -> None:
        assert answer_matches("ubiquitous", "ubiquitous") is True

    @pytest.mark.parametrize(
        "submitted",
        ["Ubiquitous", "UBIQUITOUS", "uBiQuItOuS"],
    )
    def test_case_insensitive(self, submitted: str) -> None:
        assert answer_matches(submitted, "ubiquitous") is True

    @pytest.mark.parametrize(
        "submitted",
        ["  ubiquitous", "ubiquitous  ", "  ubiquitous  ", "\tubiquitous\n"],
    )
    def test_ignores_surrounding_whitespace(self, submitted: str) -> None:
        assert answer_matches(submitted, "ubiquitous") is True

    def test_collapses_internal_whitespace_for_phrases(self) -> None:
        assert answer_matches("give  up", "give up") is True
        assert answer_matches("look   forward  to", "look forward to") is True

    @pytest.mark.parametrize(
        "submitted",
        ["curiousity", "ubiquitious", "ubiquitou", "ubiquitouss", "different"],
    )
    def test_misspellings_fail(self, submitted: str) -> None:
        """The whole point of the drill."""
        assert answer_matches(submitted, "ubiquitous") is False

    @pytest.mark.parametrize("submitted", ["", "   ", "\t"])
    def test_empty_submission_never_matches(self, submitted: str) -> None:
        assert answer_matches(submitted, "ubiquitous") is False

    def test_empty_target_matches_only_empty(self) -> None:
        assert answer_matches("", "") is True
        assert answer_matches("something", "") is False

    def test_punctuation_must_match(self) -> None:
        """Consistent with natural-key normalization, which preserves punctuation."""
        assert answer_matches("dont", "don't") is False
        assert answer_matches("don't", "don't") is True


class TestComputeScore:
    def test_all_correct(self) -> None:
        assert compute_score(10, 0) == 10

    def test_mixed(self) -> None:
        assert compute_score(35, 4) == 31

    def test_zero(self) -> None:
        assert compute_score(0, 0) == 0

    def test_balanced_is_zero(self) -> None:
        assert compute_score(5, 5) == 0

    def test_negative_is_not_clamped(self) -> None:
        """A user with more misses than hits is genuinely negative, and the drill
        screen must display that honestly (E6-S4 branch 2a)."""
        assert compute_score(2, 7) == -5

    def test_penalties_only(self) -> None:
        assert compute_score(0, 3) == -3


class TestRemainingRepetitions:
    """The NOR rule: required + wrong - correct, floored at zero."""

    def test_clean_start(self) -> None:
        assert remaining_repetitions(3, correct_count=0, wrong_count=0) == 3

    def test_first_requested_example(self) -> None:
        """NODR=3, one wrong answer overall -> NOR = 3 + 1 = 4."""
        assert remaining_repetitions(3, correct_count=0, wrong_count=1) == 4

    def test_second_requested_example(self) -> None:
        """NODR=3, one correct then two wrong -> NOR = 3 - 1 + 2 = 4."""
        assert remaining_repetitions(3, correct_count=1, wrong_count=2) == 4

    def test_order_of_correct_and_wrong_does_not_matter(self) -> None:
        """Running totals, not a consecutive streak: wrong-correct-wrong reaches
        the same remaining count as correct-wrong-wrong, since both have one
        correct_count and two wrong_count by the end."""
        assert remaining_repetitions(
            3, correct_count=1, wrong_count=2
        ) == remaining_repetitions(3, correct_count=1, wrong_count=2)

    def test_a_wrong_answer_after_reaching_the_original_target_still_costs(
        self,
    ) -> None:
        """3 correct answers would satisfy a required-3 session with no mistakes;
        one wrong answer along the way still adds exactly one repetition."""
        assert remaining_repetitions(3, correct_count=3, wrong_count=1) == 1

    def test_floored_at_zero_not_negative(self) -> None:
        """A run of correct answers cannot bank credit against future mistakes."""
        assert remaining_repetitions(3, correct_count=10, wrong_count=0) == 0

    def test_exactly_satisfied_reads_zero(self) -> None:
        assert remaining_repetitions(3, correct_count=3, wrong_count=0) == 0


class TestIsMastered:
    def test_not_yet(self) -> None:
        assert is_mastered(3, correct_count=2, wrong_count=0) is False

    def test_satisfied_exactly(self) -> None:
        assert is_mastered(3, correct_count=3, wrong_count=0) is True

    def test_a_miss_delays_it(self) -> None:
        assert is_mastered(3, correct_count=3, wrong_count=1) is False
        assert is_mastered(3, correct_count=4, wrong_count=1) is True

    def test_overshoot_still_counts(self) -> None:
        assert is_mastered(3, correct_count=99, wrong_count=0) is True


class TestTotalRequiredAttempts:
    def test_typical_session(self) -> None:
        assert total_required_attempts(170, 3) == 510

    def test_single_word_pool(self) -> None:
        assert total_required_attempts(1, 3) == 3

    def test_single_required_write(self) -> None:
        assert total_required_attempts(42, 1) == 42

    def test_maximum_threshold(self) -> None:
        assert total_required_attempts(10, 10) == 100

    def test_empty_pool_is_zero(self) -> None:
        """Defensive: the setup screen prevents starting an empty session, but the
        arithmetic must not blow up."""
        assert total_required_attempts(0, 3) == 0
