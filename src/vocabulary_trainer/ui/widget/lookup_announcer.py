"""Marshals lookup outcomes onto the UI thread so they can be announced (FR-3.11).

A :class:`LookupHandle` completes on a background worker thread. Building a speech
bubble there would be undefined behaviour -- Qt widgets may only be touched from the
thread that owns them -- so the result has to cross threads first.

A ``QObject`` with a signal is the mechanism for that: a signal emitted from a worker
to a receiver living on the UI thread is delivered as a queued connection, meaning
the slot runs on the UI thread on a later event-loop turn. That is the entire reason
this class exists rather than the Collect card subscribing directly.

It is owned by the Application, not by the Collect card, because the card closes the
instant a word is saved while its lookup keeps running. Anything owned by the card
would be destroyed before the result it was waiting for arrived.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from vocabulary_trainer.domain.models import LookupResult
from vocabulary_trainer.services.collect_service import LookupHandle

__all__ = ["LookupAnnouncer"]


class LookupAnnouncer(QObject):
    """Watches lookup handles and reports their outcome on the UI thread."""

    reported = Signal(str, bool)
    """``(word, found)`` -- emitted on the UI thread once a watched lookup resolves."""

    def watch(self, word: str, handle: LookupHandle) -> None:
        """Announce ``handle``'s outcome when it completes.

        Safe to call for a lookup that has already finished: ``subscribe`` invokes a
        late listener immediately, so the announcement still happens rather than being
        silently dropped.
        """

        def on_complete(result: LookupResult) -> None:
            # Emitting is the thread-crossing step. Everything after this point runs
            # on the UI thread, which is what makes it safe to build a widget there.
            self.reported.emit(word, not result.is_empty)

        handle.subscribe(on_complete)
