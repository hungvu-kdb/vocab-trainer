"""Tests for the presentation logic in the Collect and conflict popups.

Only the parts that are pure functions of data are covered here -- status-line wording
and the existing-entry panel text. Widget construction itself needs a live Qt
application and Windows compositing, so it is verified manually (recorded under
NFR-TEST-01: business logic is deliberately kept out of these modules).

The status-line assertions matter more than they look: the mockups still say
"Cambridge Dictionary", a source the product dropped before v2, so these tests pin the
requirement that the stale mockup copy is not reproduced (NFR-UI-03).
"""

from __future__ import annotations

from datetime import date

import pytest

from vocabulary_trainer.domain.models import LookupSource, PartOfSpeech, WordEntry
from vocabulary_trainer.ui.widget.collect_card_popup import (
    NEW_COLLECTION_SENTINEL,
    describe_source,
)
from vocabulary_trainer.ui.widget.duplicate_conflict_popup import (
    format_existing_entry,
)


class TestLookupStatusWording:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            (LookupSource.FREE_DICTIONARY, "Found in Free Dictionary"),
            (LookupSource.MERRIAM_WEBSTER, "Found in Merriam-Webster"),
            (LookupSource.GOOGLE_TRANSLATE, "Translated to Vietnamese"),
        ],
    )
    def test_names_the_source_that_answered(
        self, source: LookupSource, expected: str
    ) -> None:
        """FR-3.6: the user can judge the result's quality by its origin."""
        assert describe_source(source) == expected

    def test_no_result_is_phrased_as_an_outcome_not_an_error(self) -> None:
        """FR-3.5: the word still saved, so this must not read as a failure."""
        text = describe_source(LookupSource.NONE)
        assert "No definition found" in text
        assert "saved" in text

    @pytest.mark.parametrize("source", list(LookupSource))
    def test_every_source_has_wording(self, source: LookupSource) -> None:
        """A missing entry would raise a KeyError mid-lookup."""
        assert describe_source(source)

    @pytest.mark.parametrize("source", list(LookupSource))
    def test_stale_mockup_copy_is_not_reproduced(self, source: LookupSource) -> None:
        """NFR-UI-03: 'Cambridge Dictionary' was dropped before v2."""
        assert "Cambridge" not in describe_source(source)


class TestExistingEntryPanel:
    def _entry(
        self, collection: str = "IELTS Vocabulary", when: date | None = None
    ) -> WordEntry:
        return WordEntry(
            word="ubiquitous",
            part_of_speech=PartOfSpeech.ADJECTIVE,
            meaning="present everywhere",
            example=None,
            collection_name=collection,
            collected_on=when or date(2026, 8, 14),
        )

    def test_states_the_collection_and_date(self) -> None:
        """FR-4.2: enough context to decide in a couple of seconds."""
        text = format_existing_entry(self._entry())
        assert "IELTS Vocabulary" in text
        assert "Aug 14, 2026" in text

    def test_emphasises_the_values_not_the_labels(self) -> None:
        text = format_existing_entry(self._entry())
        assert "<b>IELTS Vocabulary</b>" in text
        assert "<b>Aug 14, 2026</b>" in text

    def test_uses_a_line_break_between_facts(self) -> None:
        assert "<br />" in format_existing_entry(self._entry())

    def test_handles_a_collection_name_with_spaces(self) -> None:
        assert "Daily Reading" in format_existing_entry(
            self._entry(collection="Daily Reading")
        )

    @pytest.mark.parametrize(
        ("when", "expected"),
        [
            (date(2026, 1, 1), "Jan 01, 2026"),
            (date(2026, 12, 31), "Dec 31, 2026"),
            (date(2026, 9, 12), "Sep 12, 2026"),
        ],
    )
    def test_date_formatting(self, when: date, expected: str) -> None:
        assert expected in format_existing_entry(self._entry(when=when))


class TestSentinel:
    def test_new_collection_sentinel_cannot_collide_with_a_real_name(self) -> None:
        """A user could legitimately name a collection "New collection"."""
        assert NEW_COLLECTION_SENTINEL.startswith("__")
        assert NEW_COLLECTION_SENTINEL.endswith("__")
