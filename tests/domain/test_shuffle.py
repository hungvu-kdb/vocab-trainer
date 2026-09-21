"""Tests for practice pool ordering (FR-5.9, FR-6.7)."""

from __future__ import annotations

import random
from collections import Counter

import pytest

from vocabulary_trainer.domain.shuffle import reinsert_avoiding_next, shuffled


class TestShuffled:
    def test_output_is_a_permutation_of_the_input(self) -> None:
        """No word may be lost or duplicated by shuffling."""
        pool = [f"word{i}" for i in range(50)]
        result = shuffled(pool, random.Random(1234))
        assert Counter(result) == Counter(pool)

    def test_does_not_mutate_the_caller_sequence(self) -> None:
        pool = ["a", "b", "c", "d"]
        original = list(pool)
        shuffled(pool, random.Random(7))
        assert pool == original

    def test_empty_pool(self) -> None:
        assert shuffled([], random.Random(1)) == []

    def test_single_element_pool(self) -> None:
        assert shuffled(["only"], random.Random(1)) == ["only"]

    def test_seeded_runs_are_deterministic(self) -> None:
        pool = list(range(20))
        assert shuffled(pool, random.Random(99)) == shuffled(pool, random.Random(99))

    def test_actually_reorders_a_large_pool(self) -> None:
        """Guards against a no-op implementation."""
        pool = list(range(100))
        assert shuffled(pool, random.Random(5)) != pool

    def test_accepts_a_tuple_and_returns_a_list(self) -> None:
        result = shuffled(("a", "b", "c"), random.Random(3))
        assert isinstance(result, list)
        assert Counter(result) == Counter(["a", "b", "c"])

    def test_preserves_duplicates(self) -> None:
        pool = ["a", "a", "b"]
        assert Counter(shuffled(pool, random.Random(2))) == Counter(pool)

    def test_works_without_an_explicit_rng(self) -> None:
        pool = list(range(10))
        assert Counter(shuffled(pool)) == Counter(pool)


class TestReinsertAvoidingNext:
    @pytest.mark.parametrize("seed", range(50))
    def test_never_lands_at_index_zero_when_others_remain(self, seed: int) -> None:
        """Index 0 is the next word drawn; reinserting there would show the user
        the word they just answered (FR-6.7)."""
        pool = ["a", "b", "c", "d"]
        reinsert_avoiding_next(pool, "recycled", random.Random(seed))
        assert pool[0] != "recycled"

    @pytest.mark.parametrize("seed", range(30))
    def test_single_other_word_places_it_second(self, seed: int) -> None:
        """With one other word, index 1 is the only valid position."""
        pool = ["other"]
        reinsert_avoiding_next(pool, "recycled", random.Random(seed))
        assert pool == ["other", "recycled"]

    def test_empty_pool_accepts_index_zero(self) -> None:
        """The word is the only one left, so immediate repeat is unavoidable and
        correct -- a single-word session must keep drawing it (E6-S3 branch 3a)."""
        pool: list[str] = []
        reinsert_avoiding_next(pool, "lonely", random.Random(1))
        assert pool == ["lonely"]

    def test_pool_grows_by_exactly_one(self) -> None:
        pool = ["a", "b", "c"]
        reinsert_avoiding_next(pool, "recycled", random.Random(11))
        assert len(pool) == 4

    def test_existing_items_are_all_retained(self) -> None:
        pool = ["a", "b", "c"]
        reinsert_avoiding_next(pool, "recycled", random.Random(11))
        assert Counter(pool) == Counter(["a", "b", "c", "recycled"])

    def test_appending_to_the_end_is_permitted(self) -> None:
        """Valid indices run to len(pool) inclusive, so the last slot is reachable."""
        landed_last = False
        for seed in range(200):
            pool = ["a", "b"]
            reinsert_avoiding_next(pool, "recycled", random.Random(seed))
            if pool[-1] == "recycled":
                landed_last = True
                break
        assert landed_last, "reinsertion should be able to place the word last"

    def test_reaches_every_valid_position_over_many_seeds(self) -> None:
        """Confirms the distribution is not stuck on one index."""
        seen: set[int] = set()
        for seed in range(300):
            pool = ["a", "b", "c"]
            reinsert_avoiding_next(pool, "recycled", random.Random(seed))
            seen.add(pool.index("recycled"))
        assert seen == {1, 2, 3}

    def test_works_without_an_explicit_rng(self) -> None:
        pool = ["a", "b"]
        reinsert_avoiding_next(pool, "recycled")
        assert len(pool) == 3
        assert pool[0] != "recycled"
