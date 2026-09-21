"""User preferences, persisted as JSON under ``%AppData%``.

Failure posture differs sharply from the master file: preferences are convenience
state, so a corrupt or unreadable file falls back to defaults rather than blocking
startup. Losing a widget position is an annoyance; losing vocabulary is not
acceptable, which is why the two stores are separate.

The Merriam-Webster API key lives here. It is never written to a log or included in
an error message (NFR-SEC-01).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from vocabulary_trainer.domain.models import (
    AppPreferences,
    CharacterKind,
    clamp_widget_scale_percent,
)

__all__ = ["PreferencesStore", "default_app_data_dir", "default_master_file_path"]


def default_app_data_dir() -> Path:
    """The application's own folder under ``%AppData%``.

    Falls back to the user's home directory on a machine without ``APPDATA`` set,
    so the app still runs outside a normal Windows session (a CI container, for
    instance) rather than failing at startup.
    """
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    return root / "VocabularyTrainer"


def default_master_file_path() -> Path:
    """``%AppData%\\VocabularyTrainer\\master.xlsx`` (FR-8.1)."""
    return default_app_data_dir() / "master.xlsx"


class PreferencesStore:
    """Loads and saves :class:`AppPreferences` as JSON."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> AppPreferences:
        """Read preferences, applying documented defaults for anything absent.

        Any failure -- missing file, malformed JSON, unreadable field -- yields
        defaults. A user should never be locked out of the app by a bad settings
        file, and every field here is recoverable by re-setting it.
        """
        defaults = AppPreferences(master_file_path=default_master_file_path())

        try:
            # "utf-8-sig" rather than "utf-8": it strips a byte-order mark if one is
            # present and behaves identically when it is not. Several Windows editors
            # (and PowerShell's Set-Content -Encoding utf8 on 5.1) add a BOM when
            # saving, and with plain "utf-8" the leading \ufeff makes json.loads fail
            # -- which discarded *every* preference over one invisible byte, defeating
            # the per-field tolerance the rest of this class is built around.
            raw = json.loads(self._path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, UnicodeDecodeError):
            return defaults

        if not isinstance(raw, dict):
            return defaults

        return AppPreferences(
            master_file_path=self._read_path(
                raw.get("master_file_path"), defaults.master_file_path
            ),
            widget_visible=self._read_bool(
                raw.get("widget_visible"), defaults.widget_visible
            ),
            widget_position=self._read_position(raw.get("widget_position")),
            character=self._read_character(raw.get("character"), defaults.character),
            widget_scale_percent=self._read_widget_scale(
                raw.get("widget_scale_percent"), defaults.widget_scale_percent
            ),
            ollama_enabled=self._read_bool(
                raw.get("ollama_enabled"), defaults.ollama_enabled
            ),
            ollama_model=self._read_optional_str(raw.get("ollama_model")),
            tts_voice_id=self._read_optional_str(raw.get("tts_voice_id")),
            merriam_webster_api_key=self._read_optional_str(
                raw.get("merriam_webster_api_key")
            ),
            start_with_windows=self._read_bool(
                raw.get("start_with_windows"), defaults.start_with_windows
            ),
            required_correct_writes=self._read_required_writes(
                raw.get("required_correct_writes"), defaults.required_correct_writes
            ),
            last_practiced_collections=self._read_str_tuple(
                raw.get("last_practiced_collections")
            ),
        )

    def save(self, preferences: AppPreferences) -> bool:
        """Write preferences atomically, reporting success.

        Uses the same temp-then-swap discipline as the master file, for the same
        reason: a crash mid-write would otherwise leave truncated JSON that the next
        launch has to discard.

        Returns ``False`` rather than raising, because a failed preference save must
        not interrupt whatever the user was doing (E1-S3 branch 5a).
        """
        payload = {
            "master_file_path": str(preferences.master_file_path),
            "widget_visible": preferences.widget_visible,
            "widget_position": list(preferences.widget_position)
            if preferences.widget_position is not None
            else None,
            "character": preferences.character.value,
            "widget_scale_percent": preferences.widget_scale_percent,
            "ollama_enabled": preferences.ollama_enabled,
            "ollama_model": preferences.ollama_model,
            "tts_voice_id": preferences.tts_voice_id,
            "merriam_webster_api_key": preferences.merriam_webster_api_key,
            "start_with_windows": preferences.start_with_windows,
            "required_correct_writes": preferences.required_correct_writes,
            "last_practiced_collections": list(preferences.last_practiced_collections),
        }

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            handle, temp_name = tempfile.mkstemp(
                dir=self._path.parent, prefix=".prefs-", suffix=".tmp"
            )
            temp_path = Path(temp_name)
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, indent=2)
                os.replace(temp_path, self._path)
            except BaseException:
                temp_path.unlink(missing_ok=True)
                raise
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    # Field readers -- each tolerates a wrong type rather than raising
    # ------------------------------------------------------------------

    @staticmethod
    def _read_path(value: object, fallback: Path) -> Path:
        if isinstance(value, str) and value.strip():
            return Path(value)
        return fallback

    @staticmethod
    def _read_bool(value: object, fallback: bool) -> bool:
        return value if isinstance(value, bool) else fallback

    @staticmethod
    def _read_optional_str(value: object) -> str | None:
        if isinstance(value, str) and value.strip():
            return value
        return None

    @staticmethod
    def _read_position(value: object) -> tuple[int, int] | None:
        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and all(isinstance(part, int) for part in value)
        ):
            return (int(value[0]), int(value[1]))
        return None

    @staticmethod
    def _read_character(value: object, fallback: CharacterKind) -> CharacterKind:
        if isinstance(value, str):
            for member in CharacterKind:
                if member.value == value:
                    return member
        return fallback

    @staticmethod
    def _read_required_writes(value: object, fallback: int) -> int:
        """Clamp to the range the setup stepper allows (FR-5.6).

        A hand-edited file could hold 0 or 500; either would make a session
        impossible or endless.
        """
        if isinstance(value, int) and not isinstance(value, bool):
            return max(1, min(10, value))
        return fallback

    @staticmethod
    def _read_widget_scale(value: object, fallback: int) -> int:
        """Clamp the widget size to the supported range (FR-7.15).

        Clamped rather than rejected because this file is hand-editable: a typo of
        ``1000`` should give a very large widget, not silently revert to 100%. A
        non-integer value has no sensible interpretation, so that falls back.

        ``bool`` is excluded explicitly -- it is a subclass of ``int``, so ``True``
        would otherwise clamp to the minimum and look like a deliberate 50%.
        """
        if isinstance(value, int) and not isinstance(value, bool):
            return clamp_widget_scale_percent(value)
        return fallback

    @staticmethod
    def _read_str_tuple(value: object) -> tuple[str, ...]:
        if isinstance(value, (list, tuple)):
            return tuple(part for part in value if isinstance(part, str))
        return ()
