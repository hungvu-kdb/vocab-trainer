"""Tests for TTS, audio feedback, and startup registration (U5).

These wrap platform APIs, so the tests substitute the platform layer rather than
driving real speech or writing to the real registry. What is verified is the
contract the rest of the app depends on: nothing here ever raises, and every
operation reports honestly whether it worked.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from vocabulary_trainer.domain.models import VoiceInfo
from vocabulary_trainer.integrations import startup_registration
from vocabulary_trainer.integrations.audio import AudioFeedbackService
from vocabulary_trainer.integrations.tts import TextToSpeechService


class FakeVoiceToken:
    def __init__(self, voice_id: str, description: str) -> None:
        self.Id = voice_id
        self._description = description

    def GetDescription(self) -> str:
        return self._description


class FakeVoiceCollection:
    def __init__(self, tokens: list[FakeVoiceToken]) -> None:
        self._tokens = tokens

    @property
    def Count(self) -> int:
        return len(self._tokens)

    def Item(self, index: int) -> FakeVoiceToken:
        return self._tokens[index]


class FakeEngine:
    def __init__(self, tokens: list[FakeVoiceToken] | None = None) -> None:
        self._tokens = tokens or []
        self.spoken: list[str] = []
        self.Voice: FakeVoiceToken | None = None

    def GetVoices(self) -> FakeVoiceCollection:
        return FakeVoiceCollection(self._tokens)

    def Speak(self, text: str) -> None:
        self.spoken.append(text)


class TestVoiceEnumeration:
    def test_lists_installed_voices(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = FakeEngine(
            [
                FakeVoiceToken("id-en-US", "Microsoft David - English (US)"),
                FakeVoiceToken("id-en-GB", "Microsoft Hazel - English (UK)"),
            ]
        )
        service = TextToSpeechService()
        monkeypatch.setattr(service, "_create_engine", lambda: engine)

        voices = service.available_voices()
        assert [v.voice_id for v in voices] == ["id-en-US", "id-en-GB"]
        assert voices[0].display_name == "Microsoft David - English (US)"

    def test_no_engine_yields_an_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A legitimate state, not an error: Settings explains speech is unavailable."""
        service = TextToSpeechService()
        monkeypatch.setattr(service, "_create_engine", lambda: None)
        assert service.available_voices() == []

    def test_enumeration_failure_yields_an_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Broken:
            def GetVoices(self) -> None:
                raise RuntimeError("COM failure")

        service = TextToSpeechService()
        monkeypatch.setattr(service, "_create_engine", lambda: Broken())
        assert service.available_voices() == []

    def test_voices_are_cached_then_invalidatable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"count": 0}

        def create() -> FakeEngine:
            calls["count"] += 1
            return FakeEngine([FakeVoiceToken("id", "A Voice")])

        service = TextToSpeechService()
        monkeypatch.setattr(service, "_create_engine", create)

        service.available_voices()
        service.available_voices()
        assert calls["count"] == 1

        service.invalidate_voice_cache()
        service.available_voices()
        assert calls["count"] == 2


