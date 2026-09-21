"""English to Vietnamese translation, the last-resort meaning source.

Lowest priority (FR-3.3): a Vietnamese gloss is better than nothing but teaches
less than an English definition, so it only wins when both dictionaries came back
empty.

Per FR-3.4 the translation becomes the Meaning and the Example is left blank -- a
translation carries no example sentence, and inventing one would be dishonest.

Uses the keyless endpoint that Google Translate's own web client calls. No API key
means no configuration burden for the user, at the cost of an interface Google does
not formally guarantee. That is acceptable here because this is a fallback: if it
stops working the word still saves with a blank meaning (FR-3.5), which is the same
outcome as being offline.
"""

from __future__ import annotations

import asyncio
from typing import Any

from vocabulary_trainer.domain.models import DefinitionCandidate, LookupSource

__all__ = ["TranslateClient"]

_ENDPOINT = "https://translate.googleapis.com/translate_a/single"


class TranslateClient:
    """Translates a word from English to Vietnamese."""

    def __init__(self, timeout: float = 6.0, target_language: str = "vi") -> None:
        self._timeout = timeout
        self._target = target_language

    @property
    def source(self) -> LookupSource:
        return LookupSource.GOOGLE_TRANSLATE

    def is_available(self) -> bool:
        """Always available: no key required."""
        return True

    async def fetch(self, word: str) -> list[DefinitionCandidate]:
        translation = await self._request(word)
        if not translation:
            return []
        return [
            DefinitionCandidate(
                # No part of speech: a translation says nothing about grammar, so
                # claiming one would let it beat a genuine dictionary match.
                part_of_speech=None,
                meaning=translation,
                example=None,
            )
        ]

    async def _request(self, word: str) -> str | None:
        try:
            import httpx
        except ImportError:  # pragma: no cover - dependency is declared
            return None

        params = {
            "client": "gtx",
            "sl": "en",
            "tl": self._target,
            "dt": "t",
            "q": word.strip(),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(_ENDPOINT, params=params)
                if response.status_code != 200:
                    return None
                return self._parse(response.json())
        except asyncio.CancelledError:
            raise
        except Exception:
            return None

    @staticmethod
    def _parse(payload: Any) -> str | None:
        """Extract the translated text from the nested array response.

        Shape is ``[[[translated, original, ...], ...], ...]`` -- positional and
        undocumented, so every index is checked before use.
        """
        if not isinstance(payload, list) or not payload:
            return None

        segments = payload[0]
        if not isinstance(segments, list):
            return None

        pieces: list[str] = []
        for segment in segments:
            if isinstance(segment, list) and segment:
                text = segment[0]
                if isinstance(text, str):
                    pieces.append(text)

        joined = "".join(pieces).strip()
        return joined or None
