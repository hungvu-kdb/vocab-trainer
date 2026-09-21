"""Tests for the four lookup clients.

No live network calls: every test either exercises the pure parser directly or
substitutes the transport. That keeps the suite fast, offline-safe, and immune to a
third-party API changing its data. The local dictionary client needs no such
substitution -- it never makes a network call in the first place -- so its tests
point it at a small temp JSON file instead of the ~45MB bundled one.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from vocabulary_trainer.domain.models import LookupSource, PartOfSpeech
from vocabulary_trainer.integrations.free_dictionary_client import FreeDictionaryClient
from vocabulary_trainer.integrations.local_dictionary_client import LocalDictionaryClient
from vocabulary_trainer.integrations.merriam_webster_client import MerriamWebsterClient
from vocabulary_trainer.integrations.translate_client import TranslateClient


def run(coro):
    return asyncio.run(coro)


class TestFreeDictionaryParsing:
    def test_extracts_definition_and_example(self) -> None:
        payload = [
            {
                "word": "ubiquitous",
                "meanings": [
                    {
                        "partOfSpeech": "adjective",
                        "definitions": [
                            {
                                "definition": "present everywhere",
                                "example": "Phones are ubiquitous.",
                            }
                        ],
                    }
                ],
            }
        ]
        candidates = FreeDictionaryClient._parse(payload)
        assert len(candidates) == 1
        assert candidates[0].part_of_speech is PartOfSpeech.ADJECTIVE
        assert candidates[0].meaning == "present everywhere"
        assert candidates[0].example == "Phones are ubiquitous."

    def test_flattens_multiple_parts_of_speech(self) -> None:
        payload = [
            {
                "meanings": [
                    {
                        "partOfSpeech": "noun",
                        "definitions": [{"definition": "a noun sense"}],
                    },
                    {
                        "partOfSpeech": "verb",
                        "definitions": [{"definition": "a verb sense"}],
                    },
                ]
            }
        ]
        candidates = FreeDictionaryClient._parse(payload)
        assert [c.part_of_speech for c in candidates] == [
            PartOfSpeech.NOUN,
            PartOfSpeech.VERB,
        ]

    def test_unmodelled_part_of_speech_becomes_none(self) -> None:
        """None keeps the candidate usable via fallback without letting it
        masquerade as a genuine match (FR-3.2)."""
        payload = [
            {
                "meanings": [
                    {
                        "partOfSpeech": "preposition",
                        "definitions": [{"definition": "a sense"}],
                    }
                ]
            }
        ]
        assert FreeDictionaryClient._parse(payload)[0].part_of_speech is None

    def test_missing_example_is_none(self) -> None:
        payload = [
            {"meanings": [{"partOfSpeech": "noun", "definitions": [{"definition": "d"}]}]}
        ]
        assert FreeDictionaryClient._parse(payload)[0].example is None

    def test_blank_example_is_none(self) -> None:
        payload = [
            {
                "meanings": [
                    {
                        "partOfSpeech": "noun",
                        "definitions": [{"definition": "d", "example": "   "}],
                    }
                ]
            }
        ]
        assert FreeDictionaryClient._parse(payload)[0].example is None

    @pytest.mark.parametrize(
        "payload",
        [
            None,
            {},
            "a string",
            [],
            [None],
            ["not a dict"],
            [{"meanings": "not a list"}],
            [{"meanings": [{"definitions": "not a list"}]}],
            [{"meanings": [{"definitions": [{"definition": ""}]}]}],
            [{"meanings": [{"definitions": [{"definition": None}]}]}],
            [{"meanings": [{"definitions": ["not a dict"]}]}],
            [{"no_meanings_key": True}],
        ],
    )
    def test_malformed_payloads_yield_no_candidates(self, payload: object) -> None:
        """Third-party JSON can change shape without notice; a surprise must
        degrade to 'no result' rather than raise."""
        assert FreeDictionaryClient._parse(payload) == []

    def test_source_and_availability(self) -> None:
        client = FreeDictionaryClient()
        assert client.source is LookupSource.FREE_DICTIONARY
        assert client.is_available() is True


class TestMerriamWebsterParsing:
    def test_extracts_shortdef_and_part_of_speech(self) -> None:
        payload = [{"fl": "adjective", "shortdef": ["present everywhere"]}]
        candidates = MerriamWebsterClient._parse(payload)
        assert candidates[0].part_of_speech is PartOfSpeech.ADJECTIVE
        assert candidates[0].meaning == "present everywhere"

    def test_strips_inline_markup_tokens(self) -> None:
        payload = [{"fl": "noun", "shortdef": ["{bc}a strong {wi}desire{/wi} to know"]}]
        assert MerriamWebsterClient._parse(payload)[0].meaning == "a strong desire to know"

    def test_digs_an_example_out_of_the_nested_sense_tree(self) -> None:
        payload = [
            {
                "fl": "noun",
                "shortdef": ["a strong desire to know"],
                "def": [
                    {
                        "sseq": [
                            [
                                [
                                    "sense",
                                    {
                                        "dt": [
                                            ["text", "{bc}the desire to know"],
                                            [
                                                "vis",
                                                [{"t": "driven by {wi}curiosity{/wi}"}],
                                            ],
                                        ]
                                    },
                                ]
                            ]
                        ]
                    }
                ],
            }
        ]
        assert MerriamWebsterClient._parse(payload)[0].example == "driven by curiosity"

    def test_spelling_suggestions_are_not_treated_as_definitions(self) -> None:
        """A not-found response is HTTP 200 with a list of plain strings. Storing
        one as a definition would be worse than returning nothing."""
        assert MerriamWebsterClient._parse(["ubiquity", "ubiquitously"]) == []

    def test_multiple_shortdefs_become_multiple_candidates(self) -> None:
        payload = [{"fl": "verb", "shortdef": ["first sense", "second sense"]}]
        assert len(MerriamWebsterClient._parse(payload)) == 2

    def test_unmodelled_label_becomes_none(self) -> None:
        payload = [{"fl": "conjunction", "shortdef": ["a sense"]}]
        assert MerriamWebsterClient._parse(payload)[0].part_of_speech is None

    @pytest.mark.parametrize(
        "payload",
        [None, {}, [], [None], [{"fl": "noun"}], [{"shortdef": "not a list"}], [{"shortdef": [""]}]],
    )
    def test_malformed_payloads_yield_no_candidates(self, payload: object) -> None:
        assert MerriamWebsterClient._parse(payload) == []

    def test_unavailable_without_a_key(self) -> None:
        """FR-3.8: no key means the orchestrator skips this source entirely."""
        assert MerriamWebsterClient().is_available() is False
        assert MerriamWebsterClient(api_key="").is_available() is False
        assert MerriamWebsterClient(api_key="   ").is_available() is False

    def test_available_with_a_key(self) -> None:
        assert MerriamWebsterClient(api_key="abc-123").is_available() is True

    def test_key_can_be_set_at_runtime(self) -> None:
        """A Settings change must take effect without restarting the app."""
        client = MerriamWebsterClient()
        assert client.is_available() is False
        client.set_api_key("abc-123")
        assert client.is_available() is True
        client.set_api_key(None)
        assert client.is_available() is False

    def test_fetch_without_a_key_returns_empty_without_calling_out(self) -> None:
        assert run(MerriamWebsterClient().fetch("ubiquitous")) == []

    def test_source(self) -> None:
        assert MerriamWebsterClient().source is LookupSource.MERRIAM_WEBSTER


class TestTranslateParsing:
    def test_extracts_the_translation(self) -> None:
        payload = [[["phổ biến", "ubiquitous", None, None, 1]], None, "en"]
        assert TranslateClient._parse(payload) == "phổ biến"

    def test_joins_multiple_segments(self) -> None:
        payload = [[["hello ", "hi ", None], ["world", "world", None]]]
        assert TranslateClient._parse(payload) == "hello world"

    @pytest.mark.parametrize(
        "payload",
        [None, [], {}, "text", [None], ["not a list"], [[]], [[None]], [[[]]], [[["   "]]]],
    )
    def test_malformed_payloads_yield_none(self, payload: object) -> None:
        assert TranslateClient._parse(payload) is None

    def test_candidate_has_no_part_of_speech(self) -> None:
        """A translation says nothing about grammar, so claiming a part of speech
        would let it beat a genuine dictionary match."""

        async def scenario() -> None:
            client = TranslateClient()

            async def fake_request(_word: str) -> str:
                return "phổ biến"

            client._request = fake_request  # type: ignore[method-assign]
            candidates = await client.fetch("ubiquitous")
            assert len(candidates) == 1
            assert candidates[0].part_of_speech is None
            assert candidates[0].meaning == "phổ biến"
            assert candidates[0].example is None

        run(scenario())

    def test_no_translation_yields_no_candidates(self) -> None:
        async def scenario() -> None:
            client = TranslateClient()

            async def fake_request(_word: str) -> None:
                return None

            client._request = fake_request  # type: ignore[method-assign]
            assert await client.fetch("ubiquitous") == []

        run(scenario())

    def test_source_and_availability(self) -> None:
        client = TranslateClient()
        assert client.source is LookupSource.GOOGLE_TRANSLATE
        assert client.is_available() is True


class TestLocalDictionaryClient:
    """The bundled offline dictionary -- the only source with no network at all."""

    @staticmethod
    def _write(tmp_path: Path, data: object) -> Path:
        path = tmp_path / "dict.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_finds_a_known_word(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            {
                "ubiquitous": {
                    "word": "ubiquitous",
                    "meanings": [
                        {
                            "definition": "present everywhere",
                            "examples": ["Phones are ubiquitous."],
                            "pos": "adjective",
                        }
                    ],
                }
            },
        )
        client = LocalDictionaryClient(path)
        candidates = run(client.fetch("ubiquitous"))
        assert len(candidates) == 1
        assert candidates[0].meaning == "present everywhere"
        assert candidates[0].example == "Phones are ubiquitous."
        assert candidates[0].part_of_speech is PartOfSpeech.ADJECTIVE

    def test_lookup_is_case_and_whitespace_tolerant(self, tmp_path: Path) -> None:
        """Routed through ``normalize_word``, same as duplicate detection (FR-4.1)
        and practice answer matching, so this source cannot disagree with them
        about what counts as the same word."""
        path = self._write(
            tmp_path,
            {"give up": {"word": "give up", "meanings": [{"definition": "quit", "examples": [], "pos": "verb"}]}},
        )
        client = LocalDictionaryClient(path)
        assert run(client.fetch("  GIVE   UP  "))[0].meaning == "quit"

    def test_unknown_word_yields_no_candidates(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, {"cat": {"word": "cat", "meanings": []}})
        client = LocalDictionaryClient(path)
        assert run(client.fetch("nonexistentword")) == []

    def test_adjective_satellite_maps_to_adjective(self, tmp_path: Path) -> None:
        """WordNet's near-synonym adjective sense has no separate chip in the
        Collect card, so it counts as a plain adjective match rather than an
        unrecognized part of speech."""
        path = self._write(
            tmp_path,
            {
                "ubiquitous": {
                    "word": "ubiquitous",
                    "meanings": [
                        {"definition": "d", "examples": [], "pos": "adjective satellite"}
                    ],
                }
            },
        )
        client = LocalDictionaryClient(path)
        assert run(client.fetch("ubiquitous"))[0].part_of_speech is PartOfSpeech.ADJECTIVE

    def test_unmodelled_part_of_speech_becomes_none(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            {"foo": {"word": "foo", "meanings": [{"definition": "d", "examples": [], "pos": "interjection"}]}},
        )
        client = LocalDictionaryClient(path)
        assert run(client.fetch("foo"))[0].part_of_speech is None

    def test_entry_with_no_usable_meaning_is_dropped(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            {"foo": {"word": "foo", "meanings": [{"definition": "   ", "examples": [], "pos": "noun"}]}},
        )
        client = LocalDictionaryClient(path)
        assert run(client.fetch("foo")) == []

    def test_result_is_cached_after_the_first_load(self, tmp_path: Path) -> None:
        """Parsing ~45MB of JSON per lookup would make Collect noticeably slow;
        the file must be read once and kept in memory for the process."""
        path = self._write(
            tmp_path, {"foo": {"word": "foo", "meanings": [{"definition": "d", "examples": [], "pos": "noun"}]}}
        )
        client = LocalDictionaryClient(path)
        run(client.fetch("foo"))

        path.write_text(json.dumps({"foo": {"word": "foo", "meanings": []}}), encoding="utf-8")
        # Still returns the cached result even though the file on disk changed.
        assert run(client.fetch("foo"))[0].meaning == "d"

    def test_missing_file_degrades_to_unavailable_rather_than_raising(
        self, tmp_path: Path
    ) -> None:
        client = LocalDictionaryClient(tmp_path / "does-not-exist.json")
        assert client.is_available() is False
        assert run(client.fetch("anything")) == []

    def test_malformed_json_degrades_to_unavailable_rather_than_raising(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "dict.json"
        path.write_text("not valid json {", encoding="utf-8")
        client = LocalDictionaryClient(path)
        assert client.is_available() is False

    @pytest.mark.parametrize(
        "data",
        [
            [],
            "a string",
            {"foo": "not a dict"},
            {"foo": {"meanings": "not a list"}},
            {"foo": {"meanings": [None]}},
            {"foo": {"meanings": [{"definition": None}]}},
            {123: {"meanings": []}},
        ],
    )
    def test_malformed_entries_degrade_rather_than_raise(
        self, tmp_path: Path, data: object
    ) -> None:
        path = self._write(tmp_path, data)
        client = LocalDictionaryClient(path)
        assert run(client.fetch("foo")) == []

    def test_source_is_available_by_default(self) -> None:
        """No API key and no network needed, so this source is always usable when
        the bundled file is present."""
        client = LocalDictionaryClient()
        assert client.source is LookupSource.LOCAL_DICTIONARY
        assert client.is_available() is True

    def test_the_bundled_file_actually_resolves_a_real_word(self) -> None:
        """Guards against the packaged asset going missing or being renamed --
        this is the one test that touches the real ~45MB dictionary."""
        client = LocalDictionaryClient()
        candidates = run(client.fetch("ubiquitous"))
        assert len(candidates) > 0
        assert any(c.part_of_speech is PartOfSpeech.ADJECTIVE for c in candidates)


class TestFetchNeverRaises:
    """The protocol guarantees this, and the orchestrator relies on it."""

    def test_free_dictionary_returns_empty_on_transport_failure(self) -> None:
        async def scenario() -> None:
            client = FreeDictionaryClient()

            async def boom(_word: str) -> None:
                return None

            client._request = boom  # type: ignore[method-assign]
            assert await client.fetch("anything") == []

        run(scenario())

    def test_merriam_webster_returns_empty_on_transport_failure(self) -> None:
        async def scenario() -> None:
            client = MerriamWebsterClient(api_key="key")

            async def boom(_word: str) -> None:
                return None

            client._request = boom  # type: ignore[method-assign]
            assert await client.fetch("anything") == []

        run(scenario())
