"""Data structures exchanged across the application.

Value objects are frozen so a repository result cannot be mutated by a caller and
silently diverge from what is on disk. The two mutable exceptions are called out
in their own docstrings.

Enums subclass ``StrEnum`` so their values serialize directly into the Excel
workbook and the JSON preference files without a conversion table, and read as
plain human-readable strings when the user opens the workbook in Excel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from pathlib import Path

from vocabulary_trainer.domain.natural_key import natural_key

__all__ = [
    "MAX_WIDGET_SCALE_PERCENT",
    "MIN_WIDGET_SCALE_PERCENT",
    "AboutInfo",
    "AppPreferences",
    "AttemptOutcome",
    "CharacterKind",
    "Collection",
    "CollectionSortMode",
    "CollectionSummary",
    "DefinitionCandidate",
    "DuplicateAction",
    "LookupResult",
    "LookupSource",
    "PartOfSpeech",
    "PracticeLogEntry",
    "PracticeWordState",
    "RepairReport",
    "SessionSummary",
    "VoiceInfo",
    "WidgetState",
    "WordEntry",
    "clamp_widget_scale_percent",
]

# Bounds for the widget size setting, as a percentage of the artwork's natural
# size. Defined here, once, because three layers need the same numbers: the
# preferences store clamps a hand-edited file, the service rejects out-of-range
# input, and the Settings slider renders the range. A second copy would let the
# UI offer a value the service refuses.
#
# 50% keeps the character large enough to remain a clickable target; 300% is
# where it starts crowding a 1080p screen. Both were chosen for that reason
# rather than being arbitrary round numbers.
MIN_WIDGET_SCALE_PERCENT = 50
MAX_WIDGET_SCALE_PERCENT = 300


def clamp_widget_scale_percent(value: int) -> int:
    """Force a scale percentage into the supported range.

    Used by the preferences store on load, where the file may have been edited by
    hand. The service layer rejects out-of-range input outright instead of
    clamping, because silently accepting 900 and storing 300 would make the UI
    disagree with what the user typed.
    """
    return max(MIN_WIDGET_SCALE_PERCENT, min(MAX_WIDGET_SCALE_PERCENT, int(value)))


class PartOfSpeech(StrEnum):
    """Grammatical type of a vocabulary entry.

    These are exactly the chips offered by the Collect card (FR-2.2).
    """

    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"
    PHRASE = "phrase"


class LookupSource(StrEnum):
    """Origin of a meaning and example.

    Declaration order is not the priority order; see
    ``domain.lookup_priority.PRIORITY`` for that.
    """

    OLLAMA = "ollama"
    LOCAL_DICTIONARY = "local_dictionary"
    FREE_DICTIONARY = "free_dictionary"
    MERRIAM_WEBSTER = "merriam_webster"
    GOOGLE_TRANSLATE = "google_translate"
    NONE = "none"


class DuplicateAction(StrEnum):
    """Resolution chosen for a duplicate word (FR-4.3 through FR-4.5).

    ``DELETE_BOTH`` is named for its full effect rather than just "delete",
    because it removes the existing row *and* discards the incoming submission
    (FR-4.6 requires the label make that unambiguous).
    """

    KEEP_OLD = "keep_old"
    REPLACE = "replace"
    DELETE_BOTH = "delete_both"


class CollectionSortMode(StrEnum):
    """Ordering of the practice setup collection list (FR-5.4)."""

    NEWEST_FIRST = "newest_first"
    OLDEST_FIRST = "oldest_first"
    NAME_ASC = "name_asc"


class CharacterKind(StrEnum):
    """Floating widget character (FR-7.4)."""

    CAT = "cat"
    CROCODILE = "crocodile"


class WidgetState(StrEnum):
    """Whether the widget owns an open popup, driving which image renders (FR-1.2)."""

    IDLE = "idle"
    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class WordEntry:
    """One row of the ``Words`` sheet."""

    word: str
    part_of_speech: PartOfSpeech
    meaning: str | None
    example: str | None
    collection_name: str
    collected_on: date

    @property
    def natural_key(self) -> tuple[str, str]:
        """Identity of this entry. Delegates so no caller reimplements the rule."""
        return natural_key(self.word, self.collection_name)


@dataclass(frozen=True, slots=True)
class Collection:
    """One row of the ``Collections`` sheet."""

    name: str
    created_on: date


@dataclass(frozen=True, slots=True)
class CollectionSummary:
    """A collection plus its word count, for list displays."""

    name: str
    created_on: date
    word_count: int


@dataclass(frozen=True, slots=True)
class DefinitionCandidate:
    """One candidate definition from one source, before any selection is made.

    ``part_of_speech`` is optional because not every source reports it. A
    candidate without one can never match a requested part of speech, so it is
    only ever chosen through the fallback path (FR-3.2).
    """

    part_of_speech: PartOfSpeech | None
    meaning: str
    example: str | None = None


@dataclass(frozen=True, slots=True)
class LookupResult:
    """The meaning and example selected for storage, plus where they came from."""

    meaning: str | None
    example: str | None
    source: LookupSource

    @property
    def is_empty(self) -> bool:
        """Whether this result carries no usable meaning.

        A source that responded but returned nothing usable counts as not having
        answered at all. Without this, an empty higher-priority response would
        beat a good lower-priority one purely on rank (FR-3.3).
        """
        return self.meaning is None or not self.meaning.strip()

    @classmethod
    def empty(cls) -> LookupResult:
        """The result used when no source answered (FR-3.5)."""
        return cls(meaning=None, example=None, source=LookupSource.NONE)


@dataclass(slots=True)
class PracticeWordState:
    """A word's progress within one practice session.

    Mutable by design: ``correct_count`` and ``wrong_count`` change as the session
    runs. Both are running totals, not a consecutive streak -- a mistake made after
    two correct answers costs the same one repetition it would have cost before
    them (the "Number Of Repetitions" rule, see ``domain.scoring``). This replaces
    the older streak-based ``consecutive_correct`` counter: previously a wrong
    answer cost score but left mastery progress untouched, whereas now it also
    pushes the word's own finish line back by one, permanently, until a correct
    answer pays it down again.
    """

    entry: WordEntry
    correct_count: int = 0
    wrong_count: int = 0

    def remaining_for(self, required: int) -> int:
        """Correct answers still owed under the NOR rule, floored at zero.

        Wrong answers can raise the effective target above ``required``, but only
        up to a fixed multiple of it (see
        ``domain.scoring.MAX_PENALTY_REPETITIONS_MULTIPLIER``) -- otherwise a
        learner stuck exactly 50/50 on a word could hold this above zero forever
        and the session would never end.
        """
        from vocabulary_trainer.domain.scoring import remaining_repetitions

        return remaining_repetitions(required, self.correct_count, self.wrong_count)

    def is_mastered_at(self, required: int) -> bool:
        """Whether this word has satisfied the NOR rule for this session (FR-6.6).

        ``remaining_for`` is already floored at zero, so this is simply "nothing
        left owed" -- an off-by-one elsewhere still cannot strand the session,
        because the floor guarantees the count can only ever reach exactly zero,
        never skip past it into negative territory unnoticed.
        """
        return self.remaining_for(required) <= 0


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    """Everything the drill screen needs to render after one submitted answer.

    ``remaining_repetitions`` is the NOR figure: correct answers still owed on
    this word under the current rule (``required_correct + wrong_count -
    correct_count``, floored at zero). Replaces the old streak-only
    ``consecutive_correct`` field now that a miss also changes the target.
    """

    was_correct: bool
    correct_spelling: str
    correct_count: int
    wrong_count: int
    remaining_repetitions: int
    required_correct: int
    became_mastered: bool
    score: int
    total_penalties: int
    attempts_made: int
    total_required_attempts: int


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """Final figures for a finished practice session (FR-6.14)."""

    score: int
    words_practiced: int
    total_penalties: int
    elapsed: timedelta
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class PracticeLogEntry:
    """One row of the separate practice-log workbook (FR-6.17, user-requested).

    Distinct from :class:`SessionSummary`: the summary is the score-focused figures
    the in-app summary screen shows, capped and JSON-stored. This is a
    spreadsheet-native record of the same session aimed at answering "when, on
    what, and where did the trouble happen" -- which words needed the most
    correction, and whether the session was actually completed.

    Pure data plus pure formatting: the two string-rendering properties below are
    the only "logic" here, kept in the domain layer so they can be tested without
    touching a workbook, matching how ``WordEntry.natural_key`` and
    ``LookupResult.is_empty`` are handled elsewhere in this module.
    """

    session_date: date
    start_time: time
    end_time: time
    collections: tuple[str, ...]
    penalty: int
    finished: bool
    wrong_counts: tuple[tuple[str, int], ...]
    """``(word, times missed in this session)`` pairs, each count > 0, sorted by
    word for a deterministic row -- insertion order would make two otherwise
    identical sessions log differently depending on shuffle order alone."""

    @property
    def collection_display(self) -> str:
        """Chosen collections joined for a single cell, e.g. ``"General, IELTS"``."""
        return ", ".join(self.collections)

    @property
    def word_with_penalty(self) -> str:
        """``'|'.join(f"{word}_{count}" ...)``, e.g. ``"hello_2|goodbye_3"``.

        Empty string for a session with no misses at all -- Excel and openpyxl
        cannot distinguish that from a genuinely blank cell, so a perfect session
        renders as an empty cell, same as it would for any other blank column.
        """
        return "|".join(f"{word}_{count}" for word, count in self.wrong_counts)


@dataclass(frozen=True, slots=True)
class VoiceInfo:
    """An installed text-to-speech voice (FR-7.5)."""

    voice_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class AboutInfo:
    """Content of the Settings About tab (FR-7.6)."""

    app_name: str
    version: str
    master_file_path: str


@dataclass(frozen=True, slots=True)
class RepairReport:
    """What ``ensure_workbook`` changed, if anything (FR-8.4).

    ``changes`` is empty when the workbook was already valid, which is the signal
    to stay silent rather than warning the user about nothing.
    """

    created_workbook: bool = False
    seeded_default_collection: bool = False
    changes: tuple[str, ...] = ()

    @property
    def needs_user_notice(self) -> bool:
        """Whether the user should be told what happened."""
        return bool(self.changes)


@dataclass(slots=True)
class AppPreferences:
    """Persisted user preferences (FR-7.13).

    Mutable because Settings edits it field by field and saves it back.
    """

    master_file_path: Path
    widget_visible: bool = True
    widget_position: tuple[int, int] | None = None
    character: CharacterKind = CharacterKind.CAT
    # Widget size as a percentage of the artwork's natural size (FR-7.15).
    # Stored as an int rather than a float so the JSON file stays readable and
    # there is no rounding drift between what the slider shows and what is saved.
    widget_scale_percent: int = 100
    # Local-LLM meaning generation via Ollama (FR-3.10). Off by default: it needs
    # software the app does not install, and a machine without Ollama must behave
    # exactly as before.
    ollama_enabled: bool = False
    # None means "no model chosen yet", which is distinct from a model that was
    # chosen and has since been removed from Ollama -- the Settings tab reports
    # the latter rather than silently falling back.
    ollama_model: str | None = None
    tts_voice_id: str | None = None
    merriam_webster_api_key: str | None = None
    start_with_windows: bool = False
    required_correct_writes: int = 3
    last_practiced_collections: tuple[str, ...] = field(default_factory=tuple)
