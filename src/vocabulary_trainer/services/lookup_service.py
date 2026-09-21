"""Running the lookup sources and picking a winner.

All available sources are queried **concurrently** on every lookup, then the
highest-priority non-empty answer is kept. That is a deliberate revision of the
original spec, which described a sequential chain stopping at the first hit: asking
in parallel means a slow first source no longer delays a result that a second source
already has.

This service is a thin concurrency coordinator by design. The branch-heavy
selection logic lives in ``domain.lookup_priority`` where it can be exhaustively
tested with no transport at all.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from vocabulary_trainer.domain.lookup_priority import select_definition, select_result
from vocabulary_trainer.domain.models import (
    LookupResult,
    LookupSource,
    PartOfSpeech,
)
from vocabulary_trainer.integrations.lookup_client import LookupClient

__all__ = ["LookupService"]

_DEFAULT_TIMEOUT = 8.0
"""Ceiling for the whole lookup when every source is a dictionary.

Generous enough for a slow connection, short enough that a user who saves
immediately is not waiting on a hung request to patch their row.
"""

_GENERATIVE_TIMEOUT = 60.0
"""Ceiling instead used whenever a generative source is available (FR-3.10).

A local model writes its answer token by token, and a cold one on CPU takes far
longer than any dictionary request: measured 5-15s on a small model, and a larger
model or a first load after boot is slower still. Under the 8s dictionary ceiling
the LLM was being cancelled before it could ever answer, so switching it on
appeared to do nothing -- the dictionaries always won by default.

This is a *ceiling*, not a delay. ``asyncio.wait`` returns as soon as every source
has finished, so a lookup that resolves in 3s still takes 3s. The full 60s is only
spent when the model is genuinely still working, which is exactly the case worth
waiting for. Waiting costs the user nothing either way: the word is written to the
workbook immediately and the row is patched when the result lands (FR-2.8, FR-2.9),
so nothing is blocked on this.
"""


class LookupService:
    """Queries every available source concurrently and selects one result."""

    def __init__(
        self,
        clients: Sequence[LookupClient],
        timeout: float | None = None,
        generative_timeout: float = _GENERATIVE_TIMEOUT,
    ) -> None:
        self._clients = list(clients)
        # None rather than a literal default so "caller said nothing" stays
        # distinguishable from "caller asked for 8s". Only the former adapts to a
        # generative source; an explicit timeout is always honoured, which is what
        # keeps the existing timeout tests meaningful.
        self._timeout = timeout
        self._generative_timeout = generative_timeout

    @staticmethod
    def _is_generative(client: LookupClient) -> bool:
        """Whether this client writes an answer rather than looking one up.

        Duck-typed on ``generate`` for the same reason ``_request`` is: a generative
        source is the exception, and testing for the method here avoids making the
        four dictionary clients declare something about themselves that only matters
        to one of them.
        """
        return callable(getattr(client, "generate", None))

    def _deadline_for(self, clients: Sequence[LookupClient]) -> float:
        """The overall ceiling, widened when a generative source is in play.

        Chosen from the sources that are *actually available* on this lookup, not
        from everything configured -- so a user who has never enabled the local model
        keeps the tighter dictionary deadline, and one who switches it off gets it
        back immediately.
        """
        if self._timeout is not None:
            return self._timeout
        if any(self._is_generative(client) for client in clients):
            return self._generative_timeout
        return _DEFAULT_TIMEOUT

    async def lookup(self, word: str, part_of_speech: PartOfSpeech) -> LookupResult:
        """Find a meaning and example for ``word`` (FR-3.1 through FR-3.5).

        Returns an empty ``LookupSource.NONE`` result when nothing usable came back,
        so the caller can always save the word regardless (FR-3.5).
        """
        if not word.strip():
            return LookupResult.empty()

        available = [client for client in self._clients if client.is_available()]
        if not available:
            return LookupResult.empty()

        gathered = await self._gather(available, word, part_of_speech)

        results: dict[LookupSource, LookupResult] = {}
        for client, candidates in gathered:
            if not candidates:
                continue
            chosen = select_definition(candidates, part_of_speech)
            if chosen is None:
                continue
            results[client.source] = LookupResult(
                meaning=chosen.meaning,
                example=chosen.example,
                source=client.source,
            )

        return select_result(results)

    @staticmethod
    def _request(
        client: LookupClient, word: str, part_of_speech: PartOfSpeech
    ) -> "asyncio.Future[list]":
        """Start one client's query, using whichever call shape it supports.

        A generative source (the local LLM) is asked for the sense matching the
        chosen part of speech, since it produces one answer rather than a list to
        select from. Dictionaries keep the plain ``fetch`` signature -- checking
        here means adding a generative source did not require touching any of them.
        """
        generate = getattr(client, "generate", None)
        if callable(generate):
            return asyncio.ensure_future(generate(word, part_of_speech))
        return asyncio.ensure_future(client.fetch(word))

    async def _gather(
        self,
        clients: Sequence[LookupClient],
        word: str,
        part_of_speech: PartOfSpeech,
    ) -> list[tuple[LookupClient, list]]:
        """Run every client at once under one shared deadline.

        A single overall timeout rather than per-client ones: the user is waiting on
        the slowest useful answer, not on each source individually. Any client still
        outstanding when the deadline passes is cancelled and treated as not having
        answered -- which ``select_result`` already handles, since a missing source
        and an empty source are equivalent to it (NFR-PERF-03).

        The deadline itself depends on what is running: see :meth:`_deadline_for`,
        which widens it to 60s when a generative source is available, because a local
        model cannot answer inside a dictionary-sized budget.
        """
        tasks = [self._request(client, word, part_of_speech) for client in clients]

        try:
            await asyncio.wait(tasks, timeout=self._deadline_for(clients))
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()

        gathered: list[tuple[LookupClient, list]] = []
        for client, task in zip(clients, tasks, strict=True):
            if not task.done() or task.cancelled():
                continue
            try:
                candidates = task.result()
            except Exception:
                # A client that raises despite the protocol's guarantee is treated
                # as not having answered, rather than failing the whole lookup.
                continue
            gathered.append((client, candidates or []))

        return gathered
