"""Tests for the Collect flow (FR-2.x, FR-4.x).

The save-then-patch ordering is the centrepiece: a word must be recorded the moment
the user asks, and enriched afterwards, so a slow dictionary never costs a capture.
"""

from __future__ import annotations

import time
from datetime import date

import pytest

from vocabulary_trainer.data.errors import MasterFileLockedError
from vocabulary_trainer.data.master_file_repository import MasterFileRepository
from vocabulary_trainer.domain.models import (
    DefinitionCandidate,
    DuplicateAction,
    LookupResult,
    LookupSource,
    PartOfSpeech,
)
from vocabulary_trainer.services.clock import FixedClock
from vocabulary_trainer.services.collect_service import (
    CollectService,
    LookupHandle,
    SaveStatus,
)
from vocabulary_trainer.services.errors import ValidationError
from vocabulary_trainer.services.lookup_service import LookupService

from conftest import FIXED_TODAY, StubLookupClient, make_entry


@pytest.fixture
def service(
    repository: MasterFileRepository, clock: FixedClock
) -> CollectService:
    lookup = LookupService(
        [
            StubLookupClient(
                LookupSource.FREE_DICTIONARY,
                [
                    DefinitionCandidate(
                        part_of_speech=PartOfSpeech.ADJECTIVE,
                        meaning="present everywhere",
                        example="Phones are ubiquitous.",
                    )
                ],
            )
        ]
    )
    return CollectService(repository, lookup, clock)


def completed_handle(
    meaning: str | None = "m", example: str | None = "e"
) -> LookupHandle:
    handle = LookupHandle("ubiquitous", PartOfSpeech.ADJECTIVE)
    handle._complete(
        LookupResult(meaning=meaning, example=example, source=LookupSource.FREE_DICTIONARY)
    )
    return handle


