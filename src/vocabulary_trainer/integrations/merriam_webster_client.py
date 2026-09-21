"""Merriam-Webster Collegiate Dictionary client.

Second priority. Requires a free API key, so this is the one client that can report
itself unavailable -- which is exactly how FR-3.8's "skip this source when no key is
set" is implemented: the orchestrator simply never calls it.

Response shape, trimmed::

    [ { "fl": "adjective",                     part of speech
        "shortdef": [ "first sense", ... ],    plain-text definitions
        "def": [ { "sseq": [...] } ] } ]       nested sense sequence, holds examples

``shortdef`` is used for the meaning because it is already plain prose.
Merriam-Webster's full ``def`` tree carries examples wrapped in markup tokens like
``{wi}word{/wi}``, which are stripped before use.

A quirk worth knowing: when a word is not found, this API returns HTTP 200 with a
list of *spelling suggestions* -- a list of plain strings rather than entry objects.
Treating that as a result would store a suggestion as a definition, so the parser
checks the element type.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from vocabulary_trainer.domain.models import (
    DefinitionCandidate,
    LookupSource,
    PartOfSpeech,
)

__all__ = ["MerriamWebsterClient"]

_ENDPOINT = "https://www.dictionaryapi.com/api/v3/references/collegiate/json/{word}"

_MARKUP = re.compile(r"\{[^{}]*\}")
"""Merriam-Webster's inline formatting tokens, e.g. ``{wi}...{/wi}``, ``{bc}``."""


class MerriamWebsterClient:
    """Fetches definitions from Merriam-Webster, when a key is configured."""

    def __init__(self, api_key: str | None = None, timeout: float = 6.0) -> None:
        self._api_key = (api_key or "").strip() or None
        self._timeout = timeout

    @property
    def source(self) -> LookupSource:
        return LookupSource.MERRIAM_WEBSTER

    def set_api_key(self, api_key: str | None) -> None:
        """Update the key at runtime, so a Settings change takes effect immediately."""
        self._api_key = (api_key or "").strip() or None

    def is_available(self) -> bool:
        """False without a key, so the orchestrator skips this source (FR-3.8)."""
        return self._api_key is not None

    async def fetch(self, word: str) -> list[DefinitionCandidate]:
        if not self.is_available():
            return []
        payload = await self._request(word)
        if payload is None:
            return []
        return self._parse(payload)

    async def _request(self, word: str) -> Any | None:
        try:
            import httpx
        except ImportError:  # pragma: no cover - dependency is declared
            return None

        url = _ENDPOINT.format(word=word.strip())
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params={"key": self._api_key})
                if response.status_code != 200:
                    return None
                return response.json()
        except asyncio.CancelledError:
            raise
        except Exception:
            return None

    @classmethod
    def _parse(cls, payload: Any) -> list[DefinitionCandidate]:
        if not isinstance(payload, list):
            return []

        candidates: list[DefinitionCandidate] = []

        for entry in payload:
            # A "not found" response is a list of suggestion strings, not entries.
            # Storing one of those as a definition would be worse than no result.
            if not isinstance(entry, dict):
                continue

            pos = _to_part_of_speech(entry.get("fl"))
            example = cls._first_example(entry.get("def"))

            shortdefs = entry.get("shortdef")
            if not isinstance(shortdefs, list):
                continue

            for shortdef in shortdefs:
                if not isinstance(shortdef, str) or not shortdef.strip():
                    continue
                candidates.append(
                    DefinitionCandidate(
                        part_of_speech=pos,
                        meaning=cls._clean(shortdef),
                        example=example,
                    )
                )

        return candidates

    @classmethod
    def _first_example(cls, definitions: object) -> str | None:
        """Dig the first usage example out of the nested sense sequence.

        Merriam-Webster expresses definition content as *tagged pairs* rather than
        keyed objects: a ``dt`` list holds entries like ``["text", "..."]`` and
        ``["vis", [{"t": "..."}]]``, where ``vis`` is a verbal illustration. So the
        example is not reachable by looking up a ``"vis"`` dictionary key -- it is
        the second element of a two-element list whose first element is the literal
        string ``"vis"``.

        The tree is also deeply nested and its depth varies by word, so this walks
        it generically rather than indexing a fixed path.
        """
        for node in cls._walk(definitions):
            # Tagged-pair form: ["vis", [{"t": "..."}]]
            if (
                isinstance(node, list)
                and len(node) == 2
                and node[0] == "vis"
                and isinstance(node[1], list)
            ):
                example = cls._example_from_illustrations(node[1])
                if example is not None:
                    return example

            # Keyed form, seen in some responses: {"vis": [{"t": "..."}]}
            if isinstance(node, dict):
                illustrations = node.get("vis")
                if isinstance(illustrations, list):
                    example = cls._example_from_illustrations(illustrations)
                    if example is not None:
                        return example

        return None

    @classmethod
    def _example_from_illustrations(cls, illustrations: list[Any]) -> str | None:
        for illustration in illustrations:
            if isinstance(illustration, dict):
                text = illustration.get("t")
                if isinstance(text, str) and text.strip():
                    return cls._clean(text)
        return None

    @classmethod
    def _walk(cls, node: object) -> Any:
        """Yield every dict and list encountered anywhere in a nested structure."""
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from cls._walk(value)
        elif isinstance(node, list):
            yield node
            for item in node:
                yield from cls._walk(item)

    @staticmethod
    def _clean(text: str) -> str:
        """Strip Merriam-Webster's inline markup tokens and tidy whitespace."""
        return " ".join(_MARKUP.sub("", text).split()).strip()


def _to_part_of_speech(value: object) -> PartOfSpeech | None:
    if not isinstance(value, str):
        return None
    text = value.strip().casefold()
    for member in PartOfSpeech:
        if member.value == text:
            return member
    # Merriam-Webster uses labels the app does not model, e.g. "preposition",
    # "conjunction", "idiom". None is honest: the candidate stays usable via the
    # fallback path without pretending to be a match.
    return None
