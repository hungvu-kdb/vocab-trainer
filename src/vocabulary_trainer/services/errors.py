"""Service-layer errors.

Errors are translated at this boundary. Raw file-system, HTTP, and library
exceptions never reach the UI (NFR-REL-01), so every message here is written to be
shown to a user as-is.

The distinction that matters: failures the user must act on become typed errors,
while failures they can do nothing about degrade quietly and are reported by a
``False`` return instead.
"""

from __future__ import annotations

__all__ = ["EmptyPoolError", "ServiceError", "ValidationError"]


class ServiceError(Exception):
    """Base class for service-layer failures with user-facing messages."""


class ValidationError(ServiceError):
    """User input was rejected. The message is shown beside the offending field."""


class EmptyPoolError(ServiceError):
    """A practice session was requested with no words in it.

    The setup screen disables Start when the pool is empty (FR-5.8), so reaching
    this is a defect rather than a user mistake. It exists as a backstop so the
    drill can never open on an empty pool and fail confusingly.
    """

    def __init__(self) -> None:
        super().__init__(
            "The selected collections contain no words. "
            "Choose a collection with at least one word to practise."
        )