class TestSaveWithLookupComplete:
    def test_saves_with_meaning_and_example(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        outcome = service.save_word(
            "ubiquitous", PartOfSpeech.ADJECTIVE, "General", completed_handle()
        )
        assert outcome.status is SaveStatus.SAVED
        stored = repository.all_words()[0]
        assert stored.meaning == "m"
        assert stored.example == "e"

    def test_stamps_the_current_date(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "General")
        assert repository.all_words()[0].collected_on == FIXED_TODAY

    def test_trims_surrounding_whitespace(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        service.save_word("  ubiquitous  ", PartOfSpeech.ADJECTIVE, "  General  ")
        stored = repository.all_words()[0]
        assert stored.word == "ubiquitous"
        assert stored.collection_name == "General"


class TestSaveMidLookup:
    def test_saves_immediately_with_blank_meaning(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        """FR-2.8: a slow dictionary must never cost the user the capture."""
        pending = LookupHandle("ubiquitous", PartOfSpeech.ADJECTIVE)

        outcome = service.save_word(
            "ubiquitous", PartOfSpeech.ADJECTIVE, "General", pending
        )

        assert outcome.status is SaveStatus.SAVED
        stored = repository.all_words()[0]
        assert stored.word == "ubiquitous"
        assert stored.meaning is None
        assert stored.example is None

    def test_patches_the_same_row_when_lookup_completes(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        """FR-2.9: patch, never insert a second row."""
        pending = LookupHandle("ubiquitous", PartOfSpeech.ADJECTIVE)
        service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "General", pending)

        pending._complete(
            LookupResult("present everywhere", "An example.", LookupSource.FREE_DICTIONARY)
        )

        words = repository.all_words()
        assert len(words) == 1, "enrichment must patch, not insert"
        assert words[0].meaning == "present everywhere"
        assert words[0].example == "An example."

    def test_empty_lookup_result_leaves_the_row_blank(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        """FR-3.5: all sources failing still leaves a usable saved word."""
        pending = LookupHandle("obscure", PartOfSpeech.NOUN)
        service.save_word("obscure", PartOfSpeech.NOUN, "General", pending)

        pending._complete(LookupResult.empty())

        stored = repository.all_words()[0]
        assert stored.word == "obscure"
        assert stored.meaning is None

    def test_patch_of_a_deleted_row_does_not_recreate_it(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        """E2-S4 branch 6c: a late lookup must not resurrect a deleted row."""
        pending = LookupHandle("ubiquitous", PartOfSpeech.ADJECTIVE)
        service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "General", pending)

        repository.delete_word(("ubiquitous", "general"))
        pending._complete(LookupResult("late meaning", None, LookupSource.FREE_DICTIONARY))

        assert repository.all_words() == []

    def test_save_without_a_handle_is_permitted(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "General")
        assert len(repository.all_words()) == 1


class TestLookupHandle:
    def test_starts_incomplete(self) -> None:
        handle = LookupHandle("word", PartOfSpeech.NOUN)
        assert handle.is_complete is False
        assert handle.result is None

    def test_listener_is_notified_on_completion(self) -> None:
        handle = LookupHandle("word", PartOfSpeech.NOUN)
        seen: list[LookupResult] = []
        handle.subscribe(seen.append)

        handle._complete(LookupResult("m", None, LookupSource.FREE_DICTIONARY))

        assert len(seen) == 1
        assert seen[0].meaning == "m"

    def test_late_subscriber_is_notified_immediately(self) -> None:
        """Removes the race between subscribing and the lookup finishing."""
        handle = completed_handle("already done")
        seen: list[LookupResult] = []
        handle.subscribe(seen.append)
        assert len(seen) == 1

    def test_a_raising_listener_does_not_break_the_pipeline(self) -> None:
        handle = LookupHandle("word", PartOfSpeech.NOUN)
        reached: list[str] = []

        handle.subscribe(lambda _r: (_ for _ in ()).throw(RuntimeError("boom")))
        handle.subscribe(lambda _r: reached.append("second"))

        handle._complete(LookupResult("m", None, LookupSource.FREE_DICTIONARY))
        assert reached == ["second"]

    def test_cancel_suppresses_notification(self) -> None:
        handle = LookupHandle("word", PartOfSpeech.NOUN)
        seen: list[LookupResult] = []
        handle.subscribe(seen.append)

        handle.cancel()
        handle._complete(LookupResult("m", None, LookupSource.FREE_DICTIONARY))

        assert seen == []
        assert handle.is_cancelled is True

    def test_real_background_lookup_completes(self, service: CollectService) -> None:
        handle = service.begin_lookup("ubiquitous", PartOfSpeech.ADJECTIVE)

        deadline = time.monotonic() + 3.0
        while not handle.is_complete and time.monotonic() < deadline:
            time.sleep(0.01)

        assert handle.is_complete is True
        result = handle.result
        assert result is not None
        assert result.meaning == "present everywhere"

    def test_begin_lookup_returns_immediately(self, service: CollectService) -> None:
        """FR-1.9: the widget stays responsive during lookup."""
        started = time.monotonic()
        service.begin_lookup("ubiquitous", PartOfSpeech.ADJECTIVE)
        assert time.monotonic() - started < 0.2


class TestValidation:
    @pytest.mark.parametrize("word", ["", "   ", "\t"])
    def test_blank_word_is_rejected(self, service: CollectService, word: str) -> None:
        with pytest.raises(ValidationError):
            service.save_word(word, PartOfSpeech.NOUN, "General")

    def test_blank_collection_is_rejected(self, service: CollectService) -> None:
        with pytest.raises(ValidationError):
            service.save_word("word", PartOfSpeech.NOUN, "   ")

    def test_nothing_is_written_when_validation_fails(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        with pytest.raises(ValidationError):
            service.save_word("", PartOfSpeech.NOUN, "General")
        assert repository.all_words() == []


class TestInlineCollectionCreation:
    def test_creates_a_collection(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        created = service.create_collection_inline("IELTS Vocabulary")
        assert created.name == "IELTS Vocabulary"
        assert created.created_on == FIXED_TODAY
        assert "IELTS Vocabulary" in [c.name for c in repository.all_collections()]

    def test_is_immediately_available_in_the_dropdown(
        self, service: CollectService
    ) -> None:
        service.create_collection_inline("IELTS")
        assert "IELTS" in service.available_collections()

    @pytest.mark.parametrize("name", ["", "   ", "\t\n"])
    def test_blank_name_is_rejected(self, service: CollectService, name: str) -> None:
        with pytest.raises(ValidationError) as exc:
            service.create_collection_inline(name)
        assert "name" in str(exc.value).lower()

    def test_duplicate_name_is_rejected_case_insensitively(
        self, service: CollectService
    ) -> None:
        service.create_collection_inline("IELTS")
        with pytest.raises(ValidationError) as exc:
            service.create_collection_inline("ielts")
        assert "already exists" in str(exc.value)

    def test_name_is_trimmed(self, service: CollectService) -> None:
        assert service.create_collection_inline("  IELTS  ").name == "IELTS"

    def test_the_default_collection_is_always_offered(
        self, service: CollectService
    ) -> None:
        """FR-8.1: the first capture always has somewhere to go."""
        assert "General" in service.available_collections()


class TestDuplicateDetection:
    def test_duplicate_blocks_the_write(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "General")
        outcome = service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "General")

        assert outcome.status is SaveStatus.DUPLICATE_DETECTED
        assert outcome.existing is not None
        assert len(repository.all_words()) == 1

    def test_detection_ignores_case_and_padding(
        self, service: CollectService
    ) -> None:
        service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "General")
        outcome = service.save_word("  UBIQUITOUS ", PartOfSpeech.ADJECTIVE, "general")
        assert outcome.status is SaveStatus.DUPLICATE_DETECTED

    def test_same_word_in_another_collection_is_not_a_duplicate(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        service.create_collection_inline("IELTS")
        service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "General")
        outcome = service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "IELTS")

        assert outcome.status is SaveStatus.SAVED
        assert len(repository.all_words()) == 2

    def test_check_duplicate_reports_the_existing_row(
        self, service: CollectService
    ) -> None:
        """The conflict popup needs the collection and date to display (FR-4.2)."""
        service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "General")
        existing = service.check_duplicate("ubiquitous", "General")
        assert existing is not None
        assert existing.collection_name == "General"
        assert existing.collected_on == FIXED_TODAY


class TestDuplicateResolution:
    def test_keep_old_changes_nothing(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        existing = make_entry("ubiquitous", meaning="original", when=date(2026, 1, 1))
        repository.insert_word(existing)
        incoming = make_entry("ubiquitous", meaning="new")

        assert service.resolve_duplicate(DuplicateAction.KEEP_OLD, existing, incoming)

        stored = repository.all_words()[0]
        assert stored.meaning == "original"
        assert stored.collected_on == date(2026, 1, 1)
        assert len(repository.all_words()) == 1

    def test_replace_updates_content_and_date(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        existing = make_entry("ubiquitous", meaning="original", when=date(2026, 1, 1))
        repository.insert_word(existing)
        incoming = make_entry("ubiquitous", meaning="refreshed", example="new example")

        service.resolve_duplicate(DuplicateAction.REPLACE, existing, incoming)

        stored = repository.all_words()[0]
        assert stored.meaning == "refreshed"
        assert stored.example == "new example"
        assert stored.collected_on == FIXED_TODAY

    def test_replace_preserves_word_and_collection(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        """FR-4.4: Replace refreshes an entry, it does not move or rename it."""
        existing = make_entry("ubiquitous", collection="General")
        repository.insert_word(existing)
        incoming = make_entry("ubiquitous", collection="General", meaning="new")

        service.resolve_duplicate(DuplicateAction.REPLACE, existing, incoming)

        stored = repository.all_words()[0]
        assert stored.word == "ubiquitous"
        assert stored.collection_name == "General"

    def test_replace_does_not_add_a_row(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        existing = make_entry("ubiquitous")
        repository.insert_word(existing)
        service.resolve_duplicate(
            DuplicateAction.REPLACE, existing, make_entry("ubiquitous", meaning="new")
        )
        assert len(repository.all_words()) == 1

    def test_delete_both_removes_the_old_and_discards_the_new(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        """FR-4.5: neither entry survives."""
        existing = make_entry("ubiquitous")
        repository.insert_word(existing)
        incoming = make_entry("ubiquitous", meaning="new")

        service.resolve_duplicate(DuplicateAction.DELETE_BOTH, existing, incoming)

        assert repository.all_words() == []

    @pytest.mark.parametrize(
        "action",
        [DuplicateAction.KEEP_OLD, DuplicateAction.REPLACE, DuplicateAction.DELETE_BOTH],
    )
    def test_no_action_ever_inserts_the_incoming_word_separately(
        self,
        service: CollectService,
        repository: MasterFileRepository,
        action: DuplicateAction,
    ) -> None:
        """FR-4.8: exactly one of {no change, updated, removed} occurs."""
        existing = make_entry("ubiquitous")
        repository.insert_word(existing)
        incoming = make_entry("ubiquitous", meaning="new")

        service.resolve_duplicate(action, existing, incoming)

        assert len(repository.all_words()) <= 1

    def test_other_rows_are_untouched_by_resolution(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        existing = make_entry("ubiquitous")
        repository.insert_word(existing)
        repository.insert_word(make_entry("bystander"))

        service.resolve_duplicate(
            DuplicateAction.DELETE_BOTH, existing, make_entry("ubiquitous")
        )

        assert [e.word for e in repository.all_words()] == ["bystander"]


class TestLockedFileHandling:
    def test_save_reports_locked_rather_than_raising(
        self,
        service: CollectService,
        repository: MasterFileRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FR-8.6: the caller must be able to keep the user's word and offer Retry."""

        def deny(_entry: object) -> None:
            raise MasterFileLockedError(repository.path)

        monkeypatch.setattr(repository, "insert_word", deny)

        outcome = service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "General")
        assert outcome.status is SaveStatus.LOCKED

    def test_retry_save_succeeds_once_the_file_is_free(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        entry = service.build_entry("ubiquitous", PartOfSpeech.ADJECTIVE, "General")
        assert service.retry_save(entry) is True
        assert len(repository.all_words()) == 1

    def test_retry_reports_failure_while_still_locked(
        self,
        service: CollectService,
        repository: MasterFileRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def deny(_entry: object) -> None:
            raise MasterFileLockedError(repository.path)

        monkeypatch.setattr(repository, "insert_word", deny)
        entry = service.build_entry("ubiquitous", PartOfSpeech.ADJECTIVE, "General")
        assert service.retry_save(entry) is False

    def test_resolution_reports_locked(
        self,
        service: CollectService,
        repository: MasterFileRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        existing = make_entry("ubiquitous")
        repository.insert_word(existing)

        def deny(_key: object) -> None:
            raise MasterFileLockedError(repository.path)

        monkeypatch.setattr(repository, "delete_word", deny)

        assert (
            service.resolve_duplicate(
                DuplicateAction.DELETE_BOTH, existing, make_entry("ubiquitous")
            )
            is False
        )

    def test_a_locked_patch_does_not_interrupt(
        self,
        service: CollectService,
        repository: MasterFileRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The row already holds the word, type, collection and date; losing only the
        enrichment is not worth an error dialog."""
        pending = LookupHandle("ubiquitous", PartOfSpeech.ADJECTIVE)
        service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "General", pending)

        def deny(*_args: object, **_kwargs: object) -> None:
            raise MasterFileLockedError(repository.path)

        monkeypatch.setattr(repository, "patch_word_enrichment", deny)
        pending._complete(LookupResult("m", "e", LookupSource.FREE_DICTIONARY))


class TestManualMeaning:
    """FR-2.11: the user may type their own meaning instead of waiting on lookup."""

    def test_saves_with_the_typed_meaning_and_example(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        outcome = service.save_word(
            "ubiquitous",
            PartOfSpeech.ADJECTIVE,
            "General",
            manual_meaning="found everywhere",
            manual_example="It is ubiquitous here.",
        )
        assert outcome.status is SaveStatus.SAVED
        stored = repository.all_words()[0]
        assert stored.meaning == "found everywhere"
        assert stored.example == "It is ubiquitous here."

    def test_manual_example_is_optional(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        service.save_word(
            "ubiquitous",
            PartOfSpeech.ADJECTIVE,
            "General",
            manual_meaning="found everywhere",
        )
        stored = repository.all_words()[0]
        assert stored.meaning == "found everywhere"
        assert stored.example is None

    def test_blank_manual_meaning_saves_with_type_only(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        """An explicit empty string still selects manual mode -- the user chose to
        skip the meaning rather than never having a lookup run."""
        service.save_word(
            "ubiquitous", PartOfSpeech.ADJECTIVE, "General", manual_meaning="   "
        )
        stored = repository.all_words()[0]
        assert stored.meaning is None

    def test_ignores_an_in_flight_lookup_handle(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        """Switching to manual must not let a stray lookup handle overwrite it."""
        pending = LookupHandle("ubiquitous", PartOfSpeech.ADJECTIVE)

        service.save_word(
            "ubiquitous",
            PartOfSpeech.ADJECTIVE,
            "General",
            pending,
            manual_meaning="my own definition",
        )

        stored = repository.all_words()[0]
        assert stored.meaning == "my own definition"

    def test_a_late_lookup_completion_never_patches_a_manual_row(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        """The core race this feature must avoid: a slow dictionary response
        silently overwriting what the user typed themselves."""
        pending = LookupHandle("ubiquitous", PartOfSpeech.ADJECTIVE)
        service.save_word(
            "ubiquitous",
            PartOfSpeech.ADJECTIVE,
            "General",
            pending,
            manual_meaning="my own definition",
        )

        pending._complete(
            LookupResult("dictionary meaning", "dictionary example", LookupSource.FREE_DICTIONARY)
        )

        stored = repository.all_words()[0]
        assert stored.meaning == "my own definition"
        assert stored.example is None

    def test_manual_save_still_detects_duplicates(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        service.save_word("ubiquitous", PartOfSpeech.ADJECTIVE, "General")
        outcome = service.save_word(
            "ubiquitous",
            PartOfSpeech.ADJECTIVE,
            "General",
            manual_meaning="my own definition",
        )
        assert outcome.status is SaveStatus.DUPLICATE_DETECTED
        assert len(repository.all_words()) == 1

    def test_manual_save_reports_locked_rather_than_raising(
        self,
        service: CollectService,
        repository: MasterFileRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def deny(_entry: object) -> None:
            raise MasterFileLockedError(repository.path)

        monkeypatch.setattr(repository, "insert_word", deny)

        outcome = service.save_word(
            "ubiquitous",
            PartOfSpeech.ADJECTIVE,
            "General",
            manual_meaning="my own definition",
        )
        assert outcome.status is SaveStatus.LOCKED

    def test_build_entry_uses_the_manual_meaning(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        """The conflict popup must also respect manual mode for the incoming side."""
        entry = service.build_entry(
            "ubiquitous",
            PartOfSpeech.ADJECTIVE,
            "General",
            completed_handle("looked up meaning", "looked up example"),
            manual_meaning="my own definition",
        )
        assert entry.meaning == "my own definition"
        assert entry.example is None
        assert repository.all_words() == []


class TestBuildEntry:
    def test_assembles_without_saving(
        self, service: CollectService, repository: MasterFileRepository
    ) -> None:
        entry = service.build_entry(
            "ubiquitous", PartOfSpeech.ADJECTIVE, "General", completed_handle("m", "e")
        )
        assert entry.word == "ubiquitous"
        assert entry.meaning == "m"
        assert repository.all_words() == []

    def test_uses_the_injected_clock(self, service: CollectService) -> None:
        assert (
            service.build_entry("word", PartOfSpeech.NOUN, "General").collected_on
            == FIXED_TODAY
        )