class TestSpeak:
    def test_dispatches_the_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = FakeEngine([FakeVoiceToken("id", "A Voice")])
        service = TextToSpeechService()
        monkeypatch.setattr(service, "_create_engine", lambda: engine)

        assert service.speak("ubiquitous") is True

        deadline = time.monotonic() + 2.0
        while not engine.spoken and time.monotonic() < deadline:
            time.sleep(0.01)
        assert engine.spoken == ["ubiquitous"]

    def test_returns_false_without_an_engine(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """E7-S4: practice continues with the success sound but no speech."""
        service = TextToSpeechService()
        monkeypatch.setattr(service, "_create_engine", lambda: None)
        assert service.speak("ubiquitous") is False

    @pytest.mark.parametrize("text", ["", "   ", "\t\n"])
    def test_blank_text_is_not_spoken(
        self, monkeypatch: pytest.MonkeyPatch, text: str
    ) -> None:
        service = TextToSpeechService()
        monkeypatch.setattr(service, "_create_engine", lambda: FakeEngine())
        assert service.speak(text) is False

    def test_a_failing_engine_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A mid-session speech failure must never interrupt the drill."""

        class Exploding(FakeEngine):
            def Speak(self, text: str) -> None:
                raise RuntimeError("engine died")

        service = TextToSpeechService()
        monkeypatch.setattr(service, "_create_engine", lambda: Exploding())
        assert service.speak("ubiquitous") is True
        time.sleep(0.1)

    def test_speaking_does_not_block_the_caller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SAPI's speak call blocks for the utterance; on the UI thread that would
        freeze the drill on every correct answer."""

        class Slow(FakeEngine):
            def Speak(self, text: str) -> None:
                time.sleep(0.5)
                super().Speak(text)

        service = TextToSpeechService()
        monkeypatch.setattr(service, "_create_engine", lambda: Slow())

        started = time.monotonic()
        service.speak("ubiquitous")
        assert time.monotonic() - started < 0.2


class TestVoiceSelection:
    def test_selection_round_trips(self) -> None:
        service = TextToSpeechService()
        assert service.selected_voice_id is None
        service.select_voice("id-en-GB")
        assert service.selected_voice_id == "id-en-GB"
        service.select_voice(None)
        assert service.selected_voice_id is None

    def test_selected_voice_is_applied_to_the_engine(self) -> None:
        wanted = FakeVoiceToken("id-en-GB", "Hazel")
        engine = FakeEngine([FakeVoiceToken("id-en-US", "David"), wanted])
        TextToSpeechService._apply_voice(engine, "id-en-GB")
        assert engine.Voice is wanted

    def test_a_vanished_voice_falls_back_silently(self) -> None:
        """E7-S4 branch 5a: a voice uninstalled since selection must not fail the
        utterance."""
        engine = FakeEngine([FakeVoiceToken("id-en-US", "David")])
        TextToSpeechService._apply_voice(engine, "id-that-no-longer-exists")
        assert engine.Voice is None

    def test_none_voice_leaves_the_system_default(self) -> None:
        engine = FakeEngine([FakeVoiceToken("id", "A Voice")])
        TextToSpeechService._apply_voice(engine, None)
        assert engine.Voice is None

    def test_apply_voice_tolerates_a_broken_engine(self) -> None:
        class Broken:
            def GetVoices(self) -> None:
                raise RuntimeError("COM failure")

        TextToSpeechService._apply_voice(Broken(), "any-id")


class TestVoiceInfo:
    def test_carries_id_and_display_name(self) -> None:
        voice = VoiceInfo(voice_id="id-en-US", display_name="Microsoft David")
        assert voice.voice_id == "id-en-US"
        assert voice.display_name == "Microsoft David"


class TestAudioFeedback:
    def test_neither_method_raises_without_assets(self) -> None:
        service = AudioFeedbackService()
        service.play_correct()
        service.play_incorrect()
        time.sleep(0.1)

    def test_missing_asset_directory_is_tolerated(self, tmp_path: Path) -> None:
        service = AudioFeedbackService(tmp_path / "no-such-dir")
        service.play_correct()
        service.play_incorrect()
        time.sleep(0.1)

    def test_resolves_a_bundled_wav_when_present(self, tmp_path: Path) -> None:
        (tmp_path / "correct.wav").write_bytes(b"RIFF fake wav")
        service = AudioFeedbackService(tmp_path)
        assert service._correct_path is not None
        assert service._incorrect_path is None

    def test_playback_does_not_block_the_caller(self, tmp_path: Path) -> None:
        """The user should be typing the next answer while the chime still sounds."""
        service = AudioFeedbackService(tmp_path)
        started = time.monotonic()
        service.play_correct()
        assert time.monotonic() - started < 0.2

    def test_a_failing_file_falls_back_to_a_system_sound(self, tmp_path: Path) -> None:
        """A corrupt asset must not silence feedback entirely."""
        (tmp_path / "correct.wav").write_bytes(b"not really a wav")
        service = AudioFeedbackService(tmp_path)
        service.play_correct()
        time.sleep(0.2)


class TestStartupCommand:
    def test_names_the_module_when_running_from_source(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.frozen", False, raising=False)
        command = startup_registration.startup_command()
        assert "-m vocabulary_trainer" in command
        assert command.startswith('"')

    def test_uses_the_executable_alone_when_frozen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.frozen", True, raising=False)
        monkeypatch.setattr("sys.executable", r"C:\Apps\VocabularyTrainer.exe")
        assert startup_registration.startup_command() == r'"C:\Apps\VocabularyTrainer.exe"'

    def test_path_is_quoted_for_spaces(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Program Files paths would otherwise be split at the space."""
        monkeypatch.setattr("sys.frozen", True, raising=False)
        monkeypatch.setattr("sys.executable", r"C:\Program Files\App\vt.exe")
        assert startup_registration.startup_command().startswith('"C:\\Program Files')


class TestStartupRegistration:
    def test_reports_failure_rather_than_raising_off_windows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """E1-S5 branch 4a: the toggle must be able to revert itself."""
        monkeypatch.setattr(startup_registration, "_winreg", lambda: None)
        assert startup_registration.is_registered() is False
        assert startup_registration.register() is False
        assert startup_registration.unregister() is False

    def test_register_and_unregister_round_trip(self) -> None:
        """Touches the real per-user Run key, then restores the prior state."""
        winreg = startup_registration._winreg()
        if winreg is None:
            pytest.skip("winreg unavailable on this platform")

        was_registered = startup_registration.is_registered()
        try:
            assert startup_registration.register() is True
            assert startup_registration.is_registered() is True
            assert startup_registration.unregister() is True
            assert startup_registration.is_registered() is False
        finally:
            if was_registered:
                startup_registration.register()
            else:
                startup_registration.unregister()

    def test_unregistering_an_absent_entry_reports_success(self) -> None:
        """The caller asked for a state, and that state has been reached."""
        if startup_registration._winreg() is None:
            pytest.skip("winreg unavailable on this platform")

        was_registered = startup_registration.is_registered()
        try:
            startup_registration.unregister()
            assert startup_registration.unregister() is True
        finally:
            if was_registered:
                startup_registration.register()

    def test_locked_key_reports_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Group policy can lock this key on a managed machine."""
        monkeypatch.setattr(
            startup_registration, "_open_run_key", lambda *, write: None
        )
        assert startup_registration.register() is False
        assert startup_registration.unregister() is False
        assert startup_registration.is_registered() is False
