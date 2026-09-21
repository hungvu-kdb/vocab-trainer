"""The contract every lookup source implements.

Three sources with different transports and response shapes answer the same
question, and the orchestrator needs them uniformly comparable so priority
selection can work (FR-3.3).

Two rules matter more than the shape itself:

* ``fetch`` **never raises**. Failure is the normal case here -- offline, no entry
  for the word, a timeout, a rate limit. Returning an empty list keeps the
  orchestrator free of exception plumbing and guarantees a word can still be saved
  (FR-3.5, FR-3.9).
* A client decides only whether it *can* answer, never whether its answer *wins*.
  Priority lives in ``domain.lookup_priority``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from vocabulary_trainer.domain.models import (
    DefinitionCandidate,
    LookupSource,
    PartOfSpeech,
)

__all__ = ["GenerativeLookupClient", "LookupClient"]


@runtime_checkable
class LookupClient(Protocol):
    """A single dictionary or translation source."""

    @property
    def source(self) -> LookupSource:
        """Which source this is, used as the priority key."""
        ...

    def is_available(self) -> bool:
        """Whether this client can be used at all.

        Distinct from "will succeed". Merriam-Webster reports ``False`` when no API
        key is configured, which is how FR-3.8's skip behaviour becomes a matter of
        not calling the client rather than a conditional threaded through the
        orchestrator.
        """
        ...

    async def fetch(self, word: str) -> list[DefinitionCandidate]:
        """Candidate definitions for ``word``, or an empty list.

        Must never raise. Must never block longer than the caller's timeout allows
        to be cancelled.
        """
        ...


@runtime_checkable
class GenerativeLookupClient(Protocol):
    """A source that needs the chosen part of speech to produce an answer.

    Dictionaries return every sense they hold and let ``select_definition`` pick;
    a generative source is asked for the one sense that matches instead, so it
    needs the part of speech up front.

    A separate protocol rather than a wider ``fetch`` signature on
    :class:`LookupClient`: adding a parameter there would touch four clients that
    have no use for it, purely to accommodate a fifth. ``LookupService`` checks for
    this at runtime and calls whichever method a client offers.
    """

    async def generate(
        self, word: str, part_of_speech: PartOfSpeech
    ) -> list[DefinitionCandidate]:
        """Candidate definitions for ``word`` as ``part_of_speech``, or empty.

        Same guarantee as ``fetch``: never raises.
        """
        ...
