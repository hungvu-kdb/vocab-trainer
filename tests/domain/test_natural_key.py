"""Tests for word and collection identity (FR-8.9, FR-2.5, FR-7.8)."""

from __future__ import annotations

import pytest

from vocabulary_trainer.domain.natural_key import (
    names_conflict,
    natural_key,
    normalize,
)


class TestNormalize:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ubiquitous", "ubiquitous"),
            ("  ubiquitous  ", "ubiquitous"),
            ("\tubiquitous\n", "ubiquitous"),
            ("Ubiquitous", "ubiquitous"),
            ("UBIQUITOUS", "ubiquitous"),
            ("UbIqUiToUs", "ubiquitous"),
        ],
    )
    def test_strips_and_casefolds(self, raw: str, expected: str) -> None:
        assert normalize(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("give up", "give up"),
            ("give  up", "give up"),
            ("give\tup", "give up"),
            ("  give   up  ", "give up"),
            ("look  forward   to", "look forward to"),
        ],
    )
    def test_collapses_internal_whitespace(self, raw: str, expected: str) -> None:
        """Phrases are stored too, so double-spacing must not create a new entry."""
        assert normalize(raw) == expected

    def test_empty_and_whitespace_only(self) -> None:
        assert normalize("") == ""
        assert normalize("   ") == ""
        assert normalize("\t\n") == ""

    def test_casefold_not_lower(self) -> None:
        """casefold handles cases lower() gets wrong, e.g. German sharp s."""
        assert normalize("STRASSE") == normalize("strasse")
        assert normalize("straße") == "strasse"

    def test_punctuation_is_preserved(self) -> None:
        """Deliberate: stripping punctuation would guess at user intent."""
        assert normalize("well,") != normalize("well")
        assert normalize("don't") == "don't"


class TestNaturalKey:
    def test_identical_inputs_match(self) -> None:
        assert natural_key("ubiquitous", "IELTS") == natural_key("ubiquitous", "IELTS")

    def test_case_only_difference_matches(self) -> None:
        assert natural_key("Ubiquitous", "ielts") == natural_key("ubiquitous", "IELTS")

    def test_whitespace_only_difference_matches(self) -> None:
        assert natural_key("  give up ", " Daily Reading ") == natural_key(
            "give up", "Daily Reading"
        )

    def test_different_word_does_not_match(self) -> None:
        assert natural_key("ubiquitous", "IELTS") != natural_key("ubiquity", "IELTS")

    def test_same_word_different_collection_does_not_match(self) -> None:
        """The key is (word, collection): the same word in two collections is
        two legitimate entries, not a duplicate."""
        assert natural_key("ubiquitous", "IELTS") != natural_key(
            "ubiquitous", "Daily Reading"
        )

    def test_returns_a_two_tuple_of_normalized_parts(self) -> None:
        assert natural_key(" Give Up ", " My List ") == ("give up", "my list")


class TestNamesConflict:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("IELTS", "IELTS"),
            ("IELTS", "ielts"),
            ("ielts", "IELTS"),
            (" IELTS ", "IELTS"),
            ("Daily  Reading", "Daily Reading"),
        ],
    )
    def test_detects_conflicts(self, a: str, b: str) -> None:
        assert names_conflict(a, b) is True

    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("IELTS", "TOEFL"),
            ("Daily Reading", "Daily Writing"),
            ("General", "General 2"),
        ],
    )
    def test_allows_genuinely_different_names(self, a: str, b: str) -> None:
        assert names_conflict(a, b) is False

    def test_recasing_own_name_is_a_conflict_with_itself(self) -> None:
        """Recasing works because callers compare against *other* collections,
        never against the one being renamed (E7-S7 branch 4c)."""
        assert names_conflict("IELTS", "ielts") is True
        # The caller's usage: renaming "ielts" to "IELTS" checks only the others.
        others = ["Daily Reading", "General"]
        assert not any(names_conflict("IELTS", other) for other in others)
