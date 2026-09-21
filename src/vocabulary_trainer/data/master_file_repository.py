"""The Excel master file: the application's system of record.

This is the only module that reads or writes the workbook. Everything it writes
goes through :meth:`MasterFileRepository._mutate`, which combines an atomic
temp-file-then-swap with a lock that serializes concurrent writers. Those two
properties together are what make the workbook safe to trust with months of
collected vocabulary (FR-8.5, FR-8.7).

The workbook is explicitly hand-editable, which shapes two decisions here:
header rows are repaired rather than rejected (FR-8.4), and malformed cells are
coerced rather than causing a row to be dropped. A word with a broken date is
still a word the user collected.
"""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Final

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from vocabulary_trainer.data.errors import (
    CollectionNotFoundError,
    DuplicateCollectionError,
    MasterFileLockedError,
    MasterFileUnreadableError,
)
from vocabulary_trainer.domain.models import (
    Collection,
    CollectionSummary,
    PartOfSpeech,
    RepairReport,
    WordEntry,
)
from vocabulary_trainer.domain.natural_key import (
    names_conflict,
    natural_key,
    normalize,
    normalize_collection,
)

__all__ = [
    "COLLECTIONS_HEADERS",
    "COLLECTIONS_SHEET",
    "DEFAULT_COLLECTION_NAME",
    "MasterFileRepository",
    "WORDS_HEADERS",
    "WORDS_SHEET",
]


WORDS_SHEET: Final = "Words"
COLLECTIONS_SHEET: Final = "Collections"

WORDS_HEADERS: Final = (
    "Words",
    "Type",
    "Meaning",
    "Example",
    "Name of collection",
    "Date",
)
COLLECTIONS_HEADERS: Final = ("Name", "Created date")

DEFAULT_COLLECTION_NAME: Final = "General"
"""Seeded so the very first Collect action always has a destination (FR-8.1)."""

_DATE_FORMATS: Final = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d")


