"""Tests for :class:`PracticeBridge` (FR-5.9, FR-6.15).

Regression coverage for a real bug: ``start_session`` and ``practice_again`` called
``ok(**self._prompt_payload(), poolSize=...)`` while ``_prompt_payload()`` already
carries a ``poolSize`` key, raising ``TypeError: ok() got multiple values for keyword
argument 'poolSize'`` on every successful call. The bridge's generic exception
handler swallowed that into an opaque "Something went wrong" -- Start practice could
never succeed. No Qt application object is needed: the bridge is a thin wrapper over
:class:`PracticeService`, in keeping with NFR-TEST-01.
"""

from __future__ import annotations

from vocabulary_trainer.data.history_store import HistoryStore
from vocabulary_trainer.data.master_file_repository import MasterFileRepository
from vocabulary_trainer.services.practice_service import PracticeService
from vocabulary_trainer.ui.web.practice_bridge import PracticeBridge

from conftest import make_entry


class TestStartSession:
    def test_succeeds_and_reports_the_first_word(
        self, repository: MasterFileRepository, history: HistoryStore
    ) -> None:
        repository.insert_word(make_entry("alpha"))
        repository.insert_word(make_entry("beta"))
        bridge = PracticeBridge(PracticeService(repository, history))

        result = bridge.start_session(["General"], 3)

        assert result["ok"] is True
        assert result["hasWord"] is True
        assert result["poolSize"] == 2

    def test_reports_a_user_facing_error_on_an_empty_pool(
        self, repository: MasterFileRepository, history: HistoryStore
    ) -> None:
        """FR-5.8's backstop: Start disabled client-side, but the bridge must still
        answer cleanly rather than crash if it is ever reached anyway."""
        bridge = PracticeBridge(PracticeService(repository, history))

        result = bridge.start_session(["General"], 3)

        assert result["ok"] is False
        assert "no words" in result["error"].lower()


class TestCollectionWordsPreview:
    """FR-5.10: the setup screen's read-only preview of a collection."""

    def test_returns_the_words_with_display_fields(
        self, repository: MasterFileRepository, history: HistoryStore
    ) -> None:
        repository.insert_word(make_entry("alpha", meaning="a meaning"))
        bridge = PracticeBridge(PracticeService(repository, history))

        result = bridge.collection_words("General")

        assert result["ok"] is True
        assert len(result["words"]) == 1
        assert result["words"][0]["word"] == "alpha"
        assert result["words"][0]["meaning"] == "a meaning"
        assert result["words"][0]["collectedOn"]

    def test_blank_meaning_and_example_become_empty_strings(
        self, repository: MasterFileRepository, history: HistoryStore
    ) -> None:
        """The page renders these as an em dash, so it needs a string not null."""
        repository.insert_word(make_entry("alpha", meaning=None, example=None))
        bridge = PracticeBridge(PracticeService(repository, history))

        word = bridge.collection_words("General")["words"][0]
        assert word["meaning"] == ""
        assert word["example"] == ""

    def test_scoped_to_the_named_collection(
        self, repository: MasterFileRepository, history: HistoryStore
    ) -> None:
        from datetime import date

        from vocabulary_trainer.domain.models import Collection

        repository.insert_collection(Collection("IELTS", date(2026, 1, 1)))
        repository.insert_word(make_entry("mine", collection="IELTS"))
        repository.insert_word(make_entry("theirs", collection="General"))
        bridge = PracticeBridge(PracticeService(repository, history))

        words = bridge.collection_words("IELTS")["words"]
        assert [w["word"] for w in words] == ["mine"]

    def test_empty_collection_answers_cleanly(
        self, repository: MasterFileRepository, history: HistoryStore
    ) -> None:
        bridge = PracticeBridge(PracticeService(repository, history))
        result = bridge.collection_words("General")
        assert result["ok"] is True
        assert result["words"] == []


class TestPracticeAgain:
    def test_succeeds_after_ending_a_session(
        self, repository: MasterFileRepository, history: HistoryStore
    ) -> None:
        repository.insert_word(make_entry("alpha"))
        practice = PracticeService(repository, history)
        bridge = PracticeBridge(practice)

        bridge.start_session(["General"], 3)
        bridge.end_session()

        result = bridge.practice_again()

        assert result["ok"] is True
        assert result["hasWord"] is True
        assert result["poolSize"] == 1
