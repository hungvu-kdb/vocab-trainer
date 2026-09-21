"""Choosing which definition, and which source, wins.

All three lookup sources are queried concurrently on every lookup, so something
has to decide what gets stored when more than one answers. That decision is pure
and branch-heavy, which is why it lives here rather than inside the service that
performs the network calls -- it can be exhaustively tested with no transport at
all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from vocabulary_trainer.domain.models import (
    DefinitionCandidate,
    LookupResult,
    LookupSource,
    PartOfSpeech,
)

__all__ = ["PRIORITY", "select_definition", "select_result"]


PRIORITY: tuple[LookupSource, ...] = (
    LookupSource.OLLAMA,
    LookupSource.LOCAL_DICTIONARY,
    LookupSource.FREE_DICTIONARY,
    LookupSource.MERRIAM_WEBSTER,
    LookupSource.GOOGLE_TRANSLATE,
)
"""Source preference, highest first (FR-3.3).

Ollama ranks first *when it is available at all*, which it is not unless the user
turned it on and picked a model (FR-3.10). Enabling it is therefore an explicit
statement that its phrasing is preferred, and a source that is off contributes
nothing to this ordering -- so the ranking below is unchanged for everyone who
never touches the setting. It also runs locally, so like the bundled dictionary it
cannot fail for network reasons.

The bundled local dictionary outranks the remaining sources (v3 workflow decision):
it needs no network at all, so it can never fail the way the two web dictionaries
can on a machine with restricted or unreliable outbound access, and a network
dictionary adds nothing over it except staleness. Free Dictionary still outranks
Merriam-Webster because it needs no API key. Dictionaries as a group outrank
translation because an English definition teaches more than a Vietnamese gloss.
"""


def select_definition(
    candidates: Sequence[DefinitionCandidate],
    preferred: PartOfSpeech,
) -> DefinitionCandidate | None:
    """Pick the definition best matching the part of speech the user chose (FR-3.2).

    A candidate whose part of speech matches wins. Failing that, the first
    candidate is returned rather than nothing -- sources order their definitions
    roughly by commonness, so "first available" is a meaningful fallback rather
    than an arbitrary one.

    Candidates that report no part of speech can never match, so they surface only
    through the fallback. That is intended: a known match should always beat an
    unknown one.
    """
    if not candidates:
        return None

    for candidate in candidates:
        if candidate.part_of_speech == preferred:
            return candidate

    return candidates[0]


def select_result(results: Mapping[LookupSource, LookupResult]) -> LookupResult:
    """Pick across sources by priority (FR-3.3), or report none (FR-3.5).

    A source missing from the mapping did not answer -- it may have timed out,
    failed, or been unavailable for want of an API key. A source present but
    carrying an empty meaning is treated identically, so an empty high-priority
    response cannot beat a usable lower-priority one.
    """
    for source in PRIORITY:
        result = results.get(source)
        if result is not None and not result.is_empty:
            return result

    return LookupResult.empty()
