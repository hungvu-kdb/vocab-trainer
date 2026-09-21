"""Tests for master-file change detection (FR-8.8).

The debounce is the substance here: Excel emits a burst of events per save, so a
naive watcher would fire several times and read a half-written file. These tests use
the polling fallback with short intervals to keep them fast and deterministic.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from vocabulary_trainer.data.file_watcher import MasterFileWatcher


@pytest.fixture
def watched_file(tmp_path: Path) -> Path:
    path = tmp_path / "master.xlsx"
    path.write_bytes(b"initial")
    return path


class Recorder:
    """Counts callbacks and lets a test wait for the first one."""

    def __init__(self) -> None:
        self.calls = 0
        self._event = threading.Event()

    def __call__(self) -> None:
        self.calls += 1
        self._event.set()

    def wait(self, timeout: float = 3.0) -> bool:
        return self._event.wait(timeout)


def polling_watcher(
    path: Path, recorder: Recorder, settle: float = 0.15
) -> MasterFileWatcher:
    """A watcher forced onto the polling fallback for deterministic timing."""
    watcher = MasterFileWatcher(
        path, recorder, settle_seconds=settle, poll_interval=0.05
    )
    watcher._start_watchdog = lambda: False  # type: ignore[method-assign]
    return watcher


class TestChangeDetection:
    def test_detects_an_external_modification(
        self, watched_file: Path
    ) -> None:
        recorder = Recorder()
        watcher = polling_watcher(watched_file, recorder)
        watcher.start()
        try:
            time.sleep(0.1)
            watched_file.write_bytes(b"edited in Excel")
            assert recorder.wait() is True
        finally:
            watcher.stop()

    def test_no_callback_without_a_change(self, watched_file: Path) -> None:
        recorder = Recorder()
        watcher = polling_watcher(watched_file, recorder)
        watcher.start()
        try:
            time.sleep(0.5)
            assert recorder.calls == 0
        finally:
            watcher.stop()

    def test_deletion_is_detected(self, watched_file: Path) -> None:
        recorder = Recorder()
        watcher = polling_watcher(watched_file, recorder)
        watcher.start()
        try:
            time.sleep(0.1)
            watched_file.unlink()
            assert recorder.wait() is True
        finally:
            watcher.stop()


class TestDebounce:
    def test_a_burst_of_writes_fires_once(self, watched_file: Path) -> None:
        """Excel's save is several filesystem events; the user cares about one."""
        recorder = Recorder()
        watcher = polling_watcher(watched_file, recorder, settle=0.3)
        watcher.start()
        try:
            time.sleep(0.1)
            for index in range(6):
                watched_file.write_bytes(f"burst {index}".encode())
                time.sleep(0.06)
            assert recorder.wait() is True
            time.sleep(0.4)
            assert recorder.calls == 1
        finally:
            watcher.stop()

    def test_callback_waits_for_quiet(self, watched_file: Path) -> None:
        """Reading mid-burst would yield a truncated or locked file."""
        recorder = Recorder()
        watcher = polling_watcher(watched_file, recorder, settle=0.6)
        watcher.start()
        try:
            time.sleep(0.1)
            watched_file.write_bytes(b"changed")
            time.sleep(0.2)
            assert recorder.calls == 0, "fired before the file had settled"
            assert recorder.wait(timeout=3.0) is True
        finally:
            watcher.stop()


class TestLifecycle:
    def test_stop_prevents_further_callbacks(self, watched_file: Path) -> None:
        recorder = Recorder()
        watcher = polling_watcher(watched_file, recorder)
        watcher.start()
        time.sleep(0.1)
        watcher.stop()

        watched_file.write_bytes(b"after stop")
        time.sleep(0.4)
        assert recorder.calls == 0

    def test_stop_cancels_a_pending_notification(self, watched_file: Path) -> None:
        recorder = Recorder()
        watcher = polling_watcher(watched_file, recorder, settle=1.0)
        watcher.start()
        time.sleep(0.1)
        watched_file.write_bytes(b"changed")
        time.sleep(0.15)
        watcher.stop()

        time.sleep(1.2)
        assert recorder.calls == 0

    def test_double_start_is_harmless(self, watched_file: Path) -> None:
        recorder = Recorder()
        watcher = polling_watcher(watched_file, recorder)
        watcher.start()
        watcher.start()
        try:
            time.sleep(0.1)
            watched_file.write_bytes(b"changed")
            assert recorder.wait() is True
        finally:
            watcher.stop()

    def test_double_stop_is_harmless(self, watched_file: Path) -> None:
        watcher = polling_watcher(watched_file, Recorder())
        watcher.start()
        watcher.stop()
        watcher.stop()

    def test_stop_before_start_is_harmless(self, watched_file: Path) -> None:
        polling_watcher(watched_file, Recorder()).stop()


class TestListenerFailure:
    def test_a_raising_listener_does_not_kill_the_watcher(
        self, watched_file: Path
    ) -> None:
        """Otherwise one bad callback would silently end all future reloads."""
        calls = {"count": 0}
        done = threading.Event()

        def listener() -> None:
            calls["count"] += 1
            done.set()
            raise RuntimeError("listener blew up")

        watcher = MasterFileWatcher(
            watched_file, listener, settle_seconds=0.15, poll_interval=0.05
        )
        watcher._start_watchdog = lambda: False  # type: ignore[method-assign]
        watcher.start()
        try:
            time.sleep(0.1)
            watched_file.write_bytes(b"first change")
            assert done.wait(3.0) is True

            done.clear()
            time.sleep(0.3)
            watched_file.write_bytes(b"second change")
            assert done.wait(3.0) is True, "watcher stopped after a listener raised"
            assert calls["count"] >= 2
        finally:
            watcher.stop()


class TestMissingFile:
    def test_watching_an_absent_file_then_creating_it(self, tmp_path: Path) -> None:
        target = tmp_path / "not-yet.xlsx"
        recorder = Recorder()
        watcher = polling_watcher(target, recorder)
        watcher.start()
        try:
            time.sleep(0.1)
            target.write_bytes(b"now it exists")
            assert recorder.wait() is True
        finally:
            watcher.stop()
