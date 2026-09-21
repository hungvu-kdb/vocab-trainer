"""Tests for concurrent lookup orchestration (FR-3.1 through FR-3.5, NFR-PERF-03)."""

from __future__ import annotations

import asyncio
import time

from vocabulary_trainer.domain.models import (
    DefinitionCandidate,
    LookupSource,
    PartOfSpeech,
)
from vocabulary_trainer.services.lookup_service import LookupService


def run(coro):
    return asyncio.run(coro)


class StubClient:
    """A lookup client with scriptable behaviour."""

    def __init__(
        self,
        source: LookupSource,
        candidates: list[DefinitionCandidate] | None = None,
        *,
        available: bool = True,
        delay: float = 0.0,
        raises: bool = False,
    ) -> None:
        self._source = source
        self._candidates = candidates or []
        self._available = available
        self._delay = delay
        self._raises = raises
        self.fetch_calls = 0

    @property
    def source(self) -> LookupSource:
        return self._source

    def is_available(self) -> bool:
        return self._available

    async def fetch(self, word: str) -> list[DefinitionCandidate]:
        self.fetch_calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raises:
            raise RuntimeError("client misbehaved")
        return list(self._candidates)


def candidate(
    pos: PartOfSpeech | None, meaning: str, example: str | None = None
) -> DefinitionCandidate:
    return DefinitionCandidate(part_of_speech=pos, meaning=meaning, example=example)


class TestSourceSelection:
    def test_free_dictionary_wins_when_all_answer(self) -> None:
        service = LookupService(
            [
                StubClient(LookupSource.FREE_DICTIONARY, [candidate(None, "free")]),
                StubClient(LookupSource.MERRIAM_WEBSTER, [candidate(None, "mw")]),
                StubClient(LookupSource.GOOGLE_TRANSLATE, [candidate(None, "vi")]),
            ]
        )
        result = run(service.lookup("word", PartOfSpeech.NOUN))
        assert result.source is LookupSource.FREE_DICTIONARY
        assert result.meaning == "free"

    def test_all_sources_are_still_queried(self) -> None:
        """Concurrency is the point: every source is asked, priority decides after."""
        clients = [
            StubClient(LookupSource.FREE_DICTIONARY, [candidate(None, "free")]),
            StubClient(LookupSource.MERRIAM_WEBSTER, [candidate(None, "mw")]),
            StubClient(LookupSource.GOOGLE_TRANSLATE, [candidate(None, "vi")]),
        ]
        run(LookupService(clients).lookup("word", PartOfSpeech.NOUN))
        assert all(client.fetch_calls == 1 for client in clients)

    def test_merriam_webster_wins_when_free_dictionary_is_silent(self) -> None:
        service = LookupService(
            [
                StubClient(LookupSource.FREE_DICTIONARY, []),
                StubClient(LookupSource.MERRIAM_WEBSTER, [candidate(None, "mw")]),
                StubClient(LookupSource.GOOGLE_TRANSLATE, [candidate(None, "vi")]),
            ]
        )
        assert run(service.lookup("word", PartOfSpeech.NOUN)).source is (
            LookupSource.MERRIAM_WEBSTER
        )

    def test_translation_wins_when_both_dictionaries_are_silent(self) -> None:
        """FR-3.4: the Vietnamese gloss is the last resort."""
        service = LookupService(
            [
                StubClient(LookupSource.FREE_DICTIONARY, []),
                StubClient(LookupSource.MERRIAM_WEBSTER, []),
                StubClient(LookupSource.GOOGLE_TRANSLATE, [candidate(None, "phổ biến")]),
            ]
        )
        result = run(service.lookup("word", PartOfSpeech.NOUN))
        assert result.source is LookupSource.GOOGLE_TRANSLATE
        assert result.meaning == "phổ biến"

    def test_all_silent_yields_an_empty_none_result(self) -> None:
        """FR-3.5: the word must still be saveable."""
        service = LookupService(
            [
                StubClient(LookupSource.FREE_DICTIONARY, []),
                StubClient(LookupSource.GOOGLE_TRANSLATE, []),
            ]
        )
        result = run(service.lookup("word", PartOfSpeech.NOUN))
        assert result.source is LookupSource.NONE
        assert result.is_empty is True


class TestAvailabilityFiltering:
    def test_unavailable_clients_are_never_called(self) -> None:
        """FR-3.8: no API key means the source is skipped, not called and failed."""
        skipped = StubClient(
            LookupSource.MERRIAM_WEBSTER, [candidate(None, "mw")], available=False
        )
        service = LookupService(
            [StubClient(LookupSource.FREE_DICTIONARY, [candidate(None, "free")]), skipped]
        )
        run(service.lookup("word", PartOfSpeech.NOUN))
        assert skipped.fetch_calls == 0

    def test_result_comes_from_a_lower_priority_source_when_higher_is_unavailable(
        self,
    ) -> None:
        service = LookupService(
            [
                StubClient(
                    LookupSource.FREE_DICTIONARY,
                    [candidate(None, "free")],
                    available=False,
                ),
                StubClient(LookupSource.MERRIAM_WEBSTER, [candidate(None, "mw")]),
            ]
        )
        assert run(service.lookup("word", PartOfSpeech.NOUN)).meaning == "mw"

    def test_no_available_clients_yields_empty(self) -> None:
        service = LookupService(
            [StubClient(LookupSource.FREE_DICTIONARY, [], available=False)]
        )
        assert run(service.lookup("word", PartOfSpeech.NOUN)).source is LookupSource.NONE

    def test_no_clients_at_all_yields_empty(self) -> None:
        assert run(LookupService([]).lookup("word", PartOfSpeech.NOUN)).is_empty is True


