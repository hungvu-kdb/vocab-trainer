"""The floating widget's runtime state.

This exists as a service rather than as fields on the widget window because the same
state is displayed and mutated from three places: the widget itself, its popup menu's
toggle, and the Settings Widget tab. If the view owned the state, those three would
have to push updates to each other. Observing one service instead means switching the
widget off from Settings updates the menu's toggle with no direct coupling between
them (E1-S4's "the two stay in sync").
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from vocabulary_trainer.data.preferences_store import PreferencesStore
from vocabulary_trainer.domain.models import (
    MAX_WIDGET_SCALE_PERCENT,
    MIN_WIDGET_SCALE_PERCENT,
    AppPreferences,
    CharacterKind,
    WidgetState,
)

__all__ = ["Unsubscribe", "WidgetStateService"]

Unsubscribe = Callable[[], None]


class WidgetStateService:
    """Holds widget state and notifies observers when it changes."""

    def __init__(
        self,
        preferences_store: PreferencesStore,
        preferences: AppPreferences | None = None,
    ) -> None:
        self._store = preferences_store
        self._preferences = preferences or preferences_store.load()
        self._state = WidgetState.IDLE
        self._lock = threading.RLock()
        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    @property
    def state(self) -> WidgetState:
        """Idle or active, driving which character image renders (FR-1.2)."""
        return self._state

    @property
    def position(self) -> tuple[int, int] | None:
        return self._preferences.widget_position

    @property
    def is_visible(self) -> bool:
        return self._preferences.widget_visible

    @property
    def character(self) -> CharacterKind:
        return self._preferences.character

    @property
    def scale_percent(self) -> int:
        """Widget size as a percentage of the artwork's natural size (FR-7.15)."""
        return self._preferences.widget_scale_percent

    @property
    def scale_factor(self) -> float:
        """The same value as a multiplier, for sizing calculations.

        Provided here so no caller has to remember to divide by 100 -- a widget
        rendered at 175x its size instead of 1.75x would be an easy mistake for a
        view to make on its own.
        """
        return self._preferences.widget_scale_percent / 100.0

    @property
    def preferences(self) -> AppPreferences:
        """The live preferences object, shared with SettingsService.

        Deliberately the same instance rather than a copy: both services edit fields
        on it and persist through the same store, so a copy would let the two drift.
        """
        return self._preferences

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def set_state(self, state: WidgetState) -> None:
        """Switch between the idle and active character images.

        Not persisted -- this is transient interaction state, and a widget that
        reopened in "active" pose with no menu showing would be wrong.
        """
        with self._lock:
            if self._state is state:
                return
            self._state = state
        self._notify()

    def move_to(self, x: int, y: int) -> bool:
        """Record a dragged position (FR-1.3, FR-1.4).

        Returns whether the position was persisted. A failure keeps the widget where
        the user dropped it for this session rather than snapping it back, because
        losing a drag would be more annoying than losing it on next launch
        (E1-S3 branch 5a).
        """
        with self._lock:
            self._preferences.widget_position = (int(x), int(y))
            saved = self._store.save(self._preferences)
        self._notify()
        return saved

    def set_visible(self, visible: bool) -> bool:
        """Show or hide the widget, persisting the choice (FR-1.6)."""
        with self._lock:
            if self._preferences.widget_visible == visible:
                return True
            self._preferences.widget_visible = visible
            saved = self._store.save(self._preferences)
        self._notify()
        return saved

    def set_scale_percent(self, percent: int) -> bool:
        """Resize the widget, applied live and persisted (FR-7.15).

        Rejects anything outside the supported range instead of clamping: this is
        called from a UI control that already limits its own range, so an
        out-of-range value means a caller bug, and quietly storing a different
        number than was asked for would hide it. The preferences *store* clamps
        instead, because a hand-edited file has no caller to correct.
        """
        if not isinstance(percent, int) or isinstance(percent, bool):
            return False
        if not (MIN_WIDGET_SCALE_PERCENT <= percent <= MAX_WIDGET_SCALE_PERCENT):
            return False

        with self._lock:
            if self._preferences.widget_scale_percent == percent:
                return True
            self._preferences.widget_scale_percent = percent
            saved = self._store.save(self._preferences)
        self._notify()
        return saved

    def set_character(self, character: CharacterKind) -> bool:
        """Change the character, applied live without a restart (FR-7.4)."""
        with self._lock:
            if self._preferences.character is character:
                return True
            self._preferences.character = character
            saved = self._store.save(self._preferences)
        self._notify()
        return saved

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def subscribe(self, listener: Callable[[], None]) -> Unsubscribe:
        """Be told when any widget state changes.

        Returns a callable that removes the listener, so a closing window can detach
        cleanly instead of leaking a reference and being notified after teardown.
        """
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def _notify(self) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener()
            except Exception:
                # One misbehaving view must not stop the others being updated, nor
                # leave the service in an inconsistent state.
                pass
