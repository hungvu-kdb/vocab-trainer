"""Tests for SettingsService and WidgetStateService (FR-1.x, FR-7.x)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from vocabulary_trainer.data.errors import MasterFileUnreadableError
from vocabulary_trainer.data.master_file_repository import MasterFileRepository
from vocabulary_trainer.data.preferences_store import PreferencesStore
from vocabulary_trainer.domain.models import (
    CharacterKind,
    Collection,
    WidgetState,
)
from vocabulary_trainer.integrations import startup_registration
from vocabulary_trainer.services.clock import FixedClock
from vocabulary_trainer.services.errors import ValidationError
from vocabulary_trainer.services.settings_service import SettingsService
from vocabulary_trainer.services.widget_state_service import WidgetStateService

from conftest import FIXED_TODAY, FakeTts, make_entry


@pytest.fixture
def widget_state(preferences_store: PreferencesStore) -> WidgetStateService:
    return WidgetStateService(preferences_store)


@pytest.fixture
def settings(
    repository: MasterFileRepository,
    preferences_store: PreferencesStore,
    widget_state: WidgetStateService,
    fake_tts: FakeTts,
    clock: FixedClock,
) -> SettingsService:
    return SettingsService(
        repository,
        preferences_store,
        widget_state,
        tts=fake_tts,
        clock=clock,
    )


class TestWidgetStateReads:
    def test_defaults(self, widget_state: WidgetStateService) -> None:
        assert widget_state.state is WidgetState.IDLE
        assert widget_state.is_visible is True
        assert widget_state.character is CharacterKind.CAT
        assert widget_state.position is None


class TestWidgetStateTransitions:
    def test_state_change_notifies_observers(
        self, widget_state: WidgetStateService
    ) -> None:
        notifications: list[int] = []
        widget_state.subscribe(lambda: notifications.append(1))

        widget_state.set_state(WidgetState.ACTIVE)

        assert widget_state.state is WidgetState.ACTIVE
        assert len(notifications) == 1

    def test_setting_the_same_state_does_not_notify(
        self, widget_state: WidgetStateService
    ) -> None:
        notifications: list[int] = []
        widget_state.subscribe(lambda: notifications.append(1))
        widget_state.set_state(WidgetState.IDLE)
        assert notifications == []

    def test_state_is_not_persisted(
        self, widget_state: WidgetStateService, preferences_store: PreferencesStore
    ) -> None:
        """A widget reopening in 'active' pose with no menu showing would be wrong."""
        widget_state.set_state(WidgetState.ACTIVE)
        assert WidgetStateService(preferences_store).state is WidgetState.IDLE

    def test_position_is_persisted(
        self, widget_state: WidgetStateService, preferences_store: PreferencesStore
    ) -> None:
        """FR-1.4: the widget reappears where the user left it."""
        assert widget_state.move_to(1200, 640) is True
        assert WidgetStateService(preferences_store).position == (1200, 640)

    def test_visibility_is_persisted(
        self, widget_state: WidgetStateService, preferences_store: PreferencesStore
    ) -> None:
        widget_state.set_visible(False)
        assert WidgetStateService(preferences_store).is_visible is False

    def test_character_is_persisted(
        self, widget_state: WidgetStateService, preferences_store: PreferencesStore
    ) -> None:
        widget_state.set_character(CharacterKind.CROCODILE)
        assert (
            WidgetStateService(preferences_store).character is CharacterKind.CROCODILE
        )

    def test_save_failure_keeps_the_in_memory_position(
        self, widget_state: WidgetStateService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """E1-S3 branch 5a: losing a drag would be worse than losing it on restart."""
        monkeypatch.setattr(widget_state._store, "save", lambda _p: False)
        assert widget_state.move_to(500, 500) is False
        assert widget_state.position == (500, 500)


class TestWidgetStateObservers:
    def test_unsubscribe_stops_notifications(
        self, widget_state: WidgetStateService
    ) -> None:
        """A closing window must be able to detach cleanly."""
        notifications: list[int] = []
        unsubscribe = widget_state.subscribe(lambda: notifications.append(1))

        widget_state.set_state(WidgetState.ACTIVE)
        unsubscribe()
        widget_state.set_state(WidgetState.IDLE)

        assert len(notifications) == 1

    def test_a_raising_observer_does_not_block_the_others(
        self, widget_state: WidgetStateService
    ) -> None:
        reached: list[str] = []
        widget_state.subscribe(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        widget_state.subscribe(lambda: reached.append("second"))

        widget_state.set_state(WidgetState.ACTIVE)
        assert reached == ["second"]

    def test_double_unsubscribe_is_harmless(
        self, widget_state: WidgetStateService
    ) -> None:
        unsubscribe = widget_state.subscribe(lambda: None)
        unsubscribe()
        unsubscribe()


class TestSettingsGeneral:
    def test_master_file_change_switches_and_persists(
        self, settings: SettingsService, tmp_path: Path
    ) -> None:
        target = tmp_path / "elsewhere" / "vocab.xlsx"
        report = settings.change_master_file(target)

        assert report.created_workbook is True
        assert settings.preferences.master_file_path == target
        assert target.exists()

    def test_unreadable_file_keeps_the_previous_path(
        self, settings: SettingsService, tmp_path: Path
    ) -> None:
        """E7-S2 branch 4b."""
        original = settings.preferences.master_file_path
        bogus = tmp_path / "not-a-workbook.xlsx"
        bogus.write_text("plain text", encoding="utf-8")

        with pytest.raises(MasterFileUnreadableError):
            settings.change_master_file(bogus)

        assert settings.preferences.master_file_path == original

    def test_start_with_windows_reports_the_achieved_state(
        self, settings: SettingsService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(startup_registration, "register", lambda: True)
        monkeypatch.setattr(startup_registration, "unregister", lambda: True)

        assert settings.set_start_with_windows(True) is True
        assert settings.preferences.start_with_windows is True

        assert settings.set_start_with_windows(False) is False
        assert settings.preferences.start_with_windows is False

    def test_failed_registration_reports_false_so_the_toggle_reverts(
        self, settings: SettingsService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """E1-S5 branch 4a: a toggle showing 'on' while nothing was registered is a
        lie the UI would keep displaying."""
        monkeypatch.setattr(startup_registration, "register", lambda: False)
        monkeypatch.setattr(startup_registration, "is_registered", lambda: False)

        assert settings.set_start_with_windows(True) is False
        assert settings.preferences.start_with_windows is False


class TestSettingsWidgetTab:
    def test_visibility_delegates_to_widget_state(
        self, settings: SettingsService, widget_state: WidgetStateService
    ) -> None:
        """E1-S4: this tab and the widget menu must not disagree."""
        settings.set_widget_visible(False)
        assert widget_state.is_visible is False

    def test_character_change_is_visible_to_the_widget(
        self, settings: SettingsService, widget_state: WidgetStateService
    ) -> None:
        settings.set_character(CharacterKind.CROCODILE)
        assert widget_state.character is CharacterKind.CROCODILE

    def test_change_notifies_widget_observers(
        self, settings: SettingsService, widget_state: WidgetStateService
    ) -> None:
        notifications: list[int] = []
        widget_state.subscribe(lambda: notifications.append(1))
        settings.set_widget_visible(False)
        assert len(notifications) == 1


class TestSettingsAudioTab:
    def test_voice_selection_is_applied_and_persisted(
        self, settings: SettingsService, fake_tts: FakeTts
    ) -> None:
        settings.set_tts_voice("voice-en-GB")
        assert fake_tts.selected == "voice-en-GB"
        assert settings.preferences.tts_voice_id == "voice-en-GB"

    def test_preview_speaks(self, settings: SettingsService, fake_tts: FakeTts) -> None:
        assert settings.preview_voice() is True
        assert fake_tts.spoken

    def test_voices_are_listed(self, settings: SettingsService) -> None:
        assert settings.available_voices() != []

    def test_works_without_a_tts_service(
        self,
        repository: MasterFileRepository,
        preferences_store: PreferencesStore,
        widget_state: WidgetStateService,
    ) -> None:
        """A machine with no speech support must not break Settings."""
        service = SettingsService(repository, preferences_store, widget_state, tts=None)
        assert service.available_voices() == []
        assert service.preview_voice() is False
        service.set_tts_voice("anything")


class TestMerriamWebsterKey:
    def test_key_is_stored_and_reported(self, settings: SettingsService) -> None:
        assert settings.has_merriam_webster_key() is False
        settings.set_merriam_webster_key("abc-123")
        assert settings.has_merriam_webster_key() is True
        assert settings.preferences.merriam_webster_api_key == "abc-123"

    def test_blank_key_clears_it(self, settings: SettingsService) -> None:
        settings.set_merriam_webster_key("abc-123")
        settings.set_merriam_webster_key("   ")
        assert settings.preferences.merriam_webster_api_key is None
        assert settings.has_merriam_webster_key() is False

    def test_key_is_applied_to_the_client_immediately(
        self,
        repository: MasterFileRepository,
        preferences_store: PreferencesStore,
        widget_state: WidgetStateService,
    ) -> None:
        """E3-S5: a Settings change must take effect without a restart."""

        class SpyClient:
            def __init__(self) -> None:
                self.key: str | None = None

            def set_api_key(self, key: str | None) -> None:
                self.key = key

        spy = SpyClient()
        service = SettingsService(
            repository,
            preferences_store,
            widget_state,
            merriam_webster_client=spy,
        )
        service.set_merriam_webster_key("live-key")
        assert spy.key == "live-key"


class TestAboutTab:
    def test_reports_name_version_and_path(self, settings: SettingsService) -> None:
        info = settings.about_info()
        assert info.app_name == "Vocabulary Trainer"
        assert info.version
        assert info.master_file_path

    def test_missing_file_is_reported_plainly(
        self, settings: SettingsService, tmp_path: Path
    ) -> None:
        """E7-S5 branch 2a: better than showing a stale path as if it were live."""
        settings.preferences.master_file_path = tmp_path / "vanished.xlsx"
        assert "not found" in settings.about_info().master_file_path


class TestCollectionsCrud:
    def test_lists_collections_with_counts(
        self, settings: SettingsService, repository: MasterFileRepository
    ) -> None:
        repository.insert_collection(Collection("IELTS", date(2026, 1, 1)))
        repository.insert_word(make_entry("alpha", collection="IELTS"))

        summaries = {s.name: s.word_count for s in settings.collections_with_counts()}
        assert summaries["IELTS"] == 1


class TestWordsForCollection:
    """FR-7.14: the Collections tab's preview table."""

    def test_returns_only_words_in_that_collection(
        self, settings: SettingsService, repository: MasterFileRepository
    ) -> None:
        repository.insert_collection(Collection("IELTS", date(2026, 1, 1)))
        repository.insert_word(make_entry("alpha", collection="IELTS"))
        repository.insert_word(make_entry("beta", collection="General"))

        words = settings.words_for_collection("IELTS")

        assert [w.word for w in words] == ["alpha"]

    def test_matches_case_insensitively_and_trims(
        self, settings: SettingsService, repository: MasterFileRepository
    ) -> None:
        repository.insert_collection(Collection("IELTS", date(2026, 1, 1)))
        repository.insert_word(make_entry("alpha", collection="IELTS"))

        assert len(settings.words_for_collection("  ielts  ")) == 1

    def test_empty_collection_returns_an_empty_list(
        self, settings: SettingsService
    ) -> None:
        settings.create_collection("Empty")
        assert settings.words_for_collection("Empty") == []

    def test_unknown_collection_name_returns_an_empty_list_rather_than_raising(
        self, settings: SettingsService
    ) -> None:
        """A stale name (e.g. deleted mid-session) must not surface as an error."""
        assert settings.words_for_collection("nonexistent") == []

    def test_carries_every_field_the_preview_table_shows(
        self, settings: SettingsService, repository: MasterFileRepository
    ) -> None:
        repository.insert_collection(Collection("IELTS", date(2026, 1, 1)))
        repository.insert_word(
            make_entry(
                "ubiquitous",
                collection="IELTS",
                meaning="present everywhere",
                example="It is ubiquitous.",
                when=date(2026, 2, 3),
            )
        )

        entry = settings.words_for_collection("IELTS")[0]
        assert entry.word == "ubiquitous"
        assert entry.meaning == "present everywhere"
        assert entry.example == "It is ubiquitous."
        assert entry.collected_on == date(2026, 2, 3)

    def test_includes_rows_with_a_blank_meaning(
        self, settings: SettingsService, repository: MasterFileRepository
    ) -> None:
        """A word saved with no lookup result, or a blank manual meaning, still
        belongs in the preview (FR-2.11's blank-meaning case)."""
        repository.insert_collection(Collection("IELTS", date(2026, 1, 1)))
        repository.insert_word(
            make_entry("alpha", collection="IELTS", meaning=None, example=None)
        )

        entry = settings.words_for_collection("IELTS")[0]
        assert entry.meaning is None
        assert entry.example is None

    def test_create(self, settings: SettingsService) -> None:
        created = settings.create_collection("Business English")
        assert created.name == "Business English"
        assert created.created_on == FIXED_TODAY

    @pytest.mark.parametrize("name", ["", "   "])
    def test_blank_name_is_rejected(self, settings: SettingsService, name: str) -> None:
        with pytest.raises(ValidationError):
            settings.create_collection(name)

    def test_duplicate_name_is_rejected(self, settings: SettingsService) -> None:
        settings.create_collection("IELTS")
        with pytest.raises(ValidationError) as exc:
            settings.create_collection("ielts")
        assert "already exists" in str(exc.value)

    def test_rename_cascades_to_word_rows(
        self, settings: SettingsService, repository: MasterFileRepository
    ) -> None:
        """FR-7.9."""
        settings.create_collection("IELTS")
        repository.insert_word(make_entry("alpha", collection="IELTS"))
        repository.insert_word(make_entry("beta", collection="IELTS"))

        settings.rename_collection("IELTS", "IELTS Advanced")

        assert all(
            e.collection_name == "IELTS Advanced" for e in repository.all_words()
        )

    def test_rename_to_a_blank_name_is_rejected(
        self, settings: SettingsService
    ) -> None:
        settings.create_collection("IELTS")
        with pytest.raises(ValidationError):
            settings.rename_collection("IELTS", "   ")

    def test_rename_collision_is_rejected(self, settings: SettingsService) -> None:
        settings.create_collection("IELTS")
        settings.create_collection("TOEFL")
        with pytest.raises(ValidationError):
            settings.rename_collection("IELTS", "toefl")

    def test_recasing_is_permitted(
        self, settings: SettingsService, repository: MasterFileRepository
    ) -> None:
        """E7-S7 branch 4c."""
        settings.create_collection("ielts")
        repository.insert_word(make_entry("alpha", collection="ielts"))

        settings.rename_collection("ielts", "IELTS")

        assert repository.all_words()[0].collection_name == "IELTS"

    def test_renaming_a_missing_collection_is_rejected(
        self, settings: SettingsService
    ) -> None:
        with pytest.raises(ValidationError):
            settings.rename_collection("nonexistent", "whatever")

    def test_deletion_count_is_reported_before_confirming(
        self, settings: SettingsService, repository: MasterFileRepository
    ) -> None:
        """FR-7.10: the dialog must state a real number."""
        settings.create_collection("Doomed")
        for index in range(17):
            repository.insert_word(make_entry(f"word{index}", collection="Doomed"))

        assert settings.word_count_for_deletion("Doomed") == 17

    def test_delete_cascades_and_returns_the_count(
        self, settings: SettingsService, repository: MasterFileRepository
    ) -> None:
        settings.create_collection("Doomed")
        for index in range(3):
            repository.insert_word(make_entry(f"word{index}", collection="Doomed"))

        assert settings.delete_collection("Doomed") == 3
        assert repository.all_words() == []

    def test_delete_leaves_other_collections_alone(
        self, settings: SettingsService, repository: MasterFileRepository
    ) -> None:
        settings.create_collection("Keep")
        settings.create_collection("Doomed")
        repository.insert_word(make_entry("survivor", collection="Keep"))
        repository.insert_word(make_entry("victim", collection="Doomed"))

        settings.delete_collection("Doomed")

        assert [e.word for e in repository.all_words()] == ["survivor"]

    def test_deleting_the_last_collection_reseeds_general(
        self, settings: SettingsService, repository: MasterFileRepository
    ) -> None:
        """E7-S8 branch 7b: Collect must always have a destination."""
        settings.delete_collection("General")
        assert [c.name for c in repository.all_collections()] == ["General"]

    def test_deleting_a_missing_collection_is_rejected(
        self, settings: SettingsService
    ) -> None:
        with pytest.raises(ValidationError):
            settings.delete_collection("nonexistent")

    def test_reported_count_matches_what_delete_removes(
        self, settings: SettingsService, repository: MasterFileRepository
    ) -> None:
        """The dialog's promise and the outcome must agree."""
        settings.create_collection("Doomed")
        for index in range(9):
            repository.insert_word(make_entry(f"w{index}", collection="Doomed"))

        promised = settings.word_count_for_deletion("Doomed")
        assert settings.delete_collection("Doomed") == promised


class TestSharedPreferences:
    def test_settings_and_widget_state_share_one_object(
        self, settings: SettingsService, widget_state: WidgetStateService
    ) -> None:
        """A copy would let the two drift apart."""
        assert settings.preferences is widget_state.preferences
