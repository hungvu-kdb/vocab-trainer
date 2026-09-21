"""Preferences, the master file location, and collection lifecycle management.

A recurring pattern here: mutators return the **achieved** state rather than ``None``.
A toggle that reports success while the underlying registration failed is a lie the UI
would then keep displaying, so the service reports what actually happened and lets the
view revert itself (FR-1.8, FR-7.4).
"""

from __future__ import annotations

from pathlib import Path

from vocabulary_trainer import APP_NAME, __version__
from vocabulary_trainer.data.errors import (
    CollectionNotFoundError,
    DuplicateCollectionError,
    MasterFileError,
    MasterFileLockedError,
    MasterFileUnreadableError,
)
from vocabulary_trainer.data.master_file_repository import MasterFileRepository
from vocabulary_trainer.data.preferences_store import PreferencesStore
from vocabulary_trainer.domain.models import (
    AboutInfo,
    AppPreferences,
    CharacterKind,
    Collection,
    CollectionSummary,
    RepairReport,
    VoiceInfo,
    WordEntry,
)
from vocabulary_trainer.integrations import startup_registration
from vocabulary_trainer.integrations.tts import TextToSpeechService
from vocabulary_trainer.services.clock import Clock, SystemClock
from vocabulary_trainer.services.errors import ValidationError
from vocabulary_trainer.services.pending_enrichment import PendingEnrichmentRegistry
from vocabulary_trainer.services.widget_state_service import WidgetStateService

__all__ = ["SettingsService"]


