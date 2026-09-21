"""Tests for the domain data structures."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from vocabulary_trainer.domain.models import (
    AppPreferences,
    CharacterKind,
    Collection,
    CollectionSortMode,
    CollectionSummary,
    DuplicateAction,
    LookupSource,
    PartOfSpeech,
    PracticeWordState,
    RepairReport,
    SessionSummary,
    WidgetState,
    WordEntry,
)


def entry(word: str = "ubiquitous", collection: str = "IELTS") -> WordEntry:
    return WordEntry(
        word=word,
        part_of_speech=PartOfSpeech.ADJECTIVE,
        meaning="present everywhere",
        example="Mobile phones are ubiquitous.",
        collection_name=collection,
        collected_on=date(2026, 8, 14),
    )


class TestWordEntry:
    def test_natural_key_delegates_to_the_shared_rule(self) -> None:
        assert entry("  Ubiquitous ", " ielts ").natural_key == ("ubiquitous", "ielts")

    def test_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            entry().word = "changed"  # type: ignore[misc]

    def test_meaning_and_example_may_be_absent(self) -> None:
        """A word saved before lookup finished, or with all sources failing."""
        bare = WordEntry(
            word="obscure",
            part_of_speech=PartOfSpeech.ADJECTIVE,
            meaning=None,
            example=None,
            collection_name="General",
            collected_on=date(2026, 9, 1),
        )
        assert bare.meaning is None
        assert bare.example is None


class TestPracticeWordState:
    def test_starts_at_zero(self) -> None:
        state = PracticeWordState(entry=entry())
        assert state.correct_count == 0
        assert state.wrong_count == 0

    def test_is_mutable_by_design(self) -> None:
        state = PracticeWordState(entry=entry())
        state.correct_count = 2
        state.wrong_count = 1
        assert state.correct_count == 2
        assert state.wrong_count == 1

    @pytest.mark.parametrize(
        ("correct", "wrong", "required", "expected"),
        [
            (0, 0, 3, False),
            (1, 0, 3, False),
            (2, 0, 3, False),
            (3, 0, 3, True),
            (4, 0, 3, True),
            (1, 0, 1, True),
            (0, 0, 1, False),
            # NOR rule: a wrong answer raises the target by one, so the same
            # correct count that would have mastered a clean run no longer does.
            (1, 1, 3, False),  # required(3) + wrong(1) - correct(1) = 3 remaining
            (2, 1, 3, False),  # 3 + 1 - 2 = 2 remaining
            (4, 1, 3, True),  # 3 + 1 - 4 = 0 remaining -> mastered
            (4, 2, 3, False),  # 3 + 2 - 4 = 1 remaining -- the request's own example
        ],
    )
    def test_mastery_threshold(
        self, correct: int, wrong: int, required: int, expected: bool
    ) -> None:
        state = PracticeWordState(
            entry=entry(), correct_count=correct, wrong_count=wrong
        )
        assert state.is_mastered_at(required) is expected

    def test_overshoot_still_counts_as_mastered(self) -> None:
        """Uses <= 0 so an off-by-one elsewhere cannot strand the session."""
        state = PracticeWordState(entry=entry(), correct_count=99)
        assert state.is_mastered_at(3) is True

    def test_remaining_is_floored_at_zero(self) -> None:
        """A run of correct answers cannot bank credit against future mistakes --
        remaining_for never goes negative, it simply reads zero once satisfied."""
        state = PracticeWordState(entry=entry(), correct_count=10, wrong_count=0)
        assert state.remaining_for(3) == 0

    @pytest.mark.parametrize(
        ("correct", "wrong", "required", "expected_remaining"),
        [
            (0, 0, 3, 3),
            (0, 1, 3, 4),  # the request's first example: NODR=3, one wrong -> 4
            (1, 2, 3, 4),  # the request's second example: 3 - 1 + 2 = 4
        ],
    )
    def test_remaining_matches_the_requested_examples(
        self, correct: int, wrong: int, required: int, expected_remaining: int
    ) -> None:
        state = PracticeWordState(
            entry=entry(), correct_count=correct, wrong_count=wrong
        )
        assert state.remaining_for(required) == expected_remaining


class TestRepairReport:
    def test_clean_workbook_needs_no_notice(self) -> None:
        assert RepairReport().needs_user_notice is False

    def test_repairs_require_a_notice(self) -> None:
        report = RepairReport(changes=("renamed column 'Word' to 'Words'",))
        assert report.needs_user_notice is True

    def test_creation_alone_is_not_a_repair_notice(self) -> None:
        """A fresh workbook is expected on first run, not something to warn about."""
        report = RepairReport(created_workbook=True, seeded_default_collection=True)
        assert report.needs_user_notice is False


class TestEnumSerialization:
    def test_values_are_human_readable_strings(self) -> None:
        """They land in the workbook and JSON directly, and users read them in Excel."""
        assert PartOfSpeech.ADJECTIVE == "adjective"
        assert CharacterKind.CROCODILE == "crocodile"
        assert WidgetState.IDLE == "idle"
        assert CollectionSortMode.NEWEST_FIRST == "newest_first"
        assert LookupSource.FREE_DICTIONARY == "free_dictionary"

    def test_delete_action_is_named_for_its_full_effect(self) -> None:
        """FR-4.6: the label must make clear neither entry survives."""
        assert DuplicateAction.DELETE_BOTH == "delete_both"

    def test_part_of_speech_covers_the_collect_card_chips(self) -> None:
        assert {p.value for p in PartOfSpeech} == {
            "noun",
            "verb",
            "adjective",
            "adverb",
            "phrase",
        }

    def test_sort_modes_cover_the_setup_control(self) -> None:
        assert {m.value for m in CollectionSortMode} == {
            "newest_first",
            "oldest_first",
            "name_asc",
        }


class TestValueObjectImmutability:
    def test_collection_is_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            Collection(name="IELTS", created_on=date(2026, 1, 1)).name = "x"  # type: ignore[misc]

    def test_collection_summary_is_frozen(self) -> None:
        summary = CollectionSummary(
            name="IELTS", created_on=date(2026, 1, 1), word_count=128
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            summary.word_count = 0  # type: ignore[misc]

    def test_session_summary_is_frozen(self) -> None:
        summary = SessionSummary(
            score=142,
            words_practiced=170,
            total_penalties=28,
            elapsed=timedelta(minutes=18, seconds=42),
            finished_at=datetime(2026, 9, 12, 10, 24),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            summary.score = 0  # type: ignore[misc]


class TestAppPreferences:
    def test_documented_defaults(self) -> None:
        prefs = AppPreferences(master_file_path=Path("master.xlsx"))
        assert prefs.widget_visible is True
        assert prefs.widget_position is None
        assert prefs.character is CharacterKind.CAT
        assert prefs.tts_voice_id is None
        assert prefs.merriam_webster_api_key is None
        assert prefs.start_with_windows is False
        assert prefs.required_correct_writes == 3
        assert prefs.last_practiced_collections == ()

    def test_is_mutable_for_settings_edits(self) -> None:
        prefs = AppPreferences(master_file_path=Path("master.xlsx"))
        prefs.widget_visible = False
        prefs.character = CharacterKind.CROCODILE
        assert prefs.widget_visible is False
        assert prefs.character is CharacterKind.CROCODILE

    def test_start_with_windows_defaults_off(self) -> None:
        """FR-1.8 requires opt-in, not opt-out."""
        assert AppPreferences(master_file_path=Path("m.xlsx")).start_with_windows is False

    def test_required_writes_default_matches_the_mockup(self) -> None:
        """practice-setup.html shows 3 (FR-5.6)."""
        assert AppPreferences(master_file_path=Path("m.xlsx")).required_correct_writes == 3
