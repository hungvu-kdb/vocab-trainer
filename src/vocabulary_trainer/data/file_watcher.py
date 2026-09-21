"""Detecting external edits to the master workbook (FR-8.8).

A user who tidies entries directly in Excel should not then see stale data in the
app, nor have their corrections overwritten. This watcher notices the change and
signals that a reload is needed.

The debounce is the substance of this module. Excel does not write a workbook in
one operation -- it emits a burst of create, modify, and rename events, and reading
mid-burst yields a truncated or locked file. So a change is only reported once the
file has been quiet for a settling interval (E8-S5 branch 3b).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

__all__ = ["MasterFileWatcher"]

_SETTLE_SECONDS = 0.75
"""How long the file must be quiet before a change is reported.

Long enough to span Excel's multi-event save burst, short enough that a user who
alt-tabs back sees fresh data. Tuned by feel rather than measurement; the only hard
requirement is that it exceeds one save burst.
"""


class MasterFileWatcher:
    """Watches one file and reports settled changes.

    Uses ``watchdog`` when available and falls back to polling when it is not, so
    the feature degrades rather than becoming a hard dependency.
    """

    def __init__(
        self,
        path: Path,
        on_change: Callable[[], None],
        settle_seconds: float = _SETTLE_SECONDS,
        poll_interval: float = 1.0,
    ) -> None:
        self._path = Path(path)
        self._on_change = on_change
        self._settle_seconds = settle_seconds
        self._poll_interval = poll_interval

        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._observer: object | None = None
        self._poll_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_signature: tuple[int, float] | None = None

    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin watching. Safe to call when already started."""
        with self._lock:
            if self._observer is not None or self._poll_thread is not None:
                return
            self._last_signature = self._signature()

        if not self._start_watchdog():
            self._start_polling()

    def stop(self) -> None:
        """Stop watching and cancel any pending notification."""
        self._stop_event.set()

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

            observer = self._observer
            self._observer = None

        if observer is not None:
            try:
                observer.stop()  # type: ignore[attr-defined]
                observer.join(timeout=2.0)  # type: ignore[attr-defined]
            except Exception:
                # A watcher that will not shut down cleanly must not block app exit.
                pass

        thread = self._poll_thread
        self._poll_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    # ------------------------------------------------------------------

    def _start_watchdog(self) -> bool:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            return False

        watcher = self

        class _Handler(FileSystemEventHandler):  # pragma: no cover - needs a live FS
            def on_any_event(self, event: object) -> None:
                src = getattr(event, "src_path", "") or ""
                dest = getattr(event, "dest_path", "") or ""
                target = watcher._path.name
                # Excel's save renames a temp file over the target, so the event we
                # care about may name the destination rather than the source.
                if target in str(src) or target in str(dest):
                    watcher._schedule_notification()

        try:
            observer = Observer()
            observer.schedule(_Handler(), str(self._path.parent), recursive=False)
            observer.daemon = True
            observer.start()
        except Exception:
            return False

        with self._lock:
            self._observer = observer
        return True

    def _start_polling(self) -> None:
        """Fallback when watchdog is unavailable: compare size and mtime."""

        def loop() -> None:
            while not self._stop_event.wait(self._poll_interval):
                current = self._signature()
                with self._lock:
                    changed = current != self._last_signature
                    self._last_signature = current
                if changed:
                    self._schedule_notification()

        thread = threading.Thread(target=loop, name="master-file-poller", daemon=True)
        self._poll_thread = thread
        thread.start()

    def _schedule_notification(self) -> None:
        """Restart the settle timer, so only the end of a burst fires a callback."""
        with self._lock:
            if self._stop_event.is_set():
                return
            if self._timer is not None:
                self._timer.cancel()
            timer = threading.Timer(self._settle_seconds, self._fire)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
            if self._stop_event.is_set():
                return
            self._last_signature = self._signature()

        try:
            self._on_change()
        except Exception:
            # A listener that raises must not kill the watcher thread and silently
            # stop all future reload notifications.
            pass

    def _signature(self) -> tuple[int, float] | None:
        try:
            stat = self._path.stat()
        except OSError:
            return None
        return (stat.st_size, stat.st_mtime)
