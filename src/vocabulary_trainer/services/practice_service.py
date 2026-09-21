"""The practice session: collection selection, the drill loop, and the summary.

This is the only service holding mutable in-flight state, and deliberately so -- a
session is transient and is not persisted until it ends. The rules it enforces live
in ``domain.scoring`` and ``domain.shuffle`` rather than here, because the invariant
that a wrong answer never erases mastery progress is the one most easily broken by a
later edit.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import datetime

from vocabulary_trainer.data.history_store import HistoryStore
from vocabulary_trainer.data.master_file_repository import MasterFileRepository
from vocabulary_trainer.data.practice_log_repository import PracticeLogRepository
from vocabulary_trainer.domain.models import (
    AttemptOutcome,
    CollectionSortMode,
    CollectionSummary,
    PracticeLogEntry,
    PracticeWordState,
    SessionSummary,
    WordEntry,
)
from vocabulary_trainer.domain.natural_key import normalize_collection, normalize_word
from vocabulary_trainer.domain.scoring import (
    answer_matches,
    compute_score,
    total_required_attempts,
)
from vocabulary_trainer.domain.shuffle import reinsert_avoiding_next, shuffled
from vocabulary_trainer.integrations.audio import AudioFeedbackService
from vocabulary_trainer.integrations.tts import TextToSpeechService
from vocabulary_trainer.services.clock import Clock, SystemClock
from vocabulary_trainer.services.errors import EmptyPoolError
from vocabulary_trainer.services.pending_enrichment import PendingEnrichmentRegistry

__all__ = ["PracticeService", "PracticeSession"]

MIN_REQUIRED_WRITES = 1
MAX_REQUIRED_WRITES = 10
"""Bounds of the setup stepper (FR-5.6)."""


class PracticeSession:
    """One run through a word pool.

    The pool is a list consumed from the front, matching the convention
    ``domain.shuffle`` relies on: index 0 is the next word drawn.
    """

    def __init__(
        self,
        pool: list[PracticeWordState],
        required_correct: int,
        collection_names: Sequence[str],
        started_at: datetime,
        rng: random.Random | None = None,
    ) -> None:
        self.required_correct = required_correct
        self.collection_names = tuple(collection_names)
        self.started_at = started_at
        self._pool = pool
        self._rng = rng
        self._initial_pool_size = len(pool)
        self._total_required_attempts = total_required_attempts(
            len(pool), required_correct
        )
        self._mastered: list[PracticeWordState] = []
        self._correct_attempts = 0
        self._penalties = 0
        self._attempts_made = 0
        self._awaiting_acknowledgement = False
        self._wrong_counts: dict[str, tuple[str, int]] = {}
        """Miss tally for the practice log (user-requested feature), keyed by the
        word's normalized form so "Hello" and "hello" tally together. Value is
        ``(display_word, times_missed)`` -- the display form is kept alongside the
        key so the log shows the word as the user typed it, not its normalized
        form."""

    # ------------------------------------------------------------------

    @property
    def current(self) -> PracticeWordState | None:
        """The word being asked, or ``None`` when the pool is exhausted."""
        return self._pool[0] if self._pool else None

    @property
    def is_finished(self) -> bool:
        return not self._pool

    @property
    def score(self) -> int:
        return compute_score(self._correct_attempts, self._penalties)

    @property
    def penalties(self) -> int:
        return self._penalties

    @property
    def attempts_made(self) -> int:
        return self._attempts_made

    @property
    def total_required_attempts(self) -> int:
        """Progress denominator, fixed when the session started.

        The pool shrinks as words are mastered; a live denominator would make the
        progress bar jump backwards (FR-6.3).
        """
        return self._total_required_attempts

    @property
    def words_mastered(self) -> int:
        return len(self._mastered)

    @property
    def pool_size(self) -> int:
        return len(self._pool)

    @property
    def initial_pool_size(self) -> int:
        return self._initial_pool_size

    @property
    def awaiting_acknowledgement(self) -> bool:
        """True after a miss, until the user acknowledges the reveal (FR-6.9)."""
        return self._awaiting_acknowledgement

    @property
    def wrong_counts(self) -> tuple[tuple[str, int], ...]:
        """``(word, times missed)`` for every word missed at least once this
        session, sorted by word for a deterministic log row."""
        return tuple(sorted(self._wrong_counts.values()))


class PracticeService:
    """Builds and runs practice sessions."""

    def __init__(
        self,
        repository: MasterFileRepository,
        history: HistoryStore,
        practice_log: PracticeLogRepository | None = None,
        tts: TextToSpeechService | None = None,
        audio: AudioFeedbackService | None = None,
        clock: Clock | None = None,
        rng: random.Random | None = None,
        pending: PendingEnrichmentRegistry | None = None,
    ) -> None:
        self._repository = repository
        self._history = history
        self._practice_log = practice_log
        self._tts = tts
        self._audio = audio
        self._clock = clock or SystemClock()
        self._rng = rng
        self._pending = pending
        self._session: PracticeSession | None = None
        self._last_config: tuple[tuple[str, ...], int] | None = None

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def list_collections(
        self,
        search: str = "",
        sort: CollectionSortMode = CollectionSortMode.NEWEST_FIRST,
    ) -> list[CollectionSummary]:
        """Collections for the setup list, filtered then sorted (FR-5.3, FR-5.4).

        Filtering and sorting are independent of each other and of which collections
        the user has checked. Selection lives in the UI and is passed back as names,
        which is why a checked collection filtered out of view stays checked with no
        special handling here (E5-S2 branch 3a).
        """
        summaries = self._repository.collection_summaries()

        needle = search.strip().casefold()
        if needle:
            summaries = [s for s in summaries if needle in s.name.casefold()]

        if sort is CollectionSortMode.NAME_ASC:
            return sorted(summaries, key=lambda s: s.name.casefold())
        if sort is CollectionSortMode.OLDEST_FIRST:
            # Name is the secondary key so collections sharing a creation date keep a
            # stable order instead of shuffling between renders (E5-S2 branch 4a).
            return sorted(summaries, key=lambda s: (s.created_on, s.name.casefold()))
        return sorted(
            summaries, key=lambda s: (s.created_on, s.name.casefold()), reverse=True
        )

    def words_for_collection(self, name: str) -> list[WordEntry]:
        """Every word in one collection, for the setup screen's preview (FR-5.10).

        Reads through the same repository method the Settings preview uses, so both
        agree on what belongs to a collection.
        """
        return self._repository.words_for(name)

    def is_lookup_pending(self, word: str, collection_name: str) -> bool:
        """Whether this row's meaning is still being looked up (FR-5.10).

        Same reporting as the Settings preview, so the two tables cannot disagree
        about whether a blank cell is waiting or finished.
        """
        if self._pending is None:
            return False
        return self._pending.is_pending(word, collection_name)

    def combined_word_count(self, collection_names: Sequence[str]) -> int:
        """Total pool size across the checked collections (FR-5.7)."""
        wanted = {normalize_collection(name) for name in collection_names}
        if not wanted:
            return 0
        return sum(
            1
            for entry in self._repository.all_words()
            if normalize_collection(entry.collection_name) in wanted
        )

    def can_start(self, collection_names: Sequence[str]) -> bool:
        """Whether Start should be enabled (FR-5.8)."""
        return self.combined_word_count(collection_names) > 0

    def clamp_required_writes(self, value: int) -> int:
        """Hold the stepper inside its permitted range (FR-5.6)."""
        return max(MIN_REQUIRED_WRITES, min(MAX_REQUIRED_WRITES, value))

    def start_session(
        self, collection_names: Sequence[str], required_correct: int
    ) -> PracticeSession:
        """Build a shuffled pool and begin a session (FR-5.9).

        Raises :class:`EmptyPoolError` on an empty pool. The setup screen already
        disables Start in that case, so this is a backstop that keeps the drill from
        ever opening on nothing.
        """
        wanted = {normalize_collection(name) for name in collection_names}
        words: list[WordEntry] = [
            entry
            for entry in self._repository.all_words()
            if normalize_collection(entry.collection_name) in wanted
        ]

        if not words:
            raise EmptyPoolError()

        required = self.clamp_required_writes(required_correct)
        pool = [PracticeWordState(entry=entry) for entry in shuffled(words, self._rng)]

        self._session = PracticeSession(
            pool=pool,
            required_correct=required,
            collection_names=collection_names,
            started_at=self._clock.now(),
            rng=self._rng,
        )
        self._last_config = (tuple(collection_names), required)
        return self._session

    # ------------------------------------------------------------------
    # Drill
    # ------------------------------------------------------------------

    @property
    def session(self) -> PracticeSession | None:
        return self._session

    def current_word(self) -> PracticeWordState | None:
        return self._session.current if self._session is not None else None

    def submit_attempt(self, answer: str) -> AttemptOutcome:
        """Judge an answer and advance the session state.

        A correct answer plays the success sound, speaks the word, and either masters
        it or returns it to the pool away from the next draw. A wrong answer adds one
        penalty, reveals the spelling, and leaves mastery progress **untouched** --
        the word stays in the pool for another try (FR-6.5 through FR-6.8).
        """
        session = self._require_session()
        state = session.current
        if state is None:
            raise EmptyPoolError()

        session._attempts_made += 1
        correct = answer_matches(answer, state.entry.word)

        if correct:
            session._correct_attempts += 1
            state.correct_count += 1

            if self._audio is not None:
                self._audio.play_correct()
            if self._tts is not None:
                self._tts.speak(state.entry.word)

            became_mastered = state.is_mastered_at(session.required_correct)
            session._pool.pop(0)
            if became_mastered:
                session._mastered.append(state)
            else:
                reinsert_avoiding_next(session._pool, state, session._rng)
            session._awaiting_acknowledgement = False
        else:
            session._penalties += 1
            state.wrong_count += 1
            # Under the NOR rule this is no longer "untouched": a miss pushes the
            # word's own finish line back by one repetition, on top of the score
            # penalty above. See PracticeWordState.remaining_for / domain.scoring
            # for the arithmetic.
            if self._audio is not None:
                self._audio.play_incorrect()
            # The drill waits for the user to read the revealed spelling before
            # advancing (FR-6.9); mastery itself is re-evaluated on the *next*
            # correct answer, not here, since a miss can only ever add to the
            # target, never immediately reopen a word that was already mastered
            # (a mastered word is no longer being asked, so it can't miss).
            session._awaiting_acknowledgement = True
            became_mastered = False

            key = normalize_word(state.entry.word)
            _, count = session._wrong_counts.get(key, (state.entry.word, 0))
            session._wrong_counts[key] = (state.entry.word, count + 1)

        return AttemptOutcome(
            was_correct=correct,
            correct_spelling=state.entry.word,
            correct_count=state.correct_count,
            wrong_count=state.wrong_count,
            remaining_repetitions=state.remaining_for(session.required_correct),
            required_correct=session.required_correct,
            became_mastered=became_mastered,
            score=session.score,
            total_penalties=session.penalties,
            attempts_made=session.attempts_made,
            total_required_attempts=session.total_required_attempts,
        )

    def acknowledge_and_advance(self) -> PracticeWordState | None:
        """Move past a revealed miss to the next word (FR-6.9).

        The missed word is rotated to a later position rather than being shown again
        immediately, for the same reason a correct-but-unmastered word is: retyping
        what is still on screen teaches nothing.
        """
        session = self._require_session()
        session._awaiting_acknowledgement = False

        if len(session._pool) > 1:
            state = session._pool.pop(0)
            reinsert_avoiding_next(session._pool, state, session._rng)

        return session.current

    # ------------------------------------------------------------------
    # Ending
    # ------------------------------------------------------------------

    def end_session(self) -> SessionSummary:
        """Finish the session and record it (FR-6.14, FR-6.16, FR-6.18).

        Reached three ways -- every word mastered, the End session button, or the
        window being closed -- all of which produce the same summary (FR-6.12,
        FR-6.13). "Finished" in the separate practice log (FR-6.18) means the first
        of those: the pool was empty, i.e. every word reached mastery, before this
        was called. Ending early or closing mid-session both log as not finished,
        because the pool still held unmastered words when the session stopped.

        A failure to write either log is swallowed: the user finished the work
        either way, and losing a statistic is not worth blocking the summary
        (E6-S6 branch 4a).
        """
        session = self._require_session()
        finished_at = self._clock.now()
        completed_naturally = session.is_finished

        summary = SessionSummary(
            score=session.score,
            words_practiced=session.words_mastered,
            total_penalties=session.penalties,
            elapsed=finished_at - session.started_at,
            finished_at=finished_at,
        )
        self._history.append(summary)

        if self._practice_log is not None:
            entry = PracticeLogEntry(
                session_date=session.started_at.date(),
                start_time=session.started_at.time(),
                end_time=finished_at.time(),
                collections=session.collection_names,
                penalty=session.penalties,
                finished=completed_naturally,
                wrong_counts=session.wrong_counts,
            )
            self._practice_log.append_entry(entry)

        self._session = None
        return summary

    def last_session_config(self) -> tuple[tuple[str, ...], int] | None:
        """Collections and threshold for "Practice again" (FR-6.15)."""
        return self._last_config

    def practice_again(self) -> PracticeSession:
        """Restart with the same collections and threshold, freshly shuffled.

        Raises :class:`EmptyPoolError` when those collections no longer hold words --
        the user may have deleted one in Settings since (E6-S6 branch 6a).
        """
        if self._last_config is None:
            raise EmptyPoolError()
        names, required = self._last_config
        return self.start_session(names, required)

    def abandon_session(self) -> None:
        """Discard the in-flight session without producing a summary.

        Used when the window closes *after* the summary has already been shown, so
        the session is not recorded twice.
        """
        self._session = None

    def _require_session(self) -> PracticeSession:
        if self._session is None:
            raise EmptyPoolError()
        return self._session
