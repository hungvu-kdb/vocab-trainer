"""The Settings window's bridge to Python (FR-7.x, FR-1.6, FR-1.8, FR-3.8).

Two things this file is careful about:

* **Toggles report the achieved state, not the requested one.** Registration for
  start-with-Windows can fail on a policy-managed machine, and a switch left showing
  "on" over a failed write is a lie the UI would keep displaying.
* **The API key is never returned across the channel.** Only whether one is set. There
  is no reason for the web layer to hold a secret it cannot use (NFR-SEC-01).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

from PySide6.QtCore import Slot

_T = TypeVar("_T")

from vocabulary_trainer.domain.models import (
    MAX_WIDGET_SCALE_PERCENT,
    MIN_WIDGET_SCALE_PERCENT,
    CharacterKind,
)
from vocabulary_trainer.integrations.ollama_client import DEFAULT_HOST
from vocabulary_trainer.services.settings_service import SettingsService
from vocabulary_trainer.ui.web.bridge import BridgeBase, fail, ok
from vocabulary_trainer.ui.widget import assets

__all__ = ["SettingsBridge"]


def _await(coroutine: Coroutine[Any, Any, _T]) -> _T:
    """Run one coroutine to completion from this synchronous slot.

    ``QWebChannel`` slots are synchronous and Qt is not running an asyncio loop, so
    an async service call has to be driven somewhere. It runs on a worker thread
    with its own loop -- the same approach ``CollectService.begin_lookup`` uses --
    rather than ``asyncio.run`` on the calling thread, which would block the Qt
    event loop and freeze the Settings window while Ollama was probed.

    Safe to block this slot briefly: the probe carries a 2-second ceiling, and a
    refused connection returns immediately, which is the case on any machine
    without Ollama running.
    """
    outcome: list[Any] = []

    def run() -> None:
        try:
            outcome.append(("ok", asyncio.run(coroutine)))
        except Exception as exc:  # pragma: no cover - defensive
            outcome.append(("error", exc))

    thread = threading.Thread(target=run, name="settings-async", daemon=True)
    thread.start()
    # Ceiling above the client's own timeout, so a hung probe cannot wedge the
    # window permanently.
    thread.join(timeout=20.0)

    if not outcome:
        raise TimeoutError("the operation did not finish in time")
    kind, value = outcome[0]
    if kind == "error":
        raise value
    return value


class SettingsBridge(BridgeBase):
    """Exposes settings operations to the Settings window's JavaScript."""

    def __init__(self, settings: SettingsService) -> None:
        super().__init__()
        self._settings = settings

    # ------------------------------------------------------------------
    # General tab
    # ------------------------------------------------------------------

    @Slot(result="QVariant")
    def general_state(self) -> dict[str, Any]:
        """Master file path and the start-with-Windows state (FR-7.3, FR-1.8)."""

        def run() -> dict[str, Any]:
            prefs = self._settings.preferences
            return ok(
                masterFilePath=str(prefs.master_file_path),
                startWithWindows=prefs.start_with_windows,
                hasMerriamWebsterKey=self._settings.has_merriam_webster_key(),
            )

        return self._guard(run)

    @Slot(result="QVariant")
    def pick_master_file(self) -> dict[str, Any]:
        """Open a native file dialog and return the chosen path (FR-7.3).

        The dialog is opened from Python rather than using the web layer's
        ``<input type="file">``, which reports only a sandboxed name and never a real
        filesystem path. Cancelling returns an empty path rather than an error, since
        cancelling is not a failure.
        """

        def run() -> dict[str, Any]:
            from PySide6.QtWidgets import QFileDialog

            current = self._settings.preferences.master_file_path
            chosen, _filter = QFileDialog.getSaveFileName(
                None,
                "Choose or create a vocabulary workbook",
                str(current),
                "Excel workbook (*.xlsx)",
                options=QFileDialog.Option.DontConfirmOverwrite,
            )
            return ok(path=chosen or "")

        return self._guard(run)

    @Slot(str, result="QVariant")
    def change_master_file(self, path: str) -> dict[str, Any]:
        """Switch workbooks, reporting any repair that was applied (FR-8.2, FR-8.4)."""

        def run() -> dict[str, Any]:
            if not str(path).strip():
                return fail("Choose a file location.")
            report = self._settings.change_master_file(Path(str(path)))
            return ok(
                masterFilePath=str(self._settings.preferences.master_file_path),
                created=report.created_workbook,
                repairs=list(report.changes),
            )

        return self._guard(run)

    @Slot(bool, result="QVariant")
    def set_start_with_windows(self, enabled: bool) -> dict[str, Any]:
        """Register or remove the sign-in entry, returning what was achieved."""

        def run() -> dict[str, Any]:
            achieved = self._settings.set_start_with_windows(bool(enabled))
            if achieved != bool(enabled):
                # Reporting failure lets the switch revert instead of misrepresenting
                # the machine's actual state (E1-S5 branch 4a).
                return fail(
                    "Windows would not allow this to be changed. "
                    "It may be blocked by a system policy.",
                    startWithWindows=achieved,
                )
            return ok(startWithWindows=achieved)

        return self._guard(run)

    # ------------------------------------------------------------------
    # Widget tab
    # ------------------------------------------------------------------

    @Slot(result="QVariant")
    def widget_state(self) -> dict[str, Any]:
        """Visibility and character, plus which characters have artwork (FR-7.4)."""

        def run() -> dict[str, Any]:
            prefs = self._settings.preferences
            return ok(
                widgetVisible=prefs.widget_visible,
                character=prefs.character.value,
                availableCharacters=[
                    c.value for c in assets.available_characters()
                ],
                # The bounds travel with the state so the slider's range is defined
                # in one place (the domain layer) rather than duplicated in markup
                # that could drift out of step with what the service accepts.
                widgetScalePercent=prefs.widget_scale_percent,
                minScalePercent=MIN_WIDGET_SCALE_PERCENT,
                maxScalePercent=MAX_WIDGET_SCALE_PERCENT,
            )

        return self._guard(run)

    @Slot(int, result="QVariant")
    def set_widget_scale_percent(self, percent: int) -> dict[str, Any]:
        """Resize the widget, applied live (FR-7.15).

        Reports the size actually in effect either way, so a rejected value lets the
        slider snap back to reality instead of displaying a size the widget is not.
        """

        def run() -> dict[str, Any]:
            if not self._settings.set_widget_scale_percent(int(percent)):
                return fail(
                    "Widget size must be between "
                    f"{MIN_WIDGET_SCALE_PERCENT}% and {MAX_WIDGET_SCALE_PERCENT}%.",
                    widgetScalePercent=self._settings.widget_scale_percent(),
                )
            return ok(widgetScalePercent=self._settings.widget_scale_percent())

        return self._guard(run)

    @Slot(bool, result="QVariant")
    def set_widget_visible(self, visible: bool) -> dict[str, Any]:
        return self._guard(
            lambda: ok(saved=self._settings.set_widget_visible(bool(visible)))
        )

    @Slot(str, result="QVariant")
    def set_character(self, character: str) -> dict[str, Any]:
        """Change the character, refusing one whose artwork is missing."""

        def run() -> dict[str, Any]:
            for candidate in CharacterKind:
                if candidate.value == character:
                    if candidate not in assets.available_characters():
                        # Keep the previous character rather than rendering a blank
                        # widget (E7-S3 branch 4a).
                        return fail(
                            f"Artwork for the {candidate.value} character is not "
                            "installed, so the current character was kept."
                        )
                    self._settings.set_character(candidate)
                    return ok(character=candidate.value)
            return fail(f"Unknown character '{character}'.")

        return self._guard(run)

    # ------------------------------------------------------------------
    # Audio tab
    # ------------------------------------------------------------------

    @Slot(result="QVariant")
    def audio_state(self) -> dict[str, Any]:
        """Installed voices and the current selection (FR-7.5)."""

        def run() -> dict[str, Any]:
            voices = self._settings.available_voices()
            return ok(
                voices=[
                    {"id": v.voice_id, "name": v.display_name} for v in voices
                ],
                selectedVoiceId=self._settings.preferences.tts_voice_id,
                # An empty list is a legitimate state, not an error: the tab explains
                # that practice plays its success sound without speech.
                hasVoices=bool(voices),
            )

        return self._guard(run)

    @Slot(str, result="QVariant")
    def set_tts_voice(self, voice_id: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            value = str(voice_id) or None
            self._settings.set_tts_voice(value)
            return ok(selectedVoiceId=value)

        return self._guard(run)

    @Slot(result="QVariant")
    def preview_voice(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if not self._settings.preview_voice():
                return fail("No speech voice is available on this computer.")
            return ok()

        return self._guard(run)

    # ------------------------------------------------------------------
    # Local LLM (Ollama)
    # ------------------------------------------------------------------

    @Slot(result="QVariant")
    def ollama_state(self) -> dict[str, Any]:
        """Current settings plus the models actually installed (FR-3.10).

        Only installed models are listed, so the dropdown can never offer one that
        would fail on first use. ``running`` distinguishes "Ollama is not there"
        from "Ollama is there but has no models", which the tab words differently.

        A previously chosen model that has since been removed is reported through
        ``modelMissing`` rather than being silently dropped -- otherwise lookups
        would quietly stop using the LLM with no indication why.
        """

        def run() -> dict[str, Any]:
            models = _await(self._settings.ollama_models())
            running = bool(models) or _await(self._settings.ollama_is_running())
            prefs = self._settings.preferences
            chosen = prefs.ollama_model
            return ok(
                enabled=prefs.ollama_enabled,
                model=chosen or "",
                models=models,
                running=running,
                modelMissing=bool(chosen) and chosen not in models,
                defaultHost=DEFAULT_HOST,
            )

        return self._guard(run)

    @Slot(bool, str, result="QVariant")
    def set_ollama(self, enabled: bool, model: str) -> dict[str, Any]:
        """Turn the LLM source on or off and choose the model.

        Reports the achieved state, so a request to enable without a model reverts
        the switch instead of showing it on while nothing is configured.
        """

        def run() -> dict[str, Any]:
            achieved = self._settings.set_ollama(
                enabled=bool(enabled), model=str(model)
            )
            if achieved != bool(enabled):
                return fail(
                    "Choose a model first \u2014 an AI source with no model "
                    "cannot generate anything.",
                    enabled=achieved,
                    model=self._settings.preferences.ollama_model or "",
                )
            return ok(
                enabled=achieved,
                model=self._settings.preferences.ollama_model or "",
            )

        return self._guard(run)

    # ------------------------------------------------------------------
    # Integrations
    # ------------------------------------------------------------------

    @Slot(str, result="QVariant")
    def set_merriam_webster_key(self, key: str) -> dict[str, Any]:
        """Store the key. Its value is never read back across the channel."""

        def run() -> dict[str, Any]:
            self._settings.set_merriam_webster_key(str(key))
            return ok(hasKey=self._settings.has_merriam_webster_key())

        return self._guard(run)

    # ------------------------------------------------------------------
    # About tab
    # ------------------------------------------------------------------

    @Slot(result="QVariant")
    def about_info(self) -> dict[str, Any]:
        """Name, version, and the workbook in use (FR-7.6)."""

        def run() -> dict[str, Any]:
            info = self._settings.about_info()
            return ok(
                appName=info.app_name,
                version=info.version,
                masterFilePath=info.master_file_path,
            )

        return self._guard(run)

    # ------------------------------------------------------------------
    # Collections tab
    # ------------------------------------------------------------------

    @Slot(result="QVariant")
    def list_collections(self) -> dict[str, Any]:
        """Collections with their word counts (FR-7.7)."""

        def run() -> dict[str, Any]:
            return ok(
                collections=[
                    {
                        "name": s.name,
                        "wordCount": s.word_count,
                        "createdOn": s.created_on.strftime("%b %d, %Y"),
                    }
                    for s in self._settings.collections_with_counts()
                ]
            )

        return self._guard(run)

    @Slot(str, result="QVariant")
    def create_collection(self, name: str) -> dict[str, Any]:
        """Create a collection (FR-7.8)."""
        return self._guard(
            lambda: ok(name=self._settings.create_collection(str(name)).name)
        )

    @Slot(str, str, result="QVariant")
    def rename_collection(self, old_name: str, new_name: str) -> dict[str, Any]:
        """Rename, cascading to every word row in one atomic write (FR-7.9)."""

        def run() -> dict[str, Any]:
            self._settings.rename_collection(str(old_name), str(new_name))
            return ok(name=str(new_name).strip())

        return self._guard(run)

    @Slot(str, result="QVariant")
    def collection_words(self, name: str) -> dict[str, Any]:
        """Every word row in one collection, for the preview table (FR-7.14)."""

        def run() -> dict[str, Any]:
            entries = self._settings.words_for_collection(str(name))
            words = [
                {
                    "word": entry.word,
                    "partOfSpeech": entry.part_of_speech.value,
                    "meaning": entry.meaning or "",
                    "example": entry.example or "",
                    "collectedOn": entry.collected_on.strftime("%b %d, %Y"),
                    # Distinguishes a blank cell that is still being filled in from
                    # one whose lookup finished with nothing. The workbook cannot
                    # tell them apart -- both are empty (FR-7.14).
                    "lookupPending": self._settings.is_lookup_pending(
                        entry.word, entry.collection_name
                    ),
                }
                for entry in entries
            ]
            return ok(
                name=str(name),
                words=words,
                # Lets the page decide whether to keep polling, without it having to
                # scan the rows itself.
                anyPending=any(word["lookupPending"] for word in words),
            )

        return self._guard(run)

    @Slot(str, result="QVariant")
    def deletion_preview(self, name: str) -> dict[str, Any]:
        """The exact word count the confirmation dialog must state (FR-7.10)."""

        def run() -> dict[str, Any]:
            count = self._settings.word_count_for_deletion(str(name))
            return ok(name=str(name), wordCount=count)

        return self._guard(run)

    @Slot(str, result="QVariant")
    def delete_collection(self, name: str) -> dict[str, Any]:
        """Delete a collection and its words (FR-7.11)."""
        return self._guard(
            lambda: ok(removed=self._settings.delete_collection(str(name)))
        )
