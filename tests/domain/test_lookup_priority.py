"""Tests for definition and source selection (FR-3.2, FR-3.3, FR-3.5)."""

from __future__ import annotations

import pytest

from vocabulary_trainer.domain.lookup_priority import (
    PRIORITY,
    select_definition,
    select_result,
)
from vocabulary_trainer.domain.models import (
    DefinitionCandidate,
    LookupResult,
    LookupSource,
    PartOfSpeech,
)


def candidate(
    pos: PartOfSpeech | None, meaning: str, example: str | None = None
) -> DefinitionCandidate:
    return DefinitionCandidate(part_of_speech=pos, meaning=meaning, example=example)


def result(source: LookupSource, meaning: str | None) -> LookupResult:
    return LookupResult(meaning=meaning, example=None, source=source)


class TestSelectDefinition:
    def test_prefers_matching_part_of_speech(self) -> None:
        candidates = [
            candidate(PartOfSpeech.NOUN, "a noun sense"),
            candidate(PartOfSpeech.VERB, "a verb sense"),
        ]
        chosen = select_definition(candidates, PartOfSpeech.VERB)
        assert chosen is not None
        assert chosen.meaning == "a verb sense"

    def test_falls_back_to_first_when_no_match(self) -> None:
        """Sources order definitions roughly by commonness, so first is meaningful."""
        candidates = [
            candidate(PartOfSpeech.NOUN, "the common noun sense"),
            candidate(PartOfSpeech.ADJECTIVE, "an adjective sense"),
        ]
        chosen = select_definition(candidates, PartOfSpeech.ADVERB)
        assert chosen is not None
        assert chosen.meaning == "the common noun sense"

    def test_empty_candidates_returns_none(self) -> None:
        assert select_definition([], PartOfSpeech.NOUN) is None

    def test_first_of_several_matches_wins(self) -> None:
        candidates = [
            candidate(PartOfSpeech.NOUN, "first noun"),
            candidate(PartOfSpeech.NOUN, "second noun"),
        ]
        chosen = select_definition(candidates, PartOfSpeech.NOUN)
        assert chosen is not None
        assert chosen.meaning == "first noun"

    def test_candidate_without_part_of_speech_only_wins_by_fallback(self) -> None:
        """A known match should always beat an unknown."""
        candidates = [
            candidate(None, "unlabelled sense"),
            candidate(PartOfSpeech.VERB, "labelled verb sense"),
        ]
        chosen = select_definition(candidates, PartOfSpeech.VERB)
        assert chosen is not None
        assert chosen.meaning == "labelled verb sense"

    def test_unlabelled_sole_candidate_is_used(self) -> None:
        chosen = select_definition([candidate(None, "only sense")], PartOfSpeech.NOUN)
        assert chosen is not None
        assert chosen.meaning == "only sense"

    def test_preserves_example(self) -> None:
        candidates = [candidate(PartOfSpeech.NOUN, "meaning", "an example sentence")]
        chosen = select_definition(candidates, PartOfSpeech.NOUN)
        assert chosen is not None
        assert chosen.example == "an example sentence"


