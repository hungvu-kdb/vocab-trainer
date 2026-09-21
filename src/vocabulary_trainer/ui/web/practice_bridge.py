"""The Practice window's bridge to Python (FR-5.x, FR-6.x).

Every slot here delegates to :class:`PracticeService`. Nothing in this file decides
whether an answer is right, when a word is mastered, or how progress is calculated --
those live in the domain layer, which is why the same rules hold no matter which UI
surface is driving them.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Slot

from vocabulary_trainer.domain.models import CollectionSortMode
from vocabulary_trainer.services.practice_service import PracticeService
from vocabulary_trainer.ui.web.bridge import BridgeBase, fail, ok

__all__ = ["PracticeBridge"]


class PracticeBridge(BridgeBase):
    """Exposes practice operations to the Practice window's JavaScript."""

    def __init__(self, practice: PracticeService) -> None:
        super().__init__()
        self._practice = practice

    # ------------------------------------------------------------------
    # Setup screen
    # ------------------------------------------------------------------

    @Slot(str, str, result="QVariant")
    def list_collections(self, search: str, sort: str) -> dict[str, Any]:
        """Collections for the checkbox list, filtered then sorted (FR-5.2 – FR-5.4)."""

        def run() -> dict[str, Any]:
            mode = self._parse_sort(sort)
            summaries = self._practice.list_collections(search=search, sort=mode)
            return ok(
                collections=[
                    {
                        "name": s.name,
                        "wordCount": s.word_count,
                        "createdOn": s.created_on.strftime("%b %d, %Y"),
                    }
                    for s in summaries
                ]
            )

        return self._guard(run)

    @Slot(str, result="QVariant")
    def collection_words(self, name: str) -> dict[str, Any]:
        """Every word in one collection, for the setup screen's preview (FR-5.10).

        Same read the Settings Collections tab offers (FR-7.14), surfaced here so
        the user can check what is actually in a collection *before* committing it
        to a pool, rather than having to open Settings to find out.
        """

        def run() -> dict[str, Any]:
            entries = self._practice.words_for_collection(str(name))
            words = [
                {
                    "word": entry.word,
                    "partOfSpeech": entry.part_of_speech.value,
                    "meaning": entry.meaning or "",
                    "example": entry.example or "",
                    "collectedOn": entry.collected_on.strftime("%b %d, %Y"),
                    # Same distinction as the Settings preview (FR-7.14): a blank
                    # cell still being filled in is not the same as one whose lookup
                    # found nothing.
                    "lookupPending": self._practice.is_lookup_pending(
                        entry.word, entry.collection_name
                    ),
                }
                for entry in entries
            ]
            return ok(
                name=str(name),
                words=words,
                anyPending=any(word["lookupPending"] for word in words),
            )

        return self._guard(run)

    @Slot("QVariantList", result="QVariant")
    def pool_summary(self, names: list[str]) -> dict[str, Any]:
        """Combined pool size and whether Start may be enabled (FR-5.7, FR-5.8)."""

        def run() -> dict[str, Any]:
            selected = [str(name) for name in names]
            count = self._practice.combined_word_count(selected)
            return ok(
                wordCount=count,
                collectionCount=len(selected),
                canStart=count > 0,
            )

        return self._guard(run)

    @Slot(int, result="QVariant")
    def clamp_required_writes(self, value: int) -> dict[str, Any]:
        """Hold the stepper inside 1-10 (FR-5.6)."""
        return self._guard(
            lambda: ok(value=self._practice.clamp_required_writes(int(value)))
        )

    @Slot("QVariantList", int, result="QVariant")
    def start_session(self, names: list[str], required: int) -> dict[str, Any]:
        """Build the pool and begin (FR-5.9)."""

        def run() -> dict[str, Any]:
            self._practice.start_session([str(name) for name in names], int(required))
            # ``_prompt_payload`` already carries the pool size (as ``poolSize``,
            # from ``session.pool_size``); passing it again as a second keyword
            # raised "got multiple values for keyword argument 'poolSize'" on every
            # successful start, which the bridge's generic exception handler turned
            # into an opaque "Something went wrong" for the user.
            return ok(**self._prompt_payload())

        return self._guard(run)

    # ------------------------------------------------------------------
    # Drill screen
    # ------------------------------------------------------------------

    @Slot(result="QVariant")
    def current_prompt(self) -> dict[str, Any]:
        """Type and meaning for the current word -- never its spelling (FR-6.2)."""
        return self._guard(lambda: ok(**self._prompt_payload()))

    @Slot(str, result="QVariant")
    def submit_attempt(self, answer: str) -> dict[str, Any]:
        """Judge an answer and report the resulting state (FR-6.4 – FR-6.11)."""

        def run() -> dict[str, Any]:
            text = str(answer)
            if not text.strip():
                # An empty submission is ignored rather than penalised, so a stray
                # Enter costs nothing (E6-S1 branch 7a).
                return ok(ignored=True)

            outcome = self._practice.submit_attempt(text)
            session = self._practice.session
            return ok(
                ignored=False,
                wasCorrect=outcome.was_correct,
                correctSpelling=outcome.correct_spelling,
                correctCount=outcome.correct_count,
                wrongCount=outcome.wrong_count,
                remainingRepetitions=outcome.remaining_repetitions,
                requiredCorrect=outcome.required_correct,
                becameMastered=outcome.became_mastered,
                score=outcome.score,
                totalPenalties=outcome.total_penalties,
                attemptsMade=outcome.attempts_made,
                totalRequiredAttempts=outcome.total_required_attempts,
                isFinished=session.is_finished if session is not None else True,
                awaitingAcknowledgement=(
                    session.awaiting_acknowledgement if session is not None else False
                ),
            )

        return self._guard(run)

    @Slot(result="QVariant")
    def acknowledge_and_advance(self) -> dict[str, Any]:
        """Move past a revealed miss once the user is ready (FR-6.9)."""

        def run() -> dict[str, Any]:
            self._practice.acknowledge_and_advance()
            return ok(**self._prompt_payload())

        return self._guard(run)

    # ------------------------------------------------------------------
    # Summary screen
    # ------------------------------------------------------------------

    @Slot(result="QVariant")
    def end_session(self) -> dict[str, Any]:
        """Finish and report the summary (FR-6.12 – FR-6.14, FR-6.16)."""

        def run() -> dict[str, Any]:
            summary = self._practice.end_session()
            return ok(
                score=summary.score,
                wordsPracticed=summary.words_practiced,
                totalPenalties=summary.total_penalties,
                elapsed=self._format_elapsed(summary.elapsed.total_seconds()),
            )

        return self._guard(run)

    @Slot(result="QVariant")
    def practice_again(self) -> dict[str, Any]:
        """Restart with the same collections and threshold (FR-6.15)."""

        def run() -> dict[str, Any]:
            self._practice.practice_again()
            return ok(**self._prompt_payload())

        return self._guard(run)

    @Slot(result="QVariant")
    def last_config(self) -> dict[str, Any]:
        """Previous selections, so Back to setup restores them (E6-S6 branch 5a)."""

        def run() -> dict[str, Any]:
            config = self._practice.last_session_config()
            if config is None:
                return ok(collections=[], requiredCorrect=3)
            names, required = config
            return ok(collections=list(names), requiredCorrect=required)

        return self._guard(run)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prompt_payload(self) -> dict[str, Any]:
        """State for rendering the drill, deliberately excluding the word itself."""
        session = self._practice.session
        state = self._practice.current_word()

        if session is None or state is None:
            return {
                "hasWord": False,
                "isFinished": True,
                "score": session.score if session is not None else 0,
                "totalPenalties": session.penalties if session is not None else 0,
                "attemptsMade": session.attempts_made if session is not None else 0,
                "totalRequiredAttempts": (
                    session.total_required_attempts if session is not None else 0
                ),
            }

        meaning = state.entry.meaning
        return {
            "hasWord": True,
            "isFinished": False,
            "partOfSpeech": state.entry.part_of_speech.value,
            # A word collected while every lookup failed has no meaning. Saying so is
            # better than an empty prompt the user cannot act on (E6-S1 branch 4a).
            "meaning": meaning if meaning else "(no meaning recorded for this word)",
            "hasMeaning": bool(meaning),
            "correctCount": state.correct_count,
            "wrongCount": state.wrong_count,
            "remainingRepetitions": state.remaining_for(session.required_correct),
            "requiredCorrect": session.required_correct,
            "score": session.score,
            "totalPenalties": session.penalties,
            "attemptsMade": session.attempts_made,
            "totalRequiredAttempts": session.total_required_attempts,
            "poolSize": session.pool_size,
            "wordsMastered": session.words_mastered,
        }

    @staticmethod
    def _parse_sort(value: str) -> CollectionSortMode:
        """Map the dropdown value onto a sort mode, defaulting to Newest first."""
        for mode in CollectionSortMode:
            if mode.value == value:
                return mode
        return CollectionSortMode.NEWEST_FIRST

    @staticmethod
    def _format_elapsed(total_seconds: float) -> str:
        """Render elapsed time as the mockup does, e.g. ``18m 42s``."""
        seconds = max(0, int(total_seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m {secs}s"
        if minutes:
            return f"{minutes}m {secs}s"
        return f"{secs}s"
