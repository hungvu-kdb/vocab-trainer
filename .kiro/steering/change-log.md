# Always update change_log.md when you change code

`change_log.md` at the repository root is a permanent, human-readable record of what
changed in this project and why. It is not generated and it is not optional.

## When to write an entry

Write one **whenever you modify, add, or delete code** — any file under `src/`,
`tests/`, `install_tool/`, or `pyproject.toml`.

Write the entry **in the same turn as the change**, once the change is verified. Not
at the end of a long session, and never batched up across several unrelated changes:
a log written from memory hours later loses the detail that makes it worth having.

Skip it only for:

- Documentation-only edits (`*.md`, including this file and `change_log.md` itself).
- Temporary scratch or verification scripts that are deleted before finishing.
- Work that was reverted, leaving no net change.

If a change turns out to be unnecessary and you drop it, that is still worth a line —
it stops the same idea being re-proposed later.

## Format

Newest entries at the **top** of the file, directly under the header block. Each
entry:

```markdown
# Date yyyy-mm-dd hh:mm

{change information}

---
```

Use the **real current date and time**, 24-hour clock. Get it from the system rather
than guessing:

```cmd
powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm'"
```

## What to write

Lead with one bold sentence saying what changed, in terms a reader who has not seen
the code will understand. Then the detail:

- **Name the files** you touched, each with what changed in it and why. Group by file,
  not by line.
- **Record the reasoning behind non-obvious decisions**, especially where you rejected
  a simpler-looking option. This is the part that pays off months later.
- **Record bugs you found**, including ones you introduced and fixed in the same
  change, and how you found them. A bug that only surfaced under a real measurement
  rather than a unit test is worth saying so.
- **State what you verified**, with the concrete result — test counts, measured
  values, actual output. Not "tested and working".
- **Say what you deliberately did not do**, if a reader might otherwise assume you
  had.

Be specific and factual. "Fixed the widget" is useless; "the widget grew but never
shrank, because `resize()` is floored by the minimum size Qt retains from the largest
pixmap held" is what someone needs.

Keep it proportional: a one-line fix gets a short entry, a new feature gets a
thorough one. Do not pad.

## Rules

- **Never rewrite or delete an existing entry.** The log is append-only. If an earlier
  entry was wrong, add a new entry correcting it and say which one it corrects.
- **Do not renumber, reorder, or reformat** entries you did not write in this turn.
- One entry per logical change, even if it spans several files. Two unrelated changes
  made in the same turn get two entries.
- Write in the same language the user is using in conversation.
- Mention `change_log.md` in your reply only if the user asked about it, or if the
  entry itself is worth their attention. Updating it is routine, not an achievement to
  report.
