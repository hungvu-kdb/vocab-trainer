"""Practice session history, appended as JSON under ``%AppData%``.

Deliberately kept out of the master workbook (FR-6.16): the workbook stays a clean
vocabulary list that a user can open in Excel without wading past session logs.

Every method degrades quietly. A summary screen must display even when its results
could not be recorded (E6-S6 branch 4a) -- the user finished the work either way,
and failing to save a statistic is not worth an error dialog.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from vocabulary_trainer.domain.models import SessionSummary

__all__ = ["HistoryStore"]

_MAX_RECORDS = 500
"""Cap on retained sessions.

Practice history is informational, not a system of record. Trimming keeps the file
small and the read cheap; a user wanting long-term analytics is out of scope.
"""


class HistoryStore:
    """Appends and reads practice session results."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, summary: SessionSummary) -> bool:
        """Record a finished session, reporting success without raising.

        Returns ``False`` on any failure so the caller can log it and carry on
        showing the summary (FR-6.16).
        """
        records = self._read_records()
        records.append(
            {
                "score": summary.score,
                "words_practiced": summary.words_practiced,
                "total_penalties": summary.total_penalties,
                "elapsed_seconds": summary.elapsed.total_seconds(),
                "finished_at": summary.finished_at.isoformat(),
            }
        )
        del records[:-_MAX_RECORDS]
        return self._write_records(records)

    def all_sessions(self) -> list[SessionSummary]:
        """Every retained session, oldest first. Unparseable records are skipped."""
        summaries: list[SessionSummary] = []
        for record in self._read_records():
            summary = self._parse(record)
            if summary is not None:
                summaries.append(summary)
        return summaries

    # ------------------------------------------------------------------

    def _read_records(self) -> list[dict[str, object]]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    def _write_records(self, records: list[dict[str, object]]) -> bool:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            handle, temp_name = tempfile.mkstemp(
                dir=self._path.parent, prefix=".history-", suffix=".tmp"
            )
            temp_path = Path(temp_name)
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    json.dump(records, stream, indent=2)
                os.replace(temp_path, self._path)
            except BaseException:
                temp_path.unlink(missing_ok=True)
                raise
            return True
        except OSError:
            return False

    @staticmethod
    def _parse(record: dict[str, object]) -> SessionSummary | None:
        try:
            finished_raw = record["finished_at"]
            if not isinstance(finished_raw, str):
                return None
            return SessionSummary(
                score=int(record["score"]),  # type: ignore[arg-type]
                words_practiced=int(record["words_practiced"]),  # type: ignore[arg-type]
                total_penalties=int(record["total_penalties"]),  # type: ignore[arg-type]
                elapsed=timedelta(seconds=float(record["elapsed_seconds"])),  # type: ignore[arg-type]
                finished_at=datetime.fromisoformat(finished_raw),
            )
        except (KeyError, TypeError, ValueError):
            return None
