"""Correct and incorrect feedback sounds for the practice drill (FR-6.5).

Playback is asynchronous and never blocks the drill: the user should be typing the
next answer while the chime is still sounding.

Falls back through three strategies so feedback survives a missing asset or an
unavailable audio device:

1. A bundled WAV file, if present.
2. A Windows system sound, which needs no asset at all.
3. Silence -- audio is a nicety, and a machine with no output device must still be
   able to practise.
"""

from __future__ import annotations

import threading
from pathlib import Path

__all__ = ["AudioFeedbackService"]


class AudioFeedbackService:
    """Plays short feedback sounds."""

    def __init__(self, assets_dir: Path | None = None) -> None:
        self._assets_dir = assets_dir
        self._correct_path = self._resolve("correct.wav")
        self._incorrect_path = self._resolve("incorrect.wav")

    def play_correct(self) -> None:
        """Sound for a correct answer."""
        self._play(self._correct_path, fallback_alias="SystemAsterisk")

    def play_incorrect(self) -> None:
        """Sound for a wrong answer."""
        self._play(self._incorrect_path, fallback_alias="SystemHand")

    # ------------------------------------------------------------------

    def _resolve(self, filename: str) -> Path | None:
        if self._assets_dir is None:
            return None
        candidate = self._assets_dir / filename
        return candidate if candidate.is_file() else None

    def _play(self, path: Path | None, fallback_alias: str) -> None:
        def run() -> None:
            if path is not None and self._play_file(path):
                return
            self._play_system_alias(fallback_alias)

        # Daemon thread: a sound still playing must never delay application exit.
        threading.Thread(target=run, name="audio-feedback", daemon=True).start()

    @staticmethod
    def _play_file(path: Path) -> bool:
        try:
            import winsound  # type: ignore[import-not-found]
        except ImportError:
            return False

        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
            return True
        except Exception:
            return False

    @staticmethod
    def _play_system_alias(alias: str) -> None:
        """Use a built-in Windows sound, so feedback works with no bundled asset."""
        try:
            import winsound  # type: ignore[import-not-found]
        except ImportError:
            return

        try:
            winsound.PlaySound(alias, winsound.SND_ALIAS)
        except Exception:
            # No audio device, or sounds disabled system-wide. Practice continues.
            pass
