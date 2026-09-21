"""Which saved rows are still waiting on a lookup to fill in their meaning.

Exists because "no meaning yet" and "no meaning ever" look identical in the
workbook: both are a blank cell. A preview table reading only the workbook has to
render them the same way, so a word saved two seconds ago showed the same em dash as
one whose lookup failed last week -- and the user could not tell whether waiting
would help.

The Collect card already knows, via its :class:`LookupHandle`, but that knowledge
was private to one popup. This registry is the shared, minimal statement of it:
*these natural keys have an enrichment patch outstanding.*

Deliberately not persisted. A pending lookup cannot survive the process that is
running it, so a registry restored from disk would claim rows are being worked on by
a thread that no longer exists -- a permanent "looking up..." with nothing behind
it. On restart every row is simply blank-or-not, which is the truth.

Keyed by natural key rather than by row position, matching every other identity
decision in the app (``domain/natural_key``), so a row that moves when the user
sorts the workbook in Excel is still recognised.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable

from vocabulary_trainer.domain.natural_key import natural_key

__all__ = ["PendingEnrichmentRegistry", "Unsubscribe"]

Unsubscribe = Callable[[], None]


class PendingEnrichmentRegistry:
    """Tracks rows whose meaning is still being looked up."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pending: set[tuple[str, str]] = set()
        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # Writes -- called by CollectService around a save
    # ------------------------------------------------------------------

    def mark_pending(self, key: tuple[str, str]) -> None:
        """Record that this row is waiting on a lookup."""
        with self._lock:
            if key in self._pending:
                return
            self._pending.add(key)
        self._notify()

    def clear_pending(self, key: tuple[str, str]) -> None:
        """Record that the lookup for this row has finished, however it ended.

        Called on success, on an empty result, and on failure alike: the row is no
        longer *waiting*, which is the only thing this registry claims. Whether it
        ended up with a meaning is already visible in the workbook.
        """
        with self._lock:
            if key not in self._pending:
                return
            self._pending.discard(key)
        self._notify()

    # ------------------------------------------------------------------
    # Reads -- called by any view rendering saved rows
    # ------------------------------------------------------------------

    def is_pending(self, word: str, collection_name: str) -> bool:
        """Whether this word's meaning is still being looked up."""
        with self._lock:
            return natural_key(word, collection_name) in self._pending

    def pending_keys(self) -> set[tuple[str, str]]:
        """A snapshot of every outstanding key.

        A copy, so a caller iterating it cannot trip over a background lookup
        completing mid-loop.
        """
        with self._lock:
            return set(self._pending)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._pending)

    # ------------------------------------------------------------------
    # Observation -- so an open preview can refresh itself
    # ------------------------------------------------------------------

    def subscribe(self, listener: Callable[[], None]) -> Unsubscribe:
        """Be told whenever the pending set changes.

        Returns a callable that detaches the listener, so a closing window does not
        leak a reference and get called after teardown.
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
                # One view failing to refresh must not stop the others, nor break the
                # lookup thread that is publishing this change.
                pass

    # ------------------------------------------------------------------

    def clear_all(self, keys: Iterable[tuple[str, str]] | None = None) -> None:
        """Drop pending state, for shutdown or a workbook switch.

        After the master file changes, keys from the previous workbook describe rows
        that are no longer on screen.
        """
        with self._lock:
            if keys is None:
                if not self._pending:
                    return
                self._pending.clear()
            else:
                targets = set(keys)
                if not targets & self._pending:
                    return
                self._pending -= targets
        self._notify()
