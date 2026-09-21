"""Tests for practice session history (FR-6.16)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from vocabulary_trainer.data.history_store import HistoryStore
from vocabulary_trainer.domain.models import SessionSummary


@pytest.fixture
def store(tmp_path: Path) -> HistoryStore:
    return HistoryStore(tmp_path / "history.json")


def summary(score: int = 142, when: datetime | None = None) -> SessionSummary:
    return SessionSummary(
        score=score,
        words_practiced=170,
        total_penalties=28,
        elapsed=timedelta(minutes=18, seconds=42),
        finished_at=when or datetime(2026, 9, 12, 10, 24, 0),
    )


class TestAppend:
    def test_records_a_session(self, store: HistoryStore) -> None:
        assert store.append(summary()) is True
        sessions = store.all_sessions()
        assert len(sessions) == 1
        assert sessions[0].score == 142

    def test_round_trips_every_field(self, store: HistoryStore) -> None:
        original = summary()
        store.append(original)
        stored = store.all_sessions()[0]
        assert stored.score == original.score
        assert stored.words_practiced == original.words_practiced
        assert stored.total_penalties == original.total_penalties
        assert stored.elapsed == original.elapsed
        assert stored.finished_at == original.finished_at

    def test_appends_rather_than_replacing(self, store: HistoryStore) -> None:
        store.append(summary(score=10))
        store.append(summary(score=20))
        store.append(summary(score=30))
        assert [s.score for s in store.all_sessions()] == [10, 20, 30]

    def test_preserves_chronological_order(self, store: HistoryStore) -> None:
        store.append(summary(when=datetime(2026, 1, 1, 9, 0)))
        store.append(summary(when=datetime(2026, 6, 1, 9, 0)))
        recorded = [s.finished_at for s in store.all_sessions()]
        assert recorded == sorted(recorded)

    def test_negative_scores_are_stored(self, store: HistoryStore) -> None:
        """Score can genuinely be negative (FR-6.10)."""
        store.append(summary(score=-12))
        assert store.all_sessions()[0].score == -12

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path / "a" / "b" / "history.json")
        assert store.append(summary()) is True
        assert store.path.exists()

    def test_leaves_no_temp_files(self, store: HistoryStore) -> None:
        store.append(summary())
        assert list(store.path.parent.glob(".history-*")) == []

    def test_trims_to_the_retention_cap(self, store: HistoryStore) -> None:
        """History is informational, so it is capped rather than unbounded."""
        records = [
            {
                "score": index,
                "words_practiced": 1,
                "total_penalties": 0,
                "elapsed_seconds": 1.0,
                "finished_at": "2026-01-01T00:00:00",
            }
            for index in range(600)
        ]
        store.path.write_text(json.dumps(records), encoding="utf-8")

        store.append(summary(score=9999))
        sessions = store.all_sessions()

        assert len(sessions) == 500
        # The newest record survives; the oldest are dropped.
        assert sessions[-1].score == 9999


class TestReadTolerance:
    def test_missing_file_reads_as_empty(self, store: HistoryStore) -> None:
        assert store.all_sessions() == []

    def test_malformed_json_reads_as_empty(self, store: HistoryStore) -> None:
        store.path.write_text("{{{not json", encoding="utf-8")
        assert store.all_sessions() == []

    def test_non_list_json_reads_as_empty(self, store: HistoryStore) -> None:
        store.path.write_text(json.dumps({"score": 1}), encoding="utf-8")
        assert store.all_sessions() == []

    def test_unparseable_records_are_skipped_not_fatal(self, store: HistoryStore) -> None:
        store.path.write_text(
            json.dumps(
                [
                    {"score": "bad"},
                    {
                        "score": 50,
                        "words_practiced": 10,
                        "total_penalties": 2,
                        "elapsed_seconds": 60.0,
                        "finished_at": "2026-05-01T12:00:00",
                    },
                    {"missing": "fields"},
                ]
            ),
            encoding="utf-8",
        )
        sessions = store.all_sessions()
        assert len(sessions) == 1
        assert sessions[0].score == 50

    def test_append_survives_a_corrupt_existing_file(self, store: HistoryStore) -> None:
        """A bad history file must not stop new sessions being recorded."""
        store.path.write_text("garbage", encoding="utf-8")
        assert store.append(summary()) is True
        assert len(store.all_sessions()) == 1


class TestFailureHandling:
    def test_append_returns_false_rather_than_raising(
        self, store: HistoryStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """E6-S6 branch 4a: the summary must still display."""

        def deny(*_args: object, **_kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(
            "vocabulary_trainer.data.history_store.tempfile.mkstemp", deny
        )
        assert store.append(summary()) is False
