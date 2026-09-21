"""Tests for preference persistence (FR-7.13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vocabulary_trainer.data.preferences_store import (
    PreferencesStore,
    default_app_data_dir,
    default_master_file_path,
)
from vocabulary_trainer.domain.models import AppPreferences, CharacterKind


@pytest.fixture
def store(tmp_path: Path) -> PreferencesStore:
    return PreferencesStore(tmp_path / "preferences.json")


class TestDefaults:
    def test_first_run_yields_documented_defaults(self, store: PreferencesStore) -> None:
        prefs = store.load()
        assert prefs.widget_visible is True
        assert prefs.widget_position is None
        assert prefs.character is CharacterKind.CAT
        assert prefs.tts_voice_id is None
        assert prefs.merriam_webster_api_key is None
        assert prefs.start_with_windows is False
        assert prefs.required_correct_writes == 3

    def test_default_master_path_is_under_app_data(self) -> None:
        """FR-8.1 names this exact location."""
        path = default_master_file_path()
        assert path.name == "master.xlsx"
        assert path.parent.name == "VocabularyTrainer"

    def test_app_data_dir_falls_back_without_appdata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The app should still run outside a normal Windows session."""
        monkeypatch.delenv("APPDATA", raising=False)
        assert default_app_data_dir().name == "VocabularyTrainer"


class TestRoundTrip:
    def test_every_field_survives_a_round_trip(self, store: PreferencesStore) -> None:
        original = AppPreferences(
            master_file_path=Path("D:/vocab/master.xlsx"),
            widget_visible=False,
            widget_position=(1200, 640),
            character=CharacterKind.CROCODILE,
            tts_voice_id="voice-en-GB",
            merriam_webster_api_key="secret-key",
            start_with_windows=True,
            required_correct_writes=5,
            last_practiced_collections=("IELTS", "Daily Reading"),
        )

        assert store.save(original) is True
        loaded = store.load()

        assert loaded.master_file_path == original.master_file_path
        assert loaded.widget_visible is False
        assert loaded.widget_position == (1200, 640)
        assert loaded.character is CharacterKind.CROCODILE
        assert loaded.tts_voice_id == "voice-en-GB"
        assert loaded.merriam_webster_api_key == "secret-key"
        assert loaded.start_with_windows is True
        assert loaded.required_correct_writes == 5
        assert loaded.last_practiced_collections == ("IELTS", "Daily Reading")

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        store = PreferencesStore(tmp_path / "a" / "b" / "preferences.json")
        assert store.save(AppPreferences(master_file_path=Path("m.xlsx"))) is True
        assert store.path.exists()

    def test_save_leaves_no_temp_files(self, store: PreferencesStore) -> None:
        store.save(AppPreferences(master_file_path=Path("m.xlsx")))
        assert list(store.path.parent.glob(".prefs-*")) == []

    def test_written_file_is_readable_json(self, store: PreferencesStore) -> None:
        """A user may want to inspect or hand-edit it."""
        store.save(AppPreferences(master_file_path=Path("m.xlsx")))
        payload = json.loads(store.path.read_text(encoding="utf-8"))
        assert payload["required_correct_writes"] == 3


class TestCorruptionTolerance:
    """A bad settings file must never lock the user out -- every field is
    recoverable by simply re-setting it."""

    def test_malformed_json_yields_defaults(self, store: PreferencesStore) -> None:
        store.path.write_text("{not json at all", encoding="utf-8")
        assert store.load().character is CharacterKind.CAT

    def test_non_object_json_yields_defaults(self, store: PreferencesStore) -> None:
        store.path.write_text("[1, 2, 3]", encoding="utf-8")
        assert store.load().widget_visible is True

    def test_wrong_field_types_fall_back_individually(
        self, store: PreferencesStore
    ) -> None:
        store.path.write_text(
            json.dumps(
                {
                    "widget_visible": "yes please",
                    "widget_position": "somewhere",
                    "character": "dragon",
                    "required_correct_writes": "three",
                    "last_practiced_collections": "IELTS",
                    "tts_voice_id": 42,
                }
            ),
            encoding="utf-8",
        )
        prefs = store.load()
        assert prefs.widget_visible is True
        assert prefs.widget_position is None
        assert prefs.character is CharacterKind.CAT
        assert prefs.required_correct_writes == 3
        assert prefs.last_practiced_collections == ()
        assert prefs.tts_voice_id is None

    def test_partial_file_keeps_the_fields_it_has(self, store: PreferencesStore) -> None:
        store.path.write_text(
            json.dumps({"character": "crocodile"}), encoding="utf-8"
        )
        prefs = store.load()
        assert prefs.character is CharacterKind.CROCODILE
        assert prefs.widget_visible is True

    @pytest.mark.parametrize(
        ("stored", "expected"),
        [(0, 1), (-5, 1), (11, 10), (500, 10), (1, 1), (10, 10), (3, 3)],
    )
    def test_required_writes_is_clamped_to_the_stepper_range(
        self, store: PreferencesStore, stored: int, expected: int
    ) -> None:
        """A hand-edited 0 would make a session impossible; 500 would make it endless."""
        store.path.write_text(
            json.dumps({"required_correct_writes": stored}), encoding="utf-8"
        )
        assert store.load().required_correct_writes == expected

    def test_boolean_is_not_accepted_as_required_writes(
        self, store: PreferencesStore
    ) -> None:
        """bool is a subclass of int in Python; True must not become 1 write."""
        store.path.write_text(
            json.dumps({"required_correct_writes": True}), encoding="utf-8"
        )
        assert store.load().required_correct_writes == 3

    def test_position_needs_exactly_two_integers(self, store: PreferencesStore) -> None:
        for bad in ([1], [1, 2, 3], [1.5, 2.5], ["a", "b"]):
            store.path.write_text(json.dumps({"widget_position": bad}), encoding="utf-8")
            assert store.load().widget_position is None

    def test_blank_strings_are_treated_as_absent(self, store: PreferencesStore) -> None:
        store.path.write_text(
            json.dumps({"tts_voice_id": "   ", "merriam_webster_api_key": ""}),
            encoding="utf-8",
        )
        prefs = store.load()
        assert prefs.tts_voice_id is None
        assert prefs.merriam_webster_api_key is None


class TestFailureHandling:
    def test_save_returns_false_rather_than_raising(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed preference save must not interrupt the user (E1-S3 branch 5a)."""
        store = PreferencesStore(tmp_path / "preferences.json")

        def deny(*_args: object, **_kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(
            "vocabulary_trainer.data.preferences_store.tempfile.mkstemp", deny
        )
        assert store.save(AppPreferences(master_file_path=Path("m.xlsx"))) is False

    def test_unreadable_file_yields_defaults(self, tmp_path: Path) -> None:
        store = PreferencesStore(tmp_path / "does-not-exist" / "preferences.json")
        assert store.load().character is CharacterKind.CAT