class MasterFileRepository:
    """Reads and writes the Excel workbook holding all vocabulary."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        # RLock rather than Lock: cascade operations call helpers that also take
        # the lock, and a plain Lock would deadlock on re-entry from one thread.
        self._write_lock = threading.RLock()
        self._words_cache: list[WordEntry] | None = None
        self._collections_cache: list[Collection] | None = None

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------
    # Lifecycle and integrity
    # ------------------------------------------------------------------

    def ensure_workbook(self) -> RepairReport:
        """Make the workbook usable, creating or repairing it as needed.

        Creating a workbook on first run is *not* reported as a repair --
        ``RepairReport.needs_user_notice`` is driven by ``changes`` alone, so a
        first run stays silent because there is nothing to warn about
        (FR-8.1, FR-8.3, FR-8.4).
        """
        with self._write_lock:
            self._remove_orphan_temp_files()

            if not self._path.exists():
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._create_fresh_workbook()
                self._invalidate_cache()
                return RepairReport(
                    created_workbook=True, seeded_default_collection=True
                )

            workbook = self._open_workbook()
            changes: list[str] = []
            try:
                changes += self._validate_and_repair(
                    workbook, WORDS_SHEET, WORDS_HEADERS
                )
                changes += self._validate_and_repair(
                    workbook, COLLECTIONS_SHEET, COLLECTIONS_HEADERS
                )
                if changes:
                    self._save_atomically(workbook)
            finally:
                workbook.close()

            self._invalidate_cache()

            seeded = False
            if not self.all_collections():
                self.insert_collection(
                    Collection(name=DEFAULT_COLLECTION_NAME, created_on=date.today())
                )
                seeded = True

            return RepairReport(
                changes=tuple(changes), seeded_default_collection=seeded
            )

    def _create_fresh_workbook(self) -> None:
        workbook = Workbook()
        words = workbook.active
        assert words is not None
        words.title = WORDS_SHEET
        words.append(list(WORDS_HEADERS))

        collections = workbook.create_sheet(COLLECTIONS_SHEET)
        collections.append(list(COLLECTIONS_HEADERS))
        collections.append([DEFAULT_COLLECTION_NAME, date.today()])

        self._save_atomically(workbook)
        workbook.close()

    def _validate_and_repair(
        self, workbook: Workbook, sheet_name: str, expected: tuple[str, ...]
    ) -> list[str]:
        """Correct a sheet's header row in place, returning what changed.

        Repair works by *position*, not by matching names elsewhere in the row: a
        renamed column is corrected where it stands, keeping the data beneath it.
        That is the honest reading of auto-repair -- the user renamed a header, and
        the data under it is still that column's data.

        Columns beyond the expected set are left untouched. The user may have added
        their own notes column, and destroying it would be indefensible for a file
        the product describes as hand-editable.
        """
        changes: list[str] = []

        if sheet_name not in workbook.sheetnames:
            sheet = workbook.create_sheet(sheet_name)
            sheet.append(list(expected))
            return [f"added the missing '{sheet_name}' sheet"]

        sheet = workbook[sheet_name]

        if sheet.max_row < 1 or all(
            cell.value in (None, "") for cell in sheet[1]
        ):
            for index, header in enumerate(expected, start=1):
                sheet.cell(row=1, column=index, value=header)
            return [f"added the missing header row to '{sheet_name}'"]

        for index, header in enumerate(expected, start=1):
            cell = sheet.cell(row=1, column=index)
            found = cell.value

            if found is None or (isinstance(found, str) and not found.strip()):
                cell.value = header
                changes.append(f"added the missing column '{header}' to '{sheet_name}'")
            elif normalize(str(found)) != normalize(header):
                cell.value = header
                changes.append(
                    f"renamed column '{found}' to '{header}' in '{sheet_name}'"
                )

        return changes

    # ------------------------------------------------------------------
    # Atomic write
    # ------------------------------------------------------------------

    def _save_atomically(self, workbook: Workbook) -> None:
        """Write the workbook so the target is only ever fully old or fully new.

        The temp file is created in the target's own directory because
        ``os.replace`` is atomic only within a single filesystem volume; a temp file
        under ``%TEMP%`` could sit on another drive, degrading the swap into a
        copy-then-delete with a window where the target is truncated.

        ``os.replace`` is used rather than ``shutil.move`` because it maps to
        ``MoveFileEx`` with ``MOVEFILE_REPLACE_EXISTING`` on Windows and overwrites
        atomically, which ``shutil.move`` does not guarantee when the destination
        exists (FR-8.5).
        """
        temp_path = self._path.parent / f".{self._path.name}.tmp-{uuid.uuid4().hex}"
        try:
            workbook.save(temp_path)
            os.replace(temp_path, self._path)
        except PermissionError as exc:
            self._quiet_unlink(temp_path)
            raise MasterFileLockedError(self._path) from exc
        except Exception:
            self._quiet_unlink(temp_path)
            raise

    def _mutate(self, build: Callable[[Workbook], None]) -> None:
        """Apply a change under the write lock, atomically.

        Read-modify-write happens entirely inside the lock. Without that, two
        concurrent inserts could each read the same starting state and the second
        would silently drop the first (FR-8.7).
        """
        with self._write_lock:
            workbook = self._open_workbook()
            try:
                build(workbook)
                self._save_atomically(workbook)
            finally:
                workbook.close()
            self._invalidate_cache()

    def _remove_orphan_temp_files(self) -> None:
        """Clear temp files left by a process killed between save and swap."""
        parent = self._path.parent
        if not parent.is_dir():
            return
        for leftover in parent.glob(f".{self._path.name}.tmp-*"):
            self._quiet_unlink(leftover)

    @staticmethod
    def _quiet_unlink(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            # A temp file we cannot remove is untidy, not incorrect. Never let
            # cleanup mask the original outcome.
            pass

    def _open_workbook(self) -> Workbook:
        try:
            return load_workbook(self._path)
        except MasterFileUnreadableError:
            raise
        except PermissionError as exc:
            raise MasterFileLockedError(self._path) from exc
        except Exception as exc:
            raise MasterFileUnreadableError(self._path, str(exc)) from exc

    def _invalidate_cache(self) -> None:
        self._words_cache = None
        self._collections_cache = None

    def invalidate_cache(self) -> None:
        """Drop cached reads. Called by the file watcher on external change (U3)."""
        with self._write_lock:
            self._invalidate_cache()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def all_words(self) -> list[WordEntry]:
        if self._words_cache is None:
            self._words_cache = self._read_words()
        return list(self._words_cache)

    def all_collections(self) -> list[Collection]:
        if self._collections_cache is None:
            self._collections_cache = self._read_collections()
        return list(self._collections_cache)

    def collection_summaries(self) -> list[CollectionSummary]:
        counts: dict[str, int] = {}
        for entry in self.all_words():
            key = normalize_collection(entry.collection_name)
            counts[key] = counts.get(key, 0) + 1
        return [
            CollectionSummary(
                name=collection.name,
                created_on=collection.created_on,
                word_count=counts.get(normalize_collection(collection.name), 0),
            )
            for collection in self.all_collections()
        ]

    def find_by_natural_key(self, word: str, collection_name: str) -> WordEntry | None:
        """Locate an entry by its identity (FR-8.9).

        Normalization is delegated to ``domain.natural_key`` so this lookup and
        duplicate detection can never disagree about what counts as the same word.
        """
        target = natural_key(word, collection_name)
        for entry in self.all_words():
            if entry.natural_key == target:
                return entry
        return None

    def word_count_for(self, collection_name: str) -> int:
        target = normalize_collection(collection_name)
        return sum(
            1
            for entry in self.all_words()
            if normalize_collection(entry.collection_name) == target
        )

    def words_for(self, collection_name: str) -> list[WordEntry]:
        """Every entry belonging to one collection.

        Lives here rather than being filtered in each service because both the
        Settings Collections tab (FR-7.14) and the Practice setup screen (FR-5.10)
        preview the same thing -- two copies of the same filter could drift on what
        counts as "in this collection", which is exactly the class of bug
        ``domain.natural_key`` exists to prevent.
        """
        target = normalize_collection(collection_name)
        return [
            entry
            for entry in self.all_words()
            if normalize_collection(entry.collection_name) == target
        ]

    def _read_words(self) -> list[WordEntry]:
        workbook = self._open_workbook()
        try:
            if WORDS_SHEET not in workbook.sheetnames:
                return []
            sheet = workbook[WORDS_SHEET]
            entries: list[WordEntry] = []
            for row in sheet.iter_rows(min_row=2, values_only=True):
                entry = self._parse_word_row(row)
                if entry is not None:
                    entries.append(entry)
            return entries
        finally:
            workbook.close()

    def _parse_word_row(self, row: tuple[object, ...]) -> WordEntry | None:
        """Turn a raw row into an entry, coercing messy cells.

        A blank word is the only condition that discards a row, because a row
        without a word carries no information. Everything else is coerced: the
        workbook is hand-edited, and a formatting mistake must not cost the user a
        word they collected.
        """
        raw_word = self._as_text(self._at(row, 0))
        if not raw_word:
            return None

        collection = self._as_text(self._at(row, 4)) or DEFAULT_COLLECTION_NAME

        return WordEntry(
            word=raw_word,
            part_of_speech=self._as_part_of_speech(self._at(row, 1)),
            meaning=self._as_optional_text(self._at(row, 2)),
            example=self._as_optional_text(self._at(row, 3)),
            collection_name=collection,
            collected_on=self._as_date(self._at(row, 5)),
        )

    def _read_collections(self) -> list[Collection]:
        workbook = self._open_workbook()
        try:
            if COLLECTIONS_SHEET not in workbook.sheetnames:
                return []
            sheet = workbook[COLLECTIONS_SHEET]
            collections: list[Collection] = []
            for row in sheet.iter_rows(min_row=2, values_only=True):
                name = self._as_text(self._at(row, 0))
                if not name:
                    continue
                collections.append(
                    Collection(name=name, created_on=self._as_date(self._at(row, 1)))
                )
            return collections
        finally:
            workbook.close()

    # ------------------------------------------------------------------
    # Cell coercion
    # ------------------------------------------------------------------

    @staticmethod
    def _at(row: tuple[object, ...], index: int) -> object:
        return row[index] if index < len(row) else None

    @staticmethod
    def _as_text(value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @classmethod
    def _as_optional_text(cls, value: object) -> str | None:
        text = cls._as_text(value)
        return text or None

    @staticmethod
    def _as_part_of_speech(value: object) -> PartOfSpeech:
        """Coerce a type cell, defaulting rather than dropping the row."""
        text = str(value).strip().casefold() if value is not None else ""
        for member in PartOfSpeech:
            if member.value == text:
                return member
        return PartOfSpeech.NOUN

    @classmethod
    def _as_date(cls, value: object) -> date:
        """Coerce a date cell, falling back to today rather than dropping the row."""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        text = cls._as_text(value)
        if text:
            for fmt in _DATE_FORMATS:
                try:
                    return datetime.strptime(text, fmt).date()
                except ValueError:
                    continue
        return date.today()

    # ------------------------------------------------------------------
    # Word mutations
    # ------------------------------------------------------------------

    def insert_word(self, entry: WordEntry) -> None:
        def build(workbook: Workbook) -> None:
            sheet = self._require_sheet(workbook, WORDS_SHEET, WORDS_HEADERS)
            sheet.append(
                [
                    entry.word,
                    entry.part_of_speech.value,
                    entry.meaning or "",
                    entry.example or "",
                    entry.collection_name,
                    entry.collected_on,
                ]
            )

        self._mutate(build)

    def patch_word_enrichment(
        self, key: tuple[str, str], meaning: str | None, example: str | None
    ) -> bool:
        """Fill in Meaning and Example on an existing row (FR-2.9).

        Returns ``False`` when the row no longer exists, so a lookup that finishes
        after its row was deleted cannot resurrect it (E2-S4 branch 6c).
        """
        patched = False

        def build(workbook: Workbook) -> None:
            nonlocal patched
            sheet = self._require_sheet(workbook, WORDS_SHEET, WORDS_HEADERS)
            for row in sheet.iter_rows(min_row=2):
                if self._row_key(row) == key:
                    row[2].value = meaning or ""
                    row[3].value = example or ""
                    patched = True
                    return

        self._mutate(build)
        return patched

    def replace_word(self, entry: WordEntry) -> bool:
        """Overwrite Meaning, Example and Date on an existing row (FR-4.4).

        Word and collection are deliberately left as they are: Replace refreshes
        the entry's content, it does not move or rename it.
        """
        replaced = False

        def build(workbook: Workbook) -> None:
            nonlocal replaced
            sheet = self._require_sheet(workbook, WORDS_SHEET, WORDS_HEADERS)
            target = entry.natural_key
            for row in sheet.iter_rows(min_row=2):
                if self._row_key(row) == target:
                    row[1].value = entry.part_of_speech.value
                    row[2].value = entry.meaning or ""
                    row[3].value = entry.example or ""
                    row[5].value = entry.collected_on
                    replaced = True
                    return

        self._mutate(build)
        return replaced

    def delete_word(self, key: tuple[str, str]) -> bool:
        deleted = False

        def build(workbook: Workbook) -> None:
            nonlocal deleted
            sheet = self._require_sheet(workbook, WORDS_SHEET, WORDS_HEADERS)
            for row in sheet.iter_rows(min_row=2):
                if self._row_key(row) == key:
                    sheet.delete_rows(row[0].row, 1)
                    deleted = True
                    return

        self._mutate(build)
        return deleted

    @classmethod
    def _row_key(cls, row: tuple[object, ...]) -> tuple[str, str]:
        cells = list(row)
        word = cls._as_text(cells[0].value if len(cells) > 0 else None)  # type: ignore[union-attr]
        collection = cls._as_text(cells[4].value if len(cells) > 4 else None)  # type: ignore[union-attr]
        return natural_key(word, collection or DEFAULT_COLLECTION_NAME)

    # ------------------------------------------------------------------
    # Collection mutations
    # ------------------------------------------------------------------

    def insert_collection(self, collection: Collection) -> None:
        existing = self.all_collections()
        if any(names_conflict(collection.name, other.name) for other in existing):
            raise DuplicateCollectionError(collection.name)

        def build(workbook: Workbook) -> None:
            sheet = self._require_sheet(
                workbook, COLLECTIONS_SHEET, COLLECTIONS_HEADERS
            )
            sheet.append([collection.name, collection.created_on])

        self._mutate(build)

    def rename_collection(self, old_name: str, new_name: str) -> None:
        """Rename a collection and carry all its words with it (FR-7.9).

        The collection row and every affected word row change inside **one** atomic
        write, so either the whole rename lands or none of it does. There is no
        partial state to revert, because a partial state is never written -- which
        is why the service layer needs no compensating logic.

        Rows are matched case-insensitively but the new name is stored exactly as
        typed. That is what makes recasing work: renaming ``ielts`` to ``IELTS``
        finds every old row and rewrites it with the new capitalization.
        """
        with self._write_lock:
            existing = self.all_collections()
            if not any(names_conflict(old_name, other.name) for other in existing):
                raise CollectionNotFoundError(old_name)

            is_recase = names_conflict(old_name, new_name)
            if not is_recase and any(
                names_conflict(new_name, other.name) for other in existing
            ):
                raise DuplicateCollectionError(new_name)

            target = normalize_collection(old_name)

            def build(workbook: Workbook) -> None:
                collections = self._require_sheet(
                    workbook, COLLECTIONS_SHEET, COLLECTIONS_HEADERS
                )
                for row in collections.iter_rows(min_row=2):
                    if normalize_collection(self._as_text(row[0].value)) == target:
                        row[0].value = new_name

                words = self._require_sheet(workbook, WORDS_SHEET, WORDS_HEADERS)
                for row in words.iter_rows(min_row=2):
                    if len(row) > 4 and (
                        normalize_collection(self._as_text(row[4].value)) == target
                    ):
                        row[4].value = new_name

            self._mutate(build)

    def delete_collection(self, name: str) -> int:
        """Delete a collection and all its words, returning how many were removed.

        Also a single atomic write, so a failure deletes nothing rather than
        half-cascading (FR-7.11, E7-S8 branch 7a).
        """
        with self._write_lock:
            if not any(names_conflict(name, other.name) for other in self.all_collections()):
                raise CollectionNotFoundError(name)

            target = normalize_collection(name)
            removed = 0

            def build(workbook: Workbook) -> None:
                nonlocal removed
                words = self._require_sheet(workbook, WORDS_SHEET, WORDS_HEADERS)
                doomed = [
                    row[0].row
                    for row in words.iter_rows(min_row=2)
                    if len(row) > 4
                    and normalize_collection(self._as_text(row[4].value)) == target
                ]
                # Delete bottom-up so earlier deletions do not shift later indices.
                for row_index in sorted(doomed, reverse=True):
                    words.delete_rows(row_index, 1)
                removed = len(doomed)

                collections = self._require_sheet(
                    workbook, COLLECTIONS_SHEET, COLLECTIONS_HEADERS
                )
                for row in list(collections.iter_rows(min_row=2)):
                    if normalize_collection(self._as_text(row[0].value)) == target:
                        collections.delete_rows(row[0].row, 1)
                        break

            self._mutate(build)
            return removed

    def ensure_default_collection(self) -> bool:
        """Seed ``General`` when no collection exists (FR-8.1, E7-S8 branch 7b)."""
        with self._write_lock:
            if self.all_collections():
                return False
            self.insert_collection(
                Collection(name=DEFAULT_COLLECTION_NAME, created_on=date.today())
            )
            return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_sheet(
        self, workbook: Workbook, name: str, headers: Iterable[str]
    ) -> Worksheet:
        """Fetch a sheet, creating it with headers if a user removed it."""
        if name not in workbook.sheetnames:
            sheet = workbook.create_sheet(name)
            sheet.append(list(headers))
            return sheet
        return workbook[name]
