"""Root test configuration.

Shared fixtures and fakes live here rather than in a per-directory ``conftest.py``
plus relative imports, because relative imports only work when the test directories
are packages -- and making them packages just to share three helpers is more
machinery than the sharing is worth.

Every fixture below constructs the service layer with **no Qt application object in
the process**. That is deliberate: if the services can be exercised without a
display, then both UI technologies are thin consumers and neither can be hiding
business logic (NFR-TEST-01).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from vocabulary_trainer.data.history_store import HistoryStore
from vocabulary_trainer.data.master_file_repository import MasterFileRepository
from vocabulary_trainer.data.preferences_store import PreferencesStore
from vocabulary_trainer.domain.models import (
    AppPreferences,
    DefinitionCandidate,
    LookupSource,
    PartOfSpeech,
    WordEntry,
)
from vocabulary_trainer.services.clock import FixedClock

FIXED_NOW = datetime(2026, 9, 12, 10, 24, 0)
FIXED_TODAY = date(2026, 9, 12)


# ----------------------------------------------------------------------
# Fakes
# ----------------------------------------------------------------------


class FakeTts:
    """Records what would have been spoken."""

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.spoken: list[str] = []
        self.selected: str | None = None

    def available_voices(self) -> list[object]:
        return [] if not self._available else [object()]

    def select_voice(self, voice_id: str | None) -> None:
        self.selected = voice_id

    def speak(self, text: str) -> bool:
        self.spoken.append(text)
        return self._available


class FakeAudio:
    """Records which feedback sounds were triggered."""

    def __init__(self) -> None:
        self.correct_plays = 0
        self.incorrect_plays = 0

    def play_correct(self) -> None:
        self.correct_plays += 1

    def play_incorrect(self) -> None:
        self.incorrect_plays += 1


class StubLookupClient:
    """A lookup client returning canned candidates."""

    def __init__(
        self,
        source: LookupSource,
        candidates: list[DefinitionCandidate] | None = None,
        available: bool = True,
    ) -> None:
        self._source = source
        self._candidates = candidates or []
        self._available = available

    @property
    def source(self) -> LookupSource:
        return self._source

    def is_available(self) -> bool:
        return self._available

    async def fetch(self, word: str) -> list[DefinitionCandidate]:
        return list(self._candidates)


def make_entry(
    word: str,
    collection: str = "General",
    pos: PartOfSpeech = PartOfSpeech.NOUN,
    meaning: str | None = "a meaning",
    example: str | None = "an example",
    when: date | None = None,
) -> WordEntry:
    """A word entry with sensible defaults, overridable per test."""
    return WordEntry(
        word=word,
        part_of_speech=pos,
        meaning=meaning,
        example=example,
        collection_name=collection,
        collected_on=when or FIXED_TODAY,
    )


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED_NOW)


@pytest.fixture
def repository(tmp_path: Path) -> MasterFileRepository:
    repo = MasterFileRepository(tmp_path / "master.xlsx")
    repo.ensure_workbook()
    return repo


@pytest.fixture
def preferences_store(tmp_path: Path) -> PreferencesStore:
    return PreferencesStore(tmp_path / "preferences.json")


@pytest.fixture
def preferences(tmp_path: Path) -> AppPreferences:
    return AppPreferences(master_file_path=tmp_path / "master.xlsx")


@pytest.fixture
def history(tmp_path: Path) -> HistoryStore:
    return HistoryStore(tmp_path / "history.json")


@pytest.fixture
def fake_tts() -> FakeTts:
    return FakeTts()


@pytest.fixture
def fake_audio() -> FakeAudio:
    return FakeAudio()