class TestPartOfSpeechPreference:
    def test_matching_part_of_speech_is_preferred(self) -> None:
        service = LookupService(
            [
                StubClient(
                    LookupSource.FREE_DICTIONARY,
                    [
                        candidate(PartOfSpeech.NOUN, "noun sense"),
                        candidate(PartOfSpeech.VERB, "verb sense"),
                    ],
                )
            ]
        )
        assert run(service.lookup("word", PartOfSpeech.VERB)).meaning == "verb sense"

    def test_falls_back_to_the_first_candidate(self) -> None:
        service = LookupService(
            [
                StubClient(
                    LookupSource.FREE_DICTIONARY,
                    [candidate(PartOfSpeech.NOUN, "first"), candidate(None, "second")],
                )
            ]
        )
        assert run(service.lookup("word", PartOfSpeech.ADVERB)).meaning == "first"

    def test_example_is_carried_through(self) -> None:
        service = LookupService(
            [
                StubClient(
                    LookupSource.FREE_DICTIONARY,
                    [candidate(PartOfSpeech.NOUN, "meaning", "an example")],
                )
            ]
        )
        assert run(service.lookup("word", PartOfSpeech.NOUN)).example == "an example"


class TestConcurrency:
    def test_sources_run_in_parallel_not_in_series(self) -> None:
        """Three 0.2s sources must finish in well under 0.6s."""
        service = LookupService(
            [
                StubClient(LookupSource.FREE_DICTIONARY, [], delay=0.2),
                StubClient(LookupSource.MERRIAM_WEBSTER, [], delay=0.2),
                StubClient(
                    LookupSource.GOOGLE_TRANSLATE, [candidate(None, "vi")], delay=0.2
                ),
            ]
        )
        started = time.monotonic()
        result = run(service.lookup("word", PartOfSpeech.NOUN))
        elapsed = time.monotonic() - started

        assert result.meaning == "vi"
        assert elapsed < 0.5, f"took {elapsed:.2f}s, suggesting serial execution"

    def test_a_slow_source_does_not_delay_the_result_past_the_timeout(self) -> None:
        """NFR-PERF-03: one hung source must not stall the whole lookup."""
        service = LookupService(
            [
                StubClient(LookupSource.FREE_DICTIONARY, [], delay=10.0),
                StubClient(LookupSource.MERRIAM_WEBSTER, [candidate(None, "mw")]),
            ],
            timeout=0.3,
        )
        started = time.monotonic()
        result = run(service.lookup("word", PartOfSpeech.NOUN))
        elapsed = time.monotonic() - started

        assert result.meaning == "mw"
        assert elapsed < 1.0

    def test_timed_out_source_is_treated_as_no_answer(self) -> None:
        """A missing source and an empty source are equivalent to selection."""
        service = LookupService(
            [StubClient(LookupSource.FREE_DICTIONARY, [candidate(None, "too slow")], delay=5.0)],
            timeout=0.2,
        )
        assert run(service.lookup("word", PartOfSpeech.NOUN)).source is LookupSource.NONE

    def test_all_sources_timing_out_yields_empty(self) -> None:
        service = LookupService(
            [
                StubClient(LookupSource.FREE_DICTIONARY, [candidate(None, "a")], delay=5.0),
                StubClient(LookupSource.MERRIAM_WEBSTER, [candidate(None, "b")], delay=5.0),
            ],
            timeout=0.2,
        )
        assert run(service.lookup("word", PartOfSpeech.NOUN)).is_empty is True


class TestRobustness:
    def test_a_raising_client_does_not_fail_the_lookup(self) -> None:
        """The protocol says fetch never raises; if one does anyway, the lookup
        still produces whatever the other sources found."""
        service = LookupService(
            [
                StubClient(LookupSource.FREE_DICTIONARY, [], raises=True),
                StubClient(LookupSource.MERRIAM_WEBSTER, [candidate(None, "mw")]),
            ]
        )
        assert run(service.lookup("word", PartOfSpeech.NOUN)).meaning == "mw"

    def test_every_client_raising_yields_empty_rather_than_propagating(self) -> None:
        service = LookupService(
            [
                StubClient(LookupSource.FREE_DICTIONARY, raises=True),
                StubClient(LookupSource.MERRIAM_WEBSTER, raises=True),
            ]
        )
        assert run(service.lookup("word", PartOfSpeech.NOUN)).source is LookupSource.NONE

    def test_blank_word_short_circuits_without_calling_clients(self) -> None:
        client = StubClient(LookupSource.FREE_DICTIONARY, [candidate(None, "x")])
        service = LookupService([client])
        assert run(service.lookup("   ", PartOfSpeech.NOUN)).is_empty is True
        assert client.fetch_calls == 0

    def test_a_client_returning_only_unusable_candidates_is_skipped(self) -> None:
        service = LookupService(
            [
                StubClient(LookupSource.FREE_DICTIONARY, []),
                StubClient(LookupSource.MERRIAM_WEBSTER, [candidate(None, "mw")]),
            ]
        )
        assert run(service.lookup("word", PartOfSpeech.NOUN)).meaning == "mw"
