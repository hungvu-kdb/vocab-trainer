# Functional Design — U2 Master File Repository

**Unit**: U2 — Master File Repository
**Stories**: E8-S1, E8-S2, E8-S3, E8-S6
**Requirements**: FR-8.1, FR-8.3, FR-8.4, FR-8.5, FR-8.7, FR-8.9

This is the unit where data loss would actually happen, which is why it is built second and tested
against real `.xlsx` files rather than mocks.

---

## 1. Workbook Schema

Two sheets. Header row is row 1; data begins at row 2.

**`Words` sheet**

| Col | Header | Type |
|---|---|---|
| A | `Words` | text |
| B | `Type` | text (a `PartOfSpeech` value) |
| C | `Meaning` | text, may be blank |
| D | `Example` | text, may be blank |
| E | `Name of collection` | text |
| F | `Date` | date |

**`Collections` sheet**

| Col | Header | Type |
|---|---|---|
| A | `Name` | text |
| B | `Created date` | date |

Headers come verbatim from the spec's data model so a user opening the workbook sees the column names
the spec documents.

---

## 2. Atomic Write (FR-8.5) — the core algorithm

Every mutation routes through this. It is the only place that writes the target path.

```
atomic_write(build_workbook):
    tmp = target.parent / f".{target.name}.tmp-{uuid4().hex}"
    try:
        workbook = build_workbook()          # construct fully in memory first
        workbook.save(tmp)                   # a failure here leaves target untouched
        os.replace(tmp, target)              # atomic on the same volume
    except PermissionError as exc:
        cleanup(tmp)
        raise MasterFileLockedError(target) from exc
    except Exception:
        cleanup(tmp)
        raise
```

**Why the temp file sits in the target's own directory**: `os.replace` is only atomic within a single
filesystem volume. A temp file in `%TEMP%` could be on a different drive, turning the swap into a
copy-then-delete with a window where the target is truncated.

**Why the workbook is built completely before saving**: if serialization raises halfway, nothing has
touched the target. The failure costs the change, never the file.

**Why `os.replace` and not `shutil.move`**: `os.replace` maps to `MoveFileEx` with
`MOVEFILE_REPLACE_EXISTING` on Windows and overwrites atomically. `shutil.move` is not atomic when the
destination exists.

**Why the temp name is dotted and randomized**: dotted so it sorts out of the way and reads as
transient; randomized so two processes cannot collide.

**Orphan cleanup**: on `ensure_workbook`, any `.{name}.tmp-*` sibling is removed. A process killed
between save and replace leaves one behind, and it should not accumulate.

---

## 3. Write Serialization (FR-8.7)

A single `threading.RLock` guards every mutating method.

```
def _mutate(self, build_workbook):
    with self._write_lock:
        self._atomic_write(build_workbook)
        self._invalidate_cache()
```

**Why `RLock` rather than `Lock`**: cascade operations call helpers that also acquire it. A plain
`Lock` would deadlock on re-entry from the same thread.

**Read-modify-write is inside the lock.** A mutation reads current state, computes the new state, and
writes — all while holding the lock. Otherwise two concurrent inserts could each read the same
starting state and the second would silently drop the first.

---

## 4. Header Validation and Repair (FR-8.3, FR-8.4)

```
validate_and_repair(sheet, expected_headers) -> list[str]:
    changes = []
    actual = read_row_1(sheet)

    if sheet has no rows at all:
        write expected_headers into row 1
        return ["added missing header row to '<sheet>'"]

    for index, expected in enumerate(expected_headers):
        found = actual[index] if index < len(actual) else None
        if found is None or blank:
            write expected at that column
            changes.append(f"added missing column '<expected>' to '<sheet>'")
        elif normalize(found) != normalize(expected):
            write expected at that column
            changes.append(f"renamed column '<found>' to '<expected>' in '<sheet>'")

    return changes
```

**Repair is by position, not by matching names.** A renamed column is corrected in place, keeping the
data beneath it. This is the honest reading of "auto-repair": the user renamed a header, the data under
it is still that column's data.

**Comparison is normalized** (case and whitespace) so `"words"` or `" Words "` is accepted as-is
rather than being noisily "repaired" to `"Words"`.

**Extra columns beyond the expected set are left alone.** A user may have added a personal notes
column, and destroying it would be indefensible for a file the spec calls human-editable.

**Unreadable file versus repairable file**: a file that openpyxl cannot open at all raises
`MasterFileUnreadableError` and no repair is attempted (E8-S3 branch 1a). Repair applies only to a
workbook that opens but has the wrong headers.

**A missing sheet is created** with its header row, rather than treated as fatal.

---

## 5. First-Run Creation (FR-8.1)

```
ensure_workbook() -> RepairReport:
    remove_orphan_temp_files()

    if target does not exist:
        mkdir parents
        create workbook with both sheets and both header rows
        seed Collection("General", today)
        return RepairReport(created_workbook=True, seeded_default_collection=True)

    open workbook                      # MasterFileUnreadableError if not a workbook
    changes = validate_and_repair(Words) + validate_and_repair(Collections)
    if changes:  write repaired workbook atomically

    if no collections exist:
        insert Collection("General", today)
        seeded = True

    return RepairReport(changes=changes, seeded_default_collection=seeded)
```

