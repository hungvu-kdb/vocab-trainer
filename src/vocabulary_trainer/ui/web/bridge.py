"""The JavaScript-to-Python boundary for the web-rendered windows.

Everything the HTML layer can do passes through a bridge object exposed over
``QWebChannel``. The rule that keeps this honest: **the bridge carries data and calls,
never decisions.** JavaScript captures input and renders state; every judgement --
whether an answer is correct, which lookup source wins, how many words a delete will
destroy -- is made by a Python service.

Consequences worth stating:

* Every slot returns JSON-serializable primitives. Passing a dataclass across the
  channel would force the JS side to know Python's shapes.
* Every slot catches its own exceptions and returns an error payload. An exception
  crossing the channel surfaces in JavaScript as an opaque failure with no message,
  which is precisely the sort of raw error NFR-REL-01 forbids reaching the user.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Slot

__all__ = ["BridgeBase", "ok", "fail"]


def ok(**payload: Any) -> dict[str, Any]:
    """A successful response."""
    return {"ok": True, **payload}


def fail(message: str, **payload: Any) -> dict[str, Any]:
    """A failed response carrying a message written for display."""
    return {"ok": False, "error": message, **payload}


class BridgeBase(QObject):
    """Shared plumbing for the Practice and Settings bridges."""

    def __init__(self) -> None:
        super().__init__()
        self._log: list[str] = []

    def _guard(self, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """Run a slot body, converting any escape into an error payload.

        Service-layer errors carry user-facing messages, so those are passed through
        verbatim. Anything else is replaced with a generic message and recorded, since
        an unexpected internal error is not something a user can act on.
        """
        from vocabulary_trainer.data.errors import MasterFileError
        from vocabulary_trainer.services.errors import ServiceError

        try:
            return operation()
        except (ServiceError, MasterFileError) as exc:
            return fail(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self._log.append(repr(exc))
            return fail("Something went wrong. Please try again.")

    @Slot(result="QVariant")
    def diagnostics(self) -> dict[str, Any]:
        """Recent internal errors, for troubleshooting a misbehaving window."""
        return ok(errors=list(self._log[-20:]))
