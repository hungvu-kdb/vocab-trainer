"""Text-to-speech for reading words aloud on a correct answer (FR-6.5, FR-7.5).

Every method degrades quietly. A machine with no installed voices, a voice that was
uninstalled since it was chosen, or an engine that fails mid-session must never
interrupt a practice run -- the success sound still plays and the drill continues
(E7-S4 branches). So ``speak`` returns a bool rather than raising.

Speech runs on a worker thread. SAPI's synchronous speak call blocks for the
duration of the utterance, which on the UI thread would freeze the drill for a
second on every correct answer.
"""

from __future__ import annotations

import threading

from vocabulary_trainer.domain.models import VoiceInfo

__all__ = ["TextToSpeechService"]


class TextToSpeechService:
    """Speaks words using the operating system's installed voices."""

    def __init__(self) -> None:
        self._voice_id: str | None = None
        self._lock = threading.Lock()
        self._voices_cache: list[VoiceInfo] | None = None

    # ------------------------------------------------------------------

    def available_voices(self) -> list[VoiceInfo]:
        """Installed voices, or an empty list when none are available.

        An empty list is a legitimate state, not an error: the Audio settings tab
        explains that practice will play its success sound without speech rather than
        showing a broken control (E7-S4 branch 2a).
        """
        if self._voices_cache is None:
            self._voices_cache = self._enumerate_voices()
        return list(self._voices_cache)

    def select_voice(self, voice_id: str | None) -> None:
        """Choose a voice by id. ``None`` means the system default."""
        with self._lock:
            self._voice_id = voice_id

    @property
    def selected_voice_id(self) -> str | None:
        return self._voice_id

    def speak(self, text: str) -> bool:
        """Say ``text`` on a background thread, reporting whether it started.

        Returns ``False`` when there is nothing to say or no engine is available.
        A ``True`` result means speech was dispatched, not that it finished.
        """
        if not text.strip():
            return False

        engine = self._create_engine()
        if engine is None:
            return False

        voice_id = self._voice_id

        def run() -> None:
            try:
                self._apply_voice(engine, voice_id)
                engine.Speak(text)
            except Exception:
                # A failure here is reported by having produced no sound. Raising on
                # a worker thread would be invisible to the user and could take down
                # the interpreter on some platforms.
                pass

        thread = threading.Thread(target=run, name="tts-speak", daemon=True)
        thread.start()
        return True

    def invalidate_voice_cache(self) -> None:
        """Force re-enumeration, e.g. after the user installs a voice."""
        self._voices_cache = None

    # ------------------------------------------------------------------
    # Platform layer -- isolated so tests can substitute it
    # ------------------------------------------------------------------

    def _enumerate_voices(self) -> list[VoiceInfo]:
        engine = self._create_engine()
        if engine is None:
            return []

        try:
            voices = engine.GetVoices()
            found: list[VoiceInfo] = []
            for index in range(voices.Count):
                token = voices.Item(index)
                found.append(
                    VoiceInfo(
                        voice_id=token.Id,
                        display_name=token.GetDescription(),
                    )
                )
            return found
        except Exception:
            return []

    @staticmethod
    def _create_engine() -> object | None:
        """Build a SAPI voice object, or ``None`` when unavailable.

        Created per call rather than cached because a COM object bound to one thread
        cannot be safely used from another, and speech happens on worker threads.
        """
        try:
            import win32com.client  # type: ignore[import-not-found]
        except ImportError:
            return None

        try:
            return win32com.client.Dispatch("SAPI.SpVoice")
        except Exception:
            return None

    @staticmethod
    def _apply_voice(engine: object, voice_id: str | None) -> None:
        """Point the engine at the chosen voice, tolerating one that has vanished.

        A voice uninstalled since it was selected falls back to the system default
        rather than failing the utterance (E7-S4 branch 5a).
        """
        if voice_id is None:
            return
        try:
            voices = engine.GetVoices()  # type: ignore[attr-defined]
            for index in range(voices.Count):
                token = voices.Item(index)
                if token.Id == voice_id:
                    engine.Voice = token  # type: ignore[attr-defined]
                    return
        except Exception:
            pass
