"""Free Dictionary API client (``api.dictionaryapi.dev``).

Highest priority source: keyless, so it is always available, and it returns
structured JSON with parts of speech already labelled.

Response shape, trimmed to what matters here::

    [ { "word": "...",
        "meanings": [ { "partOfSpeech": "adjective",
                        "definitions": [ { "definition": "...",
                                           "example": "..." } ] } ] } ]

A 404 means "no entry for this word", which is an ordinary outcome rather than an
error -- plenty of the phrases a learner collects are absent from any dictionary.
"""

from __future__ import annotations

import asyncio
from typing import Any

from vocabulary_trainer.domain.models import (
    DefinitionCandidate,
    LookupSource,
    PartOfSpeech,
)

__all__ = ["FreeDictionaryClient"]

_ENDPOINT = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"


class FreeDictionaryClient:
    """Fetches definitions from the Free Dictionary API."""

    def __init__(self, timeout: float = 6.0) -> None:
        self._timeout = timeout

    @property
    def source(self) -> LookupSource:
        return LookupSource.FREE_DICTIONARY

    def is_available(self) -> bool:
        """Always available: this API needs no key."""
        return True

    async def fetch(self, word: str) -> list[DefinitionCandidate]:
        payload = await self._request(word)
        if payload is None:
            return []
        return self._parse(payload)

    async def _request(self, word: str) -> Any | None:
        """Issue the request, converting every failure into ``None``."""
        try:
            import httpx
        except ImportError:  # pragma: no cover - dependency is declared
            return None

        url = _ENDPOINT.format(word=word.strip())
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    # 404 is the common case: no entry for this word.
                    return None
                return response.json()
        except asyncio.CancelledError:
            # Cancellation is the orchestrator enforcing its timeout; let it
            # propagate rather than swallowing it as a lookup failure.
            raise
        except Exception:
            return None

    @staticmethod
    def _parse(payload: Any) -> list[DefinitionCandidate]:
        """Flatten the nested response into candidates, skipping unusable parts.

        Written defensively throughout: this is third-party JSON that can change
        shape without notice, and a surprise here must degrade to "no result"
        rather than raise.
        """
        if not isinstance(payload, list):
            return []

        candidates: list[DefinitionCandidate] = []

        for entry in payload:
            if not isinstance(entry, dict):
                continue
            meanings = entry.get("meanings")
            if not isinstance(meanings, list):
                continue

            for meaning in meanings:
                if not isinstance(meaning, dict):
                    continue
                pos = _to_part_of_speech(meaning.get("partOfSpeech"))
                definitions = meaning.get("definitions")
                if not isinstance(definitions, list):
                    continue

                for definition in definitions:
                    if not isinstance(definition, dict):
                        continue
                    text = definition.get("definition")
                    if not isinstance(text, str) or not text.strip():
                        continue
                    example = definition.get("example")
                    candidates.append(
                        DefinitionCandidate(
                            part_of_speech=pos,
                            meaning=text.strip(),
                            example=example.strip()
                            if isinstance(example, str) and example.strip()
                            else None,
                        )
                    )

        return candidates


def _to_part_of_speech(value: object) -> PartOfSpeech | None:
    """Map an API part-of-speech string onto the app's enum.

    Unrecognized values become ``None`` rather than a wrong guess: a candidate with
    no part of speech can still be chosen through the fallback path, whereas
    mislabelling it would let it beat a genuine match (FR-3.2).
    """
    if not isinstance(value, str):
        return None
    text = value.strip().casefold()
    for member in PartOfSpeech:
        if member.value == text:
            return member
    return None
