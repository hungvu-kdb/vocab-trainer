"""Bundled offline dictionary client (WordNet-derived JSON, ``assets/dictionary``).

Highest-priority source (v3 workflow decision): unlike the two web dictionaries,
this one needs no network access at all, so it can never fail the way they did on a
machine where outbound HTTP to the lookup APIs times out or is blocked. That gap is
what motivated adding it -- auto-meaning was silently returning nothing on such a
machine because every network source failed the same way every time.

File shape, one entry per word/phrase, already keyed by its lowercase, single-spaced
form::

    { "ubiquitous": {
        "word": "ubiquitous",
        "meanings": [ { "definition": "...", "examples": [...], "pos": "adjective" } ]
      }, ... }

The file is ~45MB and holds ~127k entries, so it is parsed **once** on first use and
kept in memory for the life of the process rather than re-read per lookup -- reading
it fresh every keystroke would make Collect noticeably sluggish for no benefit, since
the dictionary never changes at runtime.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from vocabulary_trainer.domain.models import DefinitionCandidate, LookupSource, PartOfSpeech
from vocabulary_trainer.domain.natural_key import normalize_word

__all__ = ["LocalDictionaryClient"]

_DEFAULT_PATH = (
    Path(__file__).resolve().parent.parent / "assets" / "dictionary" / "wordnet-2025-dictionary.json"
)


class LocalDictionaryClient:
    """Looks words up in the bundled offline dictionary."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._lock = threading.Lock()
        self._entries: dict[str, list[DefinitionCandidate]] | None = None
        self._load_failed = False

    @property
    def source(self) -> LookupSource:
        return LookupSource.LOCAL_DICTIONARY

    def is_available(self) -> bool:
        """Whether the bundled file exists and parsed successfully.

        Checked lazily on first use rather than at construction, so a missing or
        corrupt file degrades this one source rather than failing app startup --
        the two web dictionaries and translation still work without it.
        """
        return self._ensure_loaded() is not None

    async def fetch(self, word: str) -> list[DefinitionCandidate]:
        """Candidate definitions for ``word``, or an empty list.

        Synchronous in substance -- this is a dict lookup, not I/O -- but the
        protocol requires an ``async`` method so the orchestrator can await it
        alongside the network clients without special-casing this one.
        """
        entries = self._ensure_loaded()
        if entries is None:
            return []
        key = normalize_word(word)
        return list(entries.get(key, []))

    def _ensure_loaded(self) -> dict[str, list[DefinitionCandidate]] | None:
        """Parse the bundled file on first use, then reuse it for the process."""
        with self._lock:
            if self._entries is not None or self._load_failed:
                return self._entries
            try:
                self._entries = self._load()
            except Exception:
                # A missing or corrupt bundled file must not crash the app or the
                # lookup pipeline -- it just means this one source has nothing to
                # offer, same as a network dictionary that failed to respond.
                self._load_failed = True
                self._entries = None
            return self._entries

    def _load(self) -> dict[str, list[DefinitionCandidate]]:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}

        entries: dict[str, list[DefinitionCandidate]] = {}
        for word, record in raw.items():
            if not isinstance(word, str) or not isinstance(record, dict):
                continue
            meanings = record.get("meanings")
            if not isinstance(meanings, list):
                continue

            candidates: list[DefinitionCandidate] = []
            for meaning in meanings:
                if not isinstance(meaning, dict):
                    continue
                definition = meaning.get("definition")
                if not isinstance(definition, str) or not definition.strip():
                    continue

                examples = meaning.get("examples")
                example = (
                    examples[0]
                    if isinstance(examples, list) and examples and isinstance(examples[0], str)
                    else None
                )
                candidates.append(
                    DefinitionCandidate(
                        part_of_speech=_to_part_of_speech(meaning.get("pos")),
                        meaning=definition.strip(),
                        example=example.strip() if example else None,
                    )
                )

            if candidates:
                entries[normalize_word(word)] = candidates

        return entries


def _to_part_of_speech(value: object) -> PartOfSpeech | None:
    """Map the dictionary's ``pos`` tag onto the app's enum.

    WordNet's ``"adjective satellite"`` (a near-synonym adjective sense) has no
    equivalent chip in the Collect card, so it is treated as a plain adjective
    rather than reported as unknown -- an adjective match is still a match.
    Anything else unrecognized becomes ``None``, usable only through the fallback
    path (FR-3.2), same as every other client.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().casefold()
    if text == "adjective satellite":
        return PartOfSpeech.ADJECTIVE
    for member in PartOfSpeech:
        if member.value == text:
            return member
    return None
