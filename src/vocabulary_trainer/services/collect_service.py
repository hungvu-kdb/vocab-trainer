"""Capturing a word, including duplicate resolution and inline collection creation.

The ordering in :meth:`CollectService.save_word` is the substance of this module. It
is what makes FR-2.8's "save immediately" compatible with FR-3.1's concurrent
lookup: the row is written with whatever has arrived, and enriched later. A slow
dictionary can therefore never cost the user the word they just typed.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum, auto

from vocabulary_trainer.data.errors import (
    DuplicateCollectionError,
    MasterFileLockedError,
)
from vocabulary_trainer.data.master_file_repository import MasterFileRepository
from vocabulary_trainer.domain.models import (
    Collection,
    DuplicateAction,
    LookupResult,
    PartOfSpeech,
    WordEntry,
)
from vocabulary_trainer.services.clock import Clock, SystemClock
from vocabulary_trainer.services.errors import ValidationError
from vocabulary_trainer.services.lookup_service import LookupService
from vocabulary_trainer.services.pending_enrichment import PendingEnrichmentRegistry

__all__ = [
    "BatchOutcome",
    "CollectService",
    "LookupHandle",
    "SaveOutcome",
    "SaveStatus",
]


class SaveStatus(StrEnum):
    """What happened when a save was attempted."""

    SAVED = auto()
    DUPLICATE_DETECTED = auto()
    LOCKED = auto()


@dataclass(frozen=True, slots=True)
class BatchOutcome:
    """What happened to each word in a multi-word capture (FR-2.12).

    Three lists rather than one status, because a batch genuinely has a mixed
    result: some words save, some are already in the collection, and a locked
    workbook can stop the rest. Collapsing that into a single status would force the
    UI to guess at the detail it needs to report.
    """

    saved: tuple[WordEntry, ...] = ()
    duplicates: tuple[str, ...] = ()
    locked: tuple[str, ...] = ()
    handles: tuple[tuple[str, "LookupHandle"], ...] = ()
    """The in-flight lookup for each saved word, paired with the word.

    Returned so the UI can announce each outcome as it lands (FR-3.11). Only saved
    words appear here: a skipped duplicate has its lookup cancelled, so there is
    nothing to report for it.
    """

    @property
    def attempted(self) -> int:
        return len(self.saved) + len(self.duplicates) + len(self.locked)

    @property
    def summary(self) -> str:
        """One line describing the outcome, written for display.

        Composed here rather than in the popup so the wording lives with the data
        it describes, and so the counts and the sentence cannot fall out of step.
        """
        parts: list[str] = []
        if self.saved:
            parts.append(f"Saved {len(self.saved)}")
        if self.duplicates:
            shown = ", ".join(self.duplicates[:3])
            if len(self.duplicates) > 3:
                shown += f" +{len(self.duplicates) - 3} more"
            parts.append(f"skipped {len(self.duplicates)} already there ({shown})")
        if self.locked:
            parts.append(f"{len(self.locked)} not saved \u2014 file is open in Excel")

        if not parts:
            return "Nothing to save."
        return ", ".join(parts) + "."


@dataclass(frozen=True, slots=True)
class SaveOutcome:
    """Result of a save attempt.

    ``existing`` is populated only for ``DUPLICATE_DETECTED``, carrying the row the
    conflict popup needs to display (FR-4.2).
    """

    status: SaveStatus
    existing: WordEntry | None = None
    saved: WordEntry | None = None


class LookupHandle:
    """An in-flight lookup the UI can poll or subscribe to without blocking.

    Deliberately not an awaitable: the Qt UI is not running an asyncio loop, so it
    needs something it can check on a timer or be called back from. The handle is
    also readable at any moment via :attr:`result`, which is what lets a save take
    "whatever has arrived so far" (FR-2.8).
    """

    def __init__(self, word: str, part_of_speech: PartOfSpeech) -> None:
        self.word = word
        self.part_of_speech = part_of_speech
        self._lock = threading.Lock()
        self._result: LookupResult | None = None
        self._listeners: list[Callable[[LookupResult], None]] = []
        self._cancelled = False

    @property
    def is_complete(self) -> bool:
        with self._lock:
            return self._result is not None

    @property
    def result(self) -> LookupResult | None:
        """The result so far, or ``None`` while still outstanding."""
        with self._lock:
            return self._result

    def subscribe(self, listener: Callable[[LookupResult], None]) -> None:
        """Be notified when the lookup completes.

        A listener registered after completion is called immediately, so there is no
        race between subscribing and the lookup finishing.
        """
        with self._lock:
            existing = self._result
            if existing is None:
                self._listeners.append(listener)
        if existing is not None:
            self._notify_one(listener, existing)

    def _complete(self, result: LookupResult) -> None:
        with self._lock:
            self._result = result
            if self._cancelled:
                self._listeners.clear()
                return
            listeners = list(self._listeners)
            self._listeners.clear()
        for listener in listeners:
            self._notify_one(listener, result)

    @staticmethod
    def _notify_one(
        listener: Callable[[LookupResult], None], result: LookupResult
    ) -> None:
        try:
            listener(result)
        except Exception:
            # A UI callback that raises must not break the lookup pipeline or
            # prevent other listeners from being told.
            pass

    def cancel(self) -> None:
        """Abandon the lookup, e.g. when the user closes the Collect card.

        The background request is allowed to finish and be discarded rather than
        being forcibly killed -- it holds no lock and writes nothing on its own, so
        letting it end naturally is simpler and safer than interrupting it.
        """
        with self._lock:
            self._cancelled = True
            self._listeners.clear()

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled


class CollectService:
    """Orchestrates the Collect flow."""

    def __init__(
        self,
        repository: MasterFileRepository,
        lookup: LookupService,
        clock: Clock | None = None,
        pending: PendingEnrichmentRegistry | None = None,
    ) -> None:
        self._repository = repository
        self._lookup = lookup
        self._clock = clock or SystemClock()
        # Optional so every existing construction site keeps working untouched. When
        # absent, nothing publishes pending state and previews fall back to the
        # blank-cell behaviour, which is exactly right for a caller that has no UI.
        self._pending = pending

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    def available_collections(self) -> list[str]:
        """Names for the Collection dropdown, current as of the last data load."""
        return [collection.name for collection in self._repository.all_collections()]

    def create_collection_inline(self, name: str) -> Collection:
        """Create a collection from within the Collect card (FR-2.5).

        Raises :class:`ValidationError` with a message written for display beside the
        inline field, so the popup never has to compose its own wording.
        """
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("Enter a name for the new collection.")

        collection = Collection(name=cleaned, created_on=self._clock.today())
        try:
            self._repository.insert_collection(collection)
        except DuplicateCollectionError as exc:
            raise ValidationError(str(exc)) from exc
        return collection

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def begin_lookup(self, word: str, part_of_speech: PartOfSpeech) -> LookupHandle:
        """Start all available sources concurrently, returning immediately.

        The lookup runs on a background thread with its own event loop, because the
        Qt UI is not running asyncio. The widget stays fully responsive throughout
        (FR-1.9, NFR-PERF-01).
        """
        handle = LookupHandle(word, part_of_speech)

        def run() -> None:
            import asyncio

            try:
                result = asyncio.run(self._lookup.lookup(word, part_of_speech))
            except Exception:
                # Lookup failure is an ordinary outcome, not an error the user must
                # resolve: the word still saves with a blank meaning (FR-3.5).
                result = LookupResult.empty()
            handle._complete(result)

        thread = threading.Thread(target=run, name="collect-lookup", daemon=True)
        thread.start()
        return handle

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------

    def check_duplicate(self, word: str, collection_name: str) -> WordEntry | None:
        """The existing entry with this identity, if any (FR-4.1)."""
        return self._repository.find_by_natural_key(word, collection_name)

    def save_word(
        self,
        word: str,
        part_of_speech: PartOfSpeech,
        collection_name: str,
        lookup: LookupHandle | None = None,
        *,
        manual_meaning: str | None = None,
        manual_example: str | None = None,
    ) -> SaveOutcome:
        """Save a word, enriching it later if the lookup is still running.

        The ordering matters and is the point of this method:

        1. Reject blank input.
        2. Check for a duplicate. If found, write **nothing** and report it, so the
           conflict popup decides (FR-4.1).
        3. Otherwise insert the row *now*, using whatever the lookup has produced so
           far -- possibly a blank meaning (FR-2.8).
        4. If the lookup is still outstanding, arrange to patch that same row when it
           finishes, rather than inserting a second one (FR-2.9).

        ``manual_meaning`` (optionally with ``manual_example``) switches to
        **manual-meaning mode** (FR-2.11): the user typed their own definition
        instead of waiting on the lookup pipeline. Passing it -- even as an
        empty string, to mean "type only, no meaning" -- means ``lookup`` is
        ignored entirely and no enrichment patch is ever scheduled. Without
        that exclusion, a slow dictionary response could arrive after save and
        silently overwrite what the user just typed, which auto-meaning mode
        has no equivalent risk for today.

        A locked file returns ``LOCKED`` rather than raising, so the caller can keep
        the user's typed word and offer Retry (FR-8.6).
        """
        cleaned_word = word.strip()
        if not cleaned_word:
            raise ValidationError("Enter a word or phrase to collect.")

        cleaned_collection = collection_name.strip()
        if not cleaned_collection:
            raise ValidationError("Choose a collection for this word.")

        existing = self.check_duplicate(cleaned_word, cleaned_collection)
        if existing is not None:
            return SaveOutcome(
                status=SaveStatus.DUPLICATE_DETECTED, existing=existing
            )

        if manual_meaning is not None:
            entry = WordEntry(
                word=cleaned_word,
                part_of_speech=part_of_speech,
                meaning=manual_meaning.strip() or None,
                example=(manual_example or "").strip() or None,
                collection_name=cleaned_collection,
                collected_on=self._clock.today(),
            )
            try:
                self._repository.insert_word(entry)
            except MasterFileLockedError:
                return SaveOutcome(status=SaveStatus.LOCKED)
            # Manual mode never consults the lookup pipeline, so there is
            # nothing to enrich later even if a ``lookup`` handle happens to
            # be in flight from before the user switched modes.
            return SaveOutcome(status=SaveStatus.SAVED, saved=entry)

        result = lookup.result if lookup is not None else None
        entry = WordEntry(
            word=cleaned_word,
            part_of_speech=part_of_speech,
            meaning=result.meaning if result is not None else None,
            example=result.example if result is not None else None,
            collection_name=cleaned_collection,
            collected_on=self._clock.today(),
        )

        try:
            self._repository.insert_word(entry)
        except MasterFileLockedError:
            return SaveOutcome(status=SaveStatus.LOCKED)

        if lookup is not None and not lookup.is_complete:
            self._schedule_enrichment(entry, lookup)

        return SaveOutcome(status=SaveStatus.SAVED, saved=entry)

    def _schedule_enrichment(self, entry: WordEntry, lookup: LookupHandle) -> None:
        """Patch the saved row once its lookup completes.

        Also publishes the row as *pending* for as long as that takes, so a preview
        table can say "looking up..." instead of showing the same blank cell it would
        show for a lookup that failed months ago (FR-7.14).
        """
        key = entry.natural_key
        if self._pending is not None:
            self._pending.mark_pending(key)

        def on_complete(result: LookupResult) -> None:
            # try/finally so the pending flag is cleared even if the patch raises
            # something unexpected. A row stuck showing "looking up..." forever would
            # be worse than one showing a blank meaning.
            try:
                if result.is_empty:
                    # Nothing usable arrived, so the row keeps its blank meaning
                    # (FR-3.5). Writing blanks over blanks would be a pointless
                    # workbook mutation.
                    return
                try:
                    self._repository.patch_word_enrichment(
                        key, result.meaning, result.example
                    )
                except MasterFileLockedError:
                    # The user has the workbook open. The row exists with its word,
                    # type, collection and date -- only enrichment is lost, and that
                    # is not worth interrupting them for.
                    pass
            finally:
                if self._pending is not None:
                    self._pending.clear_pending(key)

        lookup.subscribe(on_complete)

    def save_words(
        self,
        words: Sequence[str],
        part_of_speech: PartOfSpeech,
        collection_name: str,
    ) -> BatchOutcome:
        """Save several words at once, each with its own lookup (FR-2.12).

        Every word gets an independent lookup, all started before any of them are
        awaited, so ten words cost roughly one lookup's wait rather than ten in
        sequence. Each row is written immediately with a blank meaning and patched
        when its own lookup lands -- the same save-then-patch discipline as the
        single-word path, reused rather than reimplemented.

        Duplicates are **skipped**, not offered for resolution. The single-word flow
        shows a popup asking Keep/Replace/Delete, which is right when the user is
        looking at one word; asking that question five times in a row for a batch
        would be a worse experience than reporting "3 saved, 2 already there" and
        letting the user handle those individually if they care.

        A locked workbook stops the batch at the word that hit the lock: continuing
        would write some rows and not others with no clear boundary, and the caller
        can offer a single Retry for the remainder.
        """
        saved: list[WordEntry] = []
        duplicates: list[str] = []
        locked: list[str] = []
        live: list[tuple[str, LookupHandle]] = []

        # Start every lookup first. Doing this inside the save loop instead would
        # serialise them behind each row's workbook write.
        handles = [
            (word, self.begin_lookup(word, part_of_speech))
            for word in words
            if word.strip()
        ]

        for word, handle in handles:
            if locked:
                # A previous word hit the lock, so the workbook is unavailable. Cancel
                # this word's lookup rather than leaving a thread patching a row that
                # was never written.
                handle.cancel()
                locked.append(word)
                continue

            try:
                outcome = self.save_word(
                    word, part_of_speech, collection_name, handle
                )
            except ValidationError:
                # Blank or otherwise unusable: skip it rather than failing the batch.
                handle.cancel()
                continue

            if outcome.status is SaveStatus.SAVED and outcome.saved is not None:
                saved.append(outcome.saved)
                live.append((word, handle))
            elif outcome.status is SaveStatus.DUPLICATE_DETECTED:
                handle.cancel()
                duplicates.append(word)
            else:
                handle.cancel()
                locked.append(word)

        return BatchOutcome(
            saved=tuple(saved),
            duplicates=tuple(duplicates),
            locked=tuple(locked),
            handles=tuple(live),
        )

    def retry_save(self, entry: WordEntry) -> bool:
        """Reattempt a save that previously failed on a locked file (FR-8.6)."""
        try:
            self._repository.insert_word(entry)
            return True
        except MasterFileLockedError:
            return False

    # ------------------------------------------------------------------
    # Duplicate resolution
    # ------------------------------------------------------------------

    def resolve_duplicate(
        self,
        action: DuplicateAction,
        existing: WordEntry,
        incoming: WordEntry,
    ) -> bool:
        """Apply the user's choice for a duplicate word.

        Exactly one of three things happens -- nothing, the existing row is updated,
        or the existing row is removed -- and the incoming word is **never** inserted
        as a separate row by any branch (FR-4.8).

        Dismissal without a choice is mapped to ``KEEP_OLD`` by the popup before it
        reaches here, so this method never has to model "no decision" (FR-4.7).

        Returns ``False`` when the workbook was locked, so the caller can offer Retry.
        """
        try:
            if action is DuplicateAction.KEEP_OLD:
                # Nothing is written at all. The existing row keeps its meaning,
                # example and date exactly as they were (FR-4.3).
                return True

            if action is DuplicateAction.REPLACE:
                # Word and collection are preserved by the repository; only meaning,
                # example, type and date change (FR-4.4).
                refreshed = WordEntry(
                    word=existing.word,
                    part_of_speech=incoming.part_of_speech,
                    meaning=incoming.meaning,
                    example=incoming.example,
                    collection_name=existing.collection_name,
                    collected_on=self._clock.today(),
                )
                self._repository.replace_word(refreshed)
                return True

            # DELETE_BOTH: the existing row goes and the incoming word is discarded,
            # so neither entry survives (FR-4.5).
            self._repository.delete_word(existing.natural_key)
            return True

        except MasterFileLockedError:
            return False

    def build_entry(
        self,
        word: str,
        part_of_speech: PartOfSpeech,
        collection_name: str,
        lookup: LookupHandle | None = None,
        when: date | None = None,
        *,
        manual_meaning: str | None = None,
        manual_example: str | None = None,
    ) -> WordEntry:
        """Assemble an entry without saving it.

        Used by the conflict popup, which needs an ``incoming`` value to hand to
        :meth:`resolve_duplicate` for a word that was never written. Mirrors
        :meth:`save_word`'s manual-meaning handling (FR-2.11): when
        ``manual_meaning`` is given, ``lookup`` is ignored.
        """
        if manual_meaning is not None:
            return WordEntry(
                word=word.strip(),
                part_of_speech=part_of_speech,
                meaning=manual_meaning.strip() or None,
                example=(manual_example or "").strip() or None,
                collection_name=collection_name.strip(),
                collected_on=when or self._clock.today(),
            )

        result = lookup.result if lookup is not None else None
        return WordEntry(
            word=word.strip(),
            part_of_speech=part_of_speech,
            meaning=result.meaning if result is not None else None,
            example=result.example if result is not None else None,
            collection_name=collection_name.strip(),
            collected_on=when or self._clock.today(),
        )