**Creation is not reported as a repair.** `RepairReport.needs_user_notice` is driven by `changes`
only, so a first run is silent — there is nothing to warn about.

**Seeding an existing workbook that has words but no collections** adds `General` without touching any
word row. Those orphaned words keep their own collection names; seeding only guarantees Collect has a
destination.

---

## 6. Cascade Rename (FR-7.9)

The requirement forbids leaving rows inconsistent on partial failure. Rather than rename and then
patch rows — which can fail between the two — both changes happen inside **one** atomic write.

```
rename_collection(old, new):
    with lock:
        atomic_write(build):
            in Collections sheet: replace the row whose name matches old (normalized) with new
            in Words sheet: for every row whose 'Name of collection' matches old (normalized),
                            set it to new
```

Either the whole rename lands or none of it does. **There is no partial state to revert, because a
partial state is never written.** The service layer needs no compensating logic.

**Matching is normalized, writing is verbatim.** Rows are found case-insensitively; the new name is
stored exactly as the user typed it. This is what makes recasing work: renaming `"ielts"` to `"IELTS"`
matches all the old rows and rewrites them with the new capitalization.

## 7. Cascade Delete (FR-7.11)

```
delete_collection(name) -> int:
    with lock:
        atomic_write(build):
            removed = count of Words rows whose collection matches name (normalized)
            drop those rows
            drop the Collections row
        return removed
```

Also one atomic write, so a failure deletes nothing (E7-S8 branch 7a) rather than half-cascading.
Returns the count so the caller can confirm what the confirmation dialog promised.

---

## 8. Natural-Key Lookup (FR-8.9)

```
find_by_natural_key(word, collection) -> WordEntry | None:
    target = natural_key(word, collection)
    return first row whose natural_key == target, else None
```

Delegates entirely to `domain.natural_key`. The repository defines no normalization of its own, so
lookup and duplicate detection cannot disagree.

---

## 9. Read Caching

Reads are frequent (every popup open, every Practice setup). Re-parsing the workbook each time would
be wasteful, so parsed rows are cached and the cache is invalidated on:

- any mutation through this repository, and
- an external file change detected by the watcher (added in U3).

The cache holds parsed `WordEntry` and `Collection` values, which are frozen — so a caller cannot
mutate cached state.

---

## 10. Type Coercion on Read

Real workbooks contain messy cells, and this file is explicitly hand-editable. Rules:

| Situation | Behavior |
|---|---|
| `Date` cell holds a `datetime` | take `.date()` |
| `Date` cell holds a string | parse ISO first, then common formats; fall back to today |
| `Date` cell is blank | today |
| `Type` cell holds an unrecognized value | default to `PartOfSpeech.NOUN` rather than dropping the row |
| `Words` cell is blank | skip the row entirely — a word is required |
| `Name of collection` is blank | assign `General` |
| `Meaning` / `Example` blank | `None` |

**The principle: never lose a user's row over a formatting problem.** A word with a broken date is
still a word they collected. The one exception is a blank word, which carries no information at all.

---

## 11. Errors

| Error | Raised when | Caller behavior |
|---|---|---|
| `MasterFileLockedError` | `PermissionError` during save or replace | hold the change, offer Retry (FR-8.6) |
| `MasterFileUnreadableError` | openpyxl cannot open the file | reject a path change, keep the previous path |
| `CollectionNotFoundError` | rename or delete names a missing collection | surface as a validation message |
| `DuplicateCollectionError` | insert or rename collides case-insensitively | inline field error |

---

## Test Plan

All against real temporary `.xlsx` files in `tmp_path` — no mocking of openpyxl.

| # | Area | Cases |
|---|---|---|
| 1 | Creation | absent file created with both sheets, correct headers, seeded General; parent dirs created; creation not flagged as a repair |
| 2 | Header repair | renamed column corrected keeping data; missing column added; missing header row added; missing sheet created; valid headers produce no changes; case/whitespace variants accepted silently; extra user columns preserved |
| 3 | Unreadable | a non-workbook file raises `MasterFileUnreadableError` and is not repaired |
| 4 | Reads | round-trip words and collections; summaries carry correct counts; blank word rows skipped; unknown type defaults; blank collection assigned General; broken date falls back |
| 5 | Natural-key lookup | exact, case-difference, whitespace-difference, no match, same word other collection |
| 6 | Word mutations | insert; patch enrichment returns True; patch a deleted row returns False without recreating it; replace preserves word and collection while changing meaning/example/date; delete |
| 7 | Cascade rename | every matching row updated; non-matching rows untouched; recasing own name works; collision rejected; missing collection raises |
| 8 | Cascade delete | collection and its rows removed with the correct count returned; other collections' rows untouched; empty collection deletable |
| 9 | Atomic write | no temp file remains after success; a simulated failure before the swap leaves the original content intact and removes the temp; orphaned temp files cleaned on `ensure_workbook` |
| 10 | Locked file | a `PermissionError` on replace surfaces as `MasterFileLockedError` and the target keeps its previous content |
| 11 | Serialization | many concurrent inserts from threads all land, with no lost update |

Coverage target: 90%+ on this unit. The residue is platform error paths that cannot be triggered
portably.