class SettingsService:
    """Backs every tab of the Settings window."""

    def __init__(
        self,
        repository: MasterFileRepository,
        preferences_store: PreferencesStore,
        widget_state: WidgetStateService,
        tts: TextToSpeechService | None = None,
        clock: Clock | None = None,
        merriam_webster_client: object | None = None,
        ollama_client: object | None = None,
        pending: PendingEnrichmentRegistry | None = None,
    ) -> None:
        self._repository = repository
        self._store = preferences_store
        self._widget_state = widget_state
        self._tts = tts
        self._clock = clock or SystemClock()
        self._merriam_webster_client = merriam_webster_client
        self._ollama_client = ollama_client
        self._pending = pending

    # ------------------------------------------------------------------
    # General tab
    # ------------------------------------------------------------------

    @property
    def preferences(self) -> AppPreferences:
        """The live preferences, shared with :class:`WidgetStateService`."""
        return self._widget_state.preferences

    def change_master_file(self, path: Path) -> RepairReport:
        """Point the app at a different workbook (FR-7.3, FR-8.2).

        Validates or creates the target *before* committing the change, so an
        unreadable file leaves the previous path in effect rather than stranding the
        app on a file it cannot read (E7-S2 branch 4b).
        """
        candidate = MasterFileRepository(Path(path))
        try:
            report = candidate.ensure_workbook()
        except MasterFileUnreadableError:
            raise
        except MasterFileError as exc:
            raise ValidationError(str(exc)) from exc

        self.preferences.master_file_path = Path(path)
        self._store.save(self.preferences)
        return report

    def set_start_with_windows(self, enabled: bool) -> bool:
        """Register or remove the sign-in entry, returning the achieved state.

        A ``False`` return when ``True`` was requested means registration failed --
        group policy can lock that registry key -- and the toggle should revert
        (FR-1.8, E1-S5 branch 4a).
        """
        succeeded = (
            startup_registration.register()
            if enabled
            else startup_registration.unregister()
        )
        achieved = enabled if succeeded else startup_registration.is_registered()

        self.preferences.start_with_windows = achieved
        self._store.save(self.preferences)
        return achieved

    # ------------------------------------------------------------------
    # Widget tab
    # ------------------------------------------------------------------

    def set_widget_visible(self, visible: bool) -> bool:
        """Delegates so this tab and the widget menu cannot disagree (E1-S4)."""
        return self._widget_state.set_visible(visible)

    def set_character(self, character: CharacterKind) -> bool:
        """Switch the character, applied live (FR-7.4)."""
        return self._widget_state.set_character(character)

    def set_widget_scale_percent(self, percent: int) -> bool:
        """Resize the widget, applied live (FR-7.15).

        Delegates for the same reason as the two settings above: one owner of the
        state means the Settings tab and the widget itself cannot disagree.
        """
        return self._widget_state.set_scale_percent(percent)

    def widget_scale_percent(self) -> int:
        """The current widget size, for populating the Settings control."""
        return self._widget_state.scale_percent

    # ------------------------------------------------------------------
    # Audio tab
    # ------------------------------------------------------------------

    def available_voices(self) -> list[VoiceInfo]:
        """Installed voices, empty when none are available (FR-7.5)."""
        return self._tts.available_voices() if self._tts is not None else []

    def set_tts_voice(self, voice_id: str | None) -> None:
        if self._tts is not None:
            self._tts.select_voice(voice_id)
        self.preferences.tts_voice_id = voice_id
        self._store.save(self.preferences)

    def preview_voice(self, sample: str = "vocabulary") -> bool:
        """Speak a sample, reporting whether anything was said."""
        return self._tts.speak(sample) if self._tts is not None else False

    # ------------------------------------------------------------------
    # Integrations
    # ------------------------------------------------------------------

    def set_merriam_webster_key(self, key: str | None) -> None:
        """Store the API key and apply it live (FR-3.8).

        The key is persisted in the local preferences file and is never written to a
        log or included in an error message (NFR-SEC-01).
        """
        cleaned = (key or "").strip() or None
        self.preferences.merriam_webster_api_key = cleaned
        self._store.save(self.preferences)

        # Applied immediately so the next lookup includes the source without a
        # restart (E3-S5).
        if self._merriam_webster_client is not None:
            setter = getattr(self._merriam_webster_client, "set_api_key", None)
            if callable(setter):
                setter(cleaned)

    def has_merriam_webster_key(self) -> bool:
        """Whether a key is configured, without exposing its value."""
        return bool(self.preferences.merriam_webster_api_key)

    # ------------------------------------------------------------------
    # Local LLM (Ollama)
    # ------------------------------------------------------------------

    async def ollama_models(self) -> list[str]:
        """Installed model names, or empty if Ollama is not reachable (FR-3.10).

        Only models actually installed are ever offered, so the dropdown cannot
        name something that would fail on first use.
        """
        if self._ollama_client is None:
            return []
        lister = getattr(self._ollama_client, "list_models", None)
        if not callable(lister):
            return []
        return await lister()

    async def ollama_is_running(self) -> bool:
        """Whether an Ollama server answered, for explaining an empty model list."""
        if self._ollama_client is None:
            return False
        probe = getattr(self._ollama_client, "is_running", None)
        if not callable(probe):
            return False
        return await probe()

    def set_ollama(self, *, enabled: bool, model: str | None) -> bool:
        """Store the LLM settings and apply them live (FR-3.10).

        Refuses to enable without a model, because an enabled-but-modelless state
        would look active in the UI while contributing nothing to lookups. Returns
        the achieved enabled state so the toggle can revert rather than lie -- the
        same contract as the start-with-Windows switch.
        """
        cleaned = (model or "").strip() or None
        achieved = bool(enabled) and cleaned is not None

        self.preferences.ollama_enabled = achieved
        self.preferences.ollama_model = cleaned
        self._store.save(self.preferences)

        # Applied immediately so the next lookup reflects the change with no restart.
        if self._ollama_client is not None:
            configure = getattr(self._ollama_client, "configure", None)
            if callable(configure):
                configure(enabled=achieved, model=cleaned)

        return achieved

    # ------------------------------------------------------------------
    # About tab
    # ------------------------------------------------------------------

    def about_info(self) -> AboutInfo:
        """Name, version, and the workbook in use (FR-7.6)."""
        path = self.preferences.master_file_path
        return AboutInfo(
            app_name=APP_NAME,
            version=__version__,
            master_file_path=str(path)
            if path.exists()
            else f"{path} (not found)",
        )

    # ------------------------------------------------------------------
    # Collections tab
    # ------------------------------------------------------------------

    def collections_with_counts(self) -> list[CollectionSummary]:
        """Every collection with its word count (FR-7.7)."""
        return self._repository.collection_summaries()

    def words_for_collection(self, name: str) -> list[WordEntry]:
        """Every word row belonging to one collection, for the preview table (FR-7.14).

        Delegates to the repository so this and the Practice setup screen's preview
        (FR-5.10) read through one definition of "in this collection" rather than
        two filters that could drift apart.
        """
        return self._repository.words_for(name)

    def is_lookup_pending(self, word: str, collection_name: str) -> bool:
        """Whether this row's meaning is still being looked up (FR-7.14).

        Lets a preview distinguish "no meaning yet" from "no meaning found", which
        are indistinguishable in the workbook -- both are a blank cell.
        """
        if self._pending is None:
            return False
        return self._pending.is_pending(word, collection_name)

    def create_collection(self, name: str) -> Collection:
        """Create a collection (FR-7.8)."""
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("Enter a name for the new collection.")

        collection = Collection(name=cleaned, created_on=self._clock.today())
        try:
            self._repository.insert_collection(collection)
        except DuplicateCollectionError as exc:
            raise ValidationError(str(exc)) from exc
        except MasterFileLockedError:
            raise
        return collection

    def rename_collection(self, old_name: str, new_name: str) -> None:
        """Rename a collection, carrying its words with it (FR-7.9).

        The repository performs the collection row and every word row in one atomic
        write, so a partial rename is impossible and no compensating revert is needed
        here.
        """
        cleaned = new_name.strip()
        if not cleaned:
            raise ValidationError("Enter a name for the collection.")

        try:
            self._repository.rename_collection(old_name, cleaned)
        except DuplicateCollectionError as exc:
            raise ValidationError(str(exc)) from exc
        except CollectionNotFoundError as exc:
            raise ValidationError(str(exc)) from exc

    def word_count_for_deletion(self, name: str) -> int:
        """The exact figure the confirmation dialog must state (FR-7.10)."""
        return self._repository.word_count_for(name)

    def delete_collection(self, name: str) -> int:
        """Delete a collection and its words, returning how many were removed.

        Re-seeds ``General`` when the last collection is deleted, so Collect always
        has a destination (FR-7.11, E7-S8 branch 7b).
        """
        try:
            removed = self._repository.delete_collection(name)
        except CollectionNotFoundError as exc:
            raise ValidationError(str(exc)) from exc

        self._repository.ensure_default_collection()
        return removed
