"""Regression tests for background lookup surviving the Collect card's close.

The bug these exist for: the card closes immediately on every successful save, and
``closeEvent`` used to cancel the in-flight lookup unconditionally. That cancelled
the very enrichment patch ``CollectService.save_word`` had just scheduled, so a word
saved before its lookup resolved kept a blank Meaning and Example **permanently** --
the exact opposite of FR-2.9's "patch that same row when the lookup finishes".

The distinction the fix encodes: a *saved* entry hands its lookup off and lets it
run; a *discarded* entry still cancels, so a late result can never write a row the
user abandoned.

Needs a ``QApplication`` because the card is a real Qt widget, so this follows the
module-scoped fixture pattern used by the other ``tests/ui`` files.
"""

from __future__ import annotations

import pytest

qt_widgets = pytest.importorskip("PySide6.QtWidgets")

from vocabulary_trainer.data.master_file_repository import MasterFileRepository
from vocabulary_trainer.domain.models import (
    LookupResult,
    LookupSource,
    PartOfSpeech,
)
from vocabulary_trainer.services.collect_service import CollectService, LookupHandle
from vocabulary_trainer.services.lookup_service import LookupService


@pytest.fixture(scope="module")
def qt_app():
    app = qt_widgets.QApplication.instance() or qt_widgets.QApplication([])
    yield app


@pytest.fixture
def collect(repository: MasterFileRepository) -> CollectService:
    return CollectService(repository, LookupService([]))


def _card(qt_app, collect: CollectService):  # type: ignore[no-untyped-def]
    from vocabulary_trainer.ui.widget.collect_card_popup import CollectCardPopup

    return CollectCardPopup(collect, on_duplicate=lambda _existing, _incoming: None)


def _arm(card, word: str, pos: PartOfSpeech) -> LookupHandle:  # type: ignore[no-untyped-def]
    """Fill the card in and attach a lookup that has not resolved yet."""
    card._word_input.setText(word)
    card._select_pos(pos)
    pending = LookupHandle(word, pos)
    card._lookup = pending
    return pending


class TestSavedEntryKeepsItsLookup:
    def test_a_late_lookup_still_patches_the_saved_row(
        self, qt_app, collect: CollectService, repository: MasterFileRepository
    ) -> None:
        card = _card(qt_app, collect)
        pending = _arm(card, "ubiquitous", PartOfSpeech.ADJECTIVE)

        card._on_save_clicked()

        # Saved immediately with a blank meaning, and the card is gone (FR-2.8).
        assert repository.all_words()[0].meaning is None
        assert card.isVisible() is False

        pending._complete(
            LookupResult(
                "present everywhere", "An example.", LookupSource.FREE_DICTIONARY
            )
        )

        stored = repository.all_words()[0]
        assert stored.meaning == "present everywhere"
        assert stored.example == "An example."

    def test_the_lookup_is_not_cancelled_by_the_save(
        self, qt_app, collect: CollectService
    ) -> None:
        card = _card(qt_app, collect)
        pending = _arm(card, "ubiquitous", PartOfSpeech.ADJECTIVE)

        card._on_save_clicked()

        assert pending.is_cancelled is False

    def test_no_second_row_is_created_by_the_patch(
        self, qt_app, collect: CollectService, repository: MasterFileRepository
    ) -> None:
        """FR-2.9: enrichment patches, it never inserts."""
        card = _card(qt_app, collect)
        pending = _arm(card, "ubiquitous", PartOfSpeech.ADJECTIVE)
        card._on_save_clicked()

        pending._complete(
            LookupResult("a meaning", None, LookupSource.FREE_DICTIONARY)
        )

        assert len(repository.all_words()) == 1


class TestDiscardedEntryStillCancels:
    def test_closing_without_saving_cancels_the_lookup(
        self, qt_app, collect: CollectService
    ) -> None:
        card = _card(qt_app, collect)
        pending = _arm(card, "discarded", PartOfSpeech.NOUN)

        card.close()

        assert pending.is_cancelled is True

    def test_a_discarded_word_is_never_written(
        self, qt_app, collect: CollectService, repository: MasterFileRepository
    ) -> None:
        card = _card(qt_app, collect)
        pending = _arm(card, "discarded", PartOfSpeech.NOUN)
        card.close()

        pending._complete(
            LookupResult("should not appear", None, LookupSource.FREE_DICTIONARY)
        )

        assert repository.all_words() == []


class TestManualModeUnaffected:
    def test_manual_save_still_cancels_any_stray_lookup(
        self, qt_app, collect: CollectService, repository: MasterFileRepository
    ) -> None:
        """FR-2.11: a manually typed meaning must never be overwritten by a late
        dictionary result, so manual mode does *not* hand its lookup off."""
        from vocabulary_trainer.ui.widget.collect_card_popup import MeaningMode

        card = _card(qt_app, collect)
        pending = _arm(card, "ubiquitous", PartOfSpeech.ADJECTIVE)
        card._select_mode(MeaningMode.MANUAL)
        # Switching to manual cancels and clears the handle outright.
        assert pending.is_cancelled is True

        card._manual_meaning_input.setText("my own definition")
        card._on_save_clicked()

        assert repository.all_words()[0].meaning == "my own definition"

    def test_a_late_result_cannot_overwrite_a_manual_meaning(
        self, qt_app, collect: CollectService, repository: MasterFileRepository
    ) -> None:
        from vocabulary_trainer.ui.widget.collect_card_popup import MeaningMode

        card = _card(qt_app, collect)
        pending = _arm(card, "ubiquitous", PartOfSpeech.ADJECTIVE)
        card._select_mode(MeaningMode.MANUAL)
        card._manual_meaning_input.setText("my own definition")
        card._on_save_clicked()

        pending._complete(
            LookupResult("dictionary meaning", None, LookupSource.FREE_DICTIONARY)
        )

        assert repository.all_words()[0].meaning == "my own definition"


class TestSupersededLookup:
    def test_changing_the_type_cancels_the_previous_lookup(
        self, qt_app, collect: CollectService
    ) -> None:
        """Nothing was saved against it, and its result would be for a different
        part of speech than the user now wants."""
        card = _card(qt_app, collect)
        pending = _arm(card, "ubiquitous", PartOfSpeech.ADJECTIVE)

        card._select_pos(PartOfSpeech.NOUN)

        assert pending.is_cancelled is True