class TestSelectResult:
    def test_priority_order_is_local_then_dictionaries_then_translation(self) -> None:
        """Ollama first when enabled, then the offline dictionary, then the web ones.

        Ollama leads because switching it on is an explicit statement that its
        phrasing is preferred, and it is unavailable -- so absent from selection
        entirely -- unless the user turned it on and chose a model (FR-3.10). The
        bundled offline dictionary outranks the remaining sources because it needs
        no network at all (v3 workflow decision).
        """
        assert PRIORITY == (
            LookupSource.OLLAMA,
            LookupSource.LOCAL_DICTIONARY,
            LookupSource.FREE_DICTIONARY,
            LookupSource.MERRIAM_WEBSTER,
            LookupSource.GOOGLE_TRANSLATE,
        )

    @pytest.mark.parametrize(
        "source",
        [
            LookupSource.FREE_DICTIONARY,
            LookupSource.MERRIAM_WEBSTER,
            LookupSource.GOOGLE_TRANSLATE,
        ],
    )
    def test_single_answering_source_is_used(self, source: LookupSource) -> None:
        chosen = select_result({source: result(source, "a meaning")})
        assert chosen.source is source
        assert chosen.meaning == "a meaning"

    def test_free_dictionary_beats_the_others(self) -> None:
        chosen = select_result(
            {
                LookupSource.FREE_DICTIONARY: result(
                    LookupSource.FREE_DICTIONARY, "free"
                ),
                LookupSource.MERRIAM_WEBSTER: result(LookupSource.MERRIAM_WEBSTER, "mw"),
                LookupSource.GOOGLE_TRANSLATE: result(
                    LookupSource.GOOGLE_TRANSLATE, "vi"
                ),
            }
        )
        assert chosen.source is LookupSource.FREE_DICTIONARY

    def test_merriam_webster_beats_translation(self) -> None:
        chosen = select_result(
            {
                LookupSource.MERRIAM_WEBSTER: result(LookupSource.MERRIAM_WEBSTER, "mw"),
                LookupSource.GOOGLE_TRANSLATE: result(
                    LookupSource.GOOGLE_TRANSLATE, "vi"
                ),
            }
        )
        assert chosen.source is LookupSource.MERRIAM_WEBSTER

    def test_empty_high_priority_result_defers_to_lower(self) -> None:
        """An empty response must not beat a usable one purely on rank."""
        chosen = select_result(
            {
                LookupSource.FREE_DICTIONARY: result(LookupSource.FREE_DICTIONARY, None),
                LookupSource.MERRIAM_WEBSTER: result(
                    LookupSource.MERRIAM_WEBSTER, "usable"
                ),
            }
        )
        assert chosen.source is LookupSource.MERRIAM_WEBSTER
        assert chosen.meaning == "usable"

    def test_blank_meaning_counts_as_empty(self) -> None:
        chosen = select_result(
            {
                LookupSource.FREE_DICTIONARY: result(LookupSource.FREE_DICTIONARY, "   "),
                LookupSource.MERRIAM_WEBSTER: result(
                    LookupSource.MERRIAM_WEBSTER, "usable"
                ),
            }
        )
        assert chosen.source is LookupSource.MERRIAM_WEBSTER

    def test_all_empty_returns_none_source(self) -> None:
        chosen = select_result(
            {
                LookupSource.FREE_DICTIONARY: result(LookupSource.FREE_DICTIONARY, None),
                LookupSource.MERRIAM_WEBSTER: result(LookupSource.MERRIAM_WEBSTER, ""),
            }
        )
        assert chosen.source is LookupSource.NONE
        assert chosen.meaning is None
        assert chosen.is_empty is True

    def test_no_sources_at_all_returns_none_source(self) -> None:
        """Offline: nothing answered (FR-3.5)."""
        chosen = select_result({})
        assert chosen.source is LookupSource.NONE
        assert chosen.is_empty is True

    def test_missing_key_is_treated_as_no_answer(self) -> None:
        """A source that timed out or lacked an API key simply is not present."""
        chosen = select_result(
            {LookupSource.GOOGLE_TRANSLATE: result(LookupSource.GOOGLE_TRANSLATE, "vi")}
        )
        assert chosen.source is LookupSource.GOOGLE_TRANSLATE


class TestLookupResultIsEmpty:
    @pytest.mark.parametrize("meaning", [None, "", "   ", "\t\n"])
    def test_empty_meanings(self, meaning: str | None) -> None:
        assert LookupResult(meaning, None, LookupSource.FREE_DICTIONARY).is_empty is True

    def test_usable_meaning(self) -> None:
        assert (
            LookupResult("a real meaning", None, LookupSource.FREE_DICTIONARY).is_empty
            is False
        )

    def test_empty_factory(self) -> None:
        empty = LookupResult.empty()
        assert empty.is_empty is True
        assert empty.source is LookupSource.NONE
        assert empty.example is None
