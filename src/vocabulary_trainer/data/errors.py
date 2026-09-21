"""Errors raised by the data layer.

These are deliberately distinguishable from one another because the UI reacts
differently to each: a locked file offers Retry and preserves the user's input, an
unreadable file rejects a path change, and a validation problem shows an inline
message beside the offending field.

Raw ``OSError`` and openpyxl exceptions never escape this layer -- NFR-REL-01
requires that no library error text reaches the user.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "CollectionNotFoundError",
    "DuplicateCollectionError",
    "MasterFileError",
    "MasterFileLockedError",
    "MasterFileUnreadableError",
]


class MasterFileError(Exception):
    """Base class for master-file problems."""


class MasterFileLockedError(MasterFileError):
    """The workbook could not be written because another process holds it.

    Almost always Excel with the file open. The caller keeps the pending change in
    memory and offers a Retry action rather than discarding the user's work
    (FR-8.6).
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            f"The vocabulary file is open in another program:\n{path}\n\n"
            "Close it in Excel and try again."
        )


class MasterFileUnreadableError(MasterFileError):
    """The file is not a workbook this application can open.

    No repair is attempted -- header repair applies to a workbook that opens but
    has the wrong columns, not to a file that is not a workbook at all
    (E8-S3 branch 1a).
    """

    def __init__(self, path: Path, reason: str = "") -> None:
        self.path = path
        detail = f"\n\n{reason}" if reason else ""
        super().__init__(f"This file could not be read as an Excel workbook:\n{path}{detail}")


class CollectionNotFoundError(MasterFileError):
    """A rename or delete named a collection that does not exist."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"No collection named '{name}' exists.")


class DuplicateCollectionError(MasterFileError):
    """A collection name collides with an existing one, ignoring case.

    Names are compared case-insensitively (FR-2.5, FR-7.8), so ``ielts`` collides
    with ``IELTS``.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A collection named '{name}' already exists.")
