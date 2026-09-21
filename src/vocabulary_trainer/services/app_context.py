"""The composition root: the only place that knows the whole object graph.

Everything else receives its dependencies, which is what keeps the layers testable in
isolation. This module pays for that by being the single spot where construction order
matters, so the startup sequence is written out explicitly rather than left implicit in
import order.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from vocabulary_trainer.data.file_watcher import MasterFileWatcher
from vocabulary_trainer.data.history_store import HistoryStore
from vocabulary_trainer.data.master_file_repository import MasterFileRepository
from vocabulary_trainer.data.practice_log_repository import PracticeLogRepository
from vocabulary_trainer.data.preferences_store import (
    PreferencesStore,
    default_app_data_dir,
)
from vocabulary_trainer.domain.models import AppPreferences, RepairReport
from vocabulary_trainer.integrations.audio import AudioFeedbackService
from vocabulary_trainer.integrations.free_dictionary_client import FreeDictionaryClient
from vocabulary_trainer.integrations.local_dictionary_client import LocalDictionaryClient
from vocabulary_trainer.integrations.merriam_webster_client import MerriamWebsterClient
from vocabulary_trainer.integrations.ollama_client import OllamaClient
from vocabulary_trainer.integrations.translate_client import TranslateClient
from vocabulary_trainer.integrations.tts import TextToSpeechService
from vocabulary_trainer.services.clock import Clock, SystemClock
from vocabulary_trainer.services.collect_service import CollectService
from vocabulary_trainer.services.lookup_service import LookupService
from vocabulary_trainer.services.pending_enrichment import PendingEnrichmentRegistry
from vocabulary_trainer.services.practice_service import PracticeService
from vocabulary_trainer.services.settings_service import SettingsService
from vocabulary_trainer.services.widget_state_service import WidgetStateService

__all__ = ["AppContext"]

Unsubscribe = Callable[[], None]


class AppContext:
    """Owns every constructed component and the wiring between them."""

    def __init__(
        self,
        app_data_dir: Path | None = None,
        clock: Clock | None = None,
        start_watching: bool = True,
    ) -> None:
        self._clock = clock or SystemClock()
        self._data_dir = app_data_dir or default_app_data_dir()
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # 1. Preferences first: everything else depends on the master file path they
        #    carry, and on the widget state they seed.
        self._preferences_store = PreferencesStore(self._data_dir / "preferences.json")
        self._preferences: AppPreferences = self._preferences_store.load()

        # The default master file path is derived from the data directory rather than
        # read from a global. Without this, overriding app_data_dir would move the
        # preferences file but leave the workbook pointing at the real %AppData%, so a
        # portable install -- or a test -- would silently share one workbook.
        if not self._has_stored_master_path():
            self._preferences.master_file_path = self._data_dir / "master.xlsx"

        # 2. The workbook. Creating or repairing it here means every later component can
        #    assume a valid schema rather than each re-checking.
        self.repository = MasterFileRepository(self._preferences.master_file_path)
        self.startup_report: RepairReport = self.repository.ensure_workbook()

        self._history = HistoryStore(self._data_dir / "practice-history.json")
        self._practice_log = PracticeLogRepository(
            self._data_dir / "practice-log.xlsx"
        )

        # 3. Integrations. The Merriam-Webster client is held as an attribute because
        #    SettingsService pushes a new API key into it when the user saves one.
        self.merriam_webster = MerriamWebsterClient(
            api_key=self._preferences.merriam_webster_api_key
        )
        self._tts = TextToSpeechService()
        self._tts.select_voice(self._preferences.tts_voice_id)
        self._audio = AudioFeedbackService(
            assets_dir=Path(__file__).resolve().parent.parent / "assets" / "sounds"
        )

        # Held as an attribute for the same reason as the Merriam-Webster client:
        # SettingsService pushes the enabled flag and model name into it live.
        # Inert unless the user has switched it on and chosen a model, so a machine
        # with no Ollama installed is unaffected (FR-3.10).
        self.ollama = OllamaClient(
            enabled=self._preferences.ollama_enabled,
            model=self._preferences.ollama_model,
        )

        lookup = LookupService(
            [
                self.ollama,
                LocalDictionaryClient(),
                FreeDictionaryClient(),
                self.merriam_webster,
                TranslateClient(),
            ]
        )

        # 4. Services. WidgetStateService is given the already-loaded preferences so it
        #    and SettingsService mutate one shared object rather than two copies that
        #    could drift.
        self.widget_state = WidgetStateService(
            self._preferences_store, self._preferences
        )
        # Shared by the service that creates pending lookups and every view that
        # renders saved rows, so a preview can tell "looking up" from "found
        # nothing" -- indistinguishable in the workbook, where both are blank.
        self.pending_enrichment = PendingEnrichmentRegistry()

        self.collect = CollectService(
            self.repository, lookup, self._clock, pending=self.pending_enrichment
        )
        self.practice = PracticeService(
            self.repository,
            self._history,
            practice_log=self._practice_log,
            tts=self._tts,
            audio=self._audio,
            clock=self._clock,
            pending=self.pending_enrichment,
        )
        self.settings = SettingsService(
            self.repository,
            self._preferences_store,
            self.widget_state,
            tts=self._tts,
            clock=self._clock,
            merriam_webster_client=self.merriam_webster,
            ollama_client=self.ollama,
            pending=self.pending_enrichment,
        )

        # 5. Watch the workbook for external edits.
        self._reload_listeners: list[Callable[[], None]] = []
        self._watcher: MasterFileWatcher | None = None
        if start_watching:
            self._watcher = MasterFileWatcher(
                self._preferences.master_file_path, self._on_external_change
            )
            self._watcher.start()

    # ------------------------------------------------------------------

    def _has_stored_master_path(self) -> bool:
        """Whether the user has ever chosen a workbook location.

        Distinguishes a deliberate choice from the store's own default. Only the
        default is overridden by the data directory; a path the user picked in Settings
        is always honoured.
        """
        try:
            import json

            raw = json.loads(
                self._preferences_store.path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return False
        return isinstance(raw, dict) and bool(raw.get("master_file_path"))

    @property
    def preferences(self) -> AppPreferences:
        return self._preferences

    @property
    def app_data_dir(self) -> Path:
        return self._data_dir

    def on_data_reloaded(self, listener: Callable[[], None]) -> Unsubscribe:
        """Be told after an external workbook change has been absorbed (FR-8.8).

        Open views subscribe so their collection lists and counts refresh. Two things
        are deliberately *not* disturbed: an in-flight practice session keeps the pool
        it started with, and unsaved input in a Collect card is preserved -- swapping
        either underneath the user would be worse than showing slightly stale data
        (E8-S5 branches).
        """
        self._reload_listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._reload_listeners:
                self._reload_listeners.remove(listener)

        return unsubscribe

    def _on_external_change(self) -> None:
        self.repository.invalidate_cache()
        for listener in list(self._reload_listeners):
            try:
                listener()
            except Exception:
                # One view failing to refresh must not stop the others, nor kill the
                # watcher thread and silently end all future reloads.
                pass

    def retarget_master_file(self, path: Path) -> None:
        """Point the watcher at a new workbook after the user changed the path.

        Without this the app would keep watching the old file and never notice edits to
        the new one -- a silent staleness that is hard to diagnose from the UI.
        """
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = MasterFileWatcher(Path(path), self._on_external_change)
            self._watcher.start()

    def shutdown(self) -> None:
        """Stop background work and flush pending preference writes."""
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        self._reload_listeners.clear()
        self._preferences_store.save(self._preferences)
