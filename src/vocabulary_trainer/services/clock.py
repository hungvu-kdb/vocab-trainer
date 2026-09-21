"""Time, injected rather than read directly.

Two requirements make this necessary rather than fussy: FR-2.8 stamps every saved
row with the current date, and FR-6.14 reports how long a session took. Reading the
system clock inline would make both untestable without either sleeping in tests or
asserting on whatever value happens to come back.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Protocol

__all__ = ["Clock", "FixedClock", "SystemClock"]


class Clock(Protocol):
    """Source of the current date and time."""

    def today(self) -> date:
        """Current date, for stamping a collected word."""
        ...

    def now(self) -> datetime:
        """Current timestamp, for session start and end."""
        ...


class SystemClock:
    """The real clock, used in production."""

    def today(self) -> date:
        return date.today()

    def now(self) -> datetime:
        return datetime.now()


class FixedClock:
    """A controllable clock for tests.

    ``advance`` lets a test move time forward deliberately, so elapsed-time
    assertions are exact instead of approximate.
    """

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def today(self) -> date:
        return self._moment.date()

    def now(self) -> datetime:
        return self._moment

    def advance(self, **kwargs: float) -> None:
        """Move the clock forward, e.g. ``advance(minutes=18, seconds=42)``."""
        self._moment = self._moment + timedelta(**kwargs)

    def set(self, moment: datetime) -> None:
        self._moment = moment
