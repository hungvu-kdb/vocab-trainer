---
inclusion: manual
---

# "Wrap up" — release-packaging workflow

Trigger: the user says **"wrap up"** (or a clear variant like "let's wrap up" /
"wrap this up"), with no further explanation needed. When triggered, run the
full sequence below in order. Do not skip steps or reorder them.

## Why this exists

`current_published_installation_package/` holds whatever installer the user's
end users (their "friend"/testers) actually have installed right now — it is
the **shipped baseline**, not the latest build. The source tree in `src/`
moves ahead of it constantly. "Wrap up" is the ritual that closes that gap:
diff the baseline against `change_log.md`, let the user choose which changes
actually ship in the next release, build accordingly, and hand off exactly one
folder (`send_out/`) that is safe to give to end users.

## Step 1 — Identify the baseline

Read every file in `current_published_installation_package/`. For the
`.cmd`/`.exe` installer, extract the embedded version string and wheel/package
name (for the `.cmd`, it is plain text after `#PSBEGIN`, e.g. `$AppVersion` and
`$WheelName`; for a PyInstaller `.exe`, the version was baked in at build time
by `install_tool/build_exe.py` — check `change_log.md` around the matching
date instead, since the binary itself won't grep cleanly).

This tells you the exact point in project history the current install
represents.

## Step 2 — List what's new since then, as a checkbox list

Read `change_log.md` top-to-bottom (newest first) and stop once you reach an
entry at or before the baseline's date/version. Everything above that line is
a candidate.

Do **not** present this list inline in chat. Write it to a file instead:

`send_out/wrap-up-checklist.md`

One checkbox per changelog entry (not per file) — group multiple file-level
bullets from one entry into one checkbox, since that's the unit the user
actually decides on. For each item give: a one-line plain-language
description (not the internal implementation prose from the changelog), and
flag clearly if that entry is **known-broken / has an open question** (e.g. a
refactor with a failing test or an unresolved design decision noted in the
log) — do not present a broken feature as a selectable, ready-to-ship option
without that flag. Confirm test suite status (`python -m pytest`) as part of
this step, not just changelog text, since the log can describe something as
done while the tree currently disagrees.

Tell the user the file is there, ask them to check the boxes (`- [ ]` →
`- [x]`) and confirm when done. Then **read the file back** to see which boxes
are checked — do not rely on memory of what you wrote, the user may have
edited it.

This file is scratch/working state, not a deliverable: **delete it** once
Step 4 has finished and the user has confirmed the release (same moment
`send_out/` gets replaced with the real installer + release note). If the
user restarts a wrap-up before finishing an earlier one, the stale checklist
file being overwritten by Step 2 is expected and fine — no need to preserve
old ones.

## Step 3 — Build the new installer

Only after the user has told you which items are selected:

1. **Do not touch user data.** Nothing in this flow may write to
   `%LocalAppData%\VocabularyTrainer` or `%AppData%\VocabularyTrainer` on this
   machine or any target machine. The installer script
   (`install_tool/installer_main.py`) already preserves
   `%AppData%\VocabularyTrainer` (the workbook + collections) across a
   reinstall by design — confirm this is still true before relying on it,
   don't just assume no regression crept in.
2. If any selected item is not actually in a shippable state (failing tests,
   unresolved question per Step 2's flag), **stop and ask** rather than
   shipping it anyway or silently dropping it.
3. Run the full test suite (`python -m pytest`) and require it green before
   building. If it's red because of an unselected/unrelated item, that's a
   judgment call — surface it to the user rather than deciding alone.
4. Bump the version in `pyproject.toml` (the `[project] version` field) — pick
   the next patch/minor number consistent with the size of the change, and
   say what you picked and why.
5. Build via `install_tool/build_exe.py` (rebuilds the wheel from `src/` fresh
   every time, generates the icon, freezes with PyInstaller, self-checks the
   binary). Do not hand-edit `install_tool/installer_main.py`'s version
   placeholder directly — let the build script do the substitution.
6. Add a `change_log.md` entry for the wrap-up/release build itself (this is a
   real change per the always-on change-log steering rule), noting which
   checklist items were included in this release.

## Step 4 — Deliver to `send_out/`

1. **Replace the entire contents** of `send_out/` — delete whatever's
   currently there first (this folder holds only the current release
   candidate, never a history of old ones), then copy in the freshly built
   `.exe`.
2. Also copy a short release note into `send_out/` (plain `.txt` or `.md`) —
   what version, what's new (the checked items, in plain language for an end
   user, not the developer-facing changelog prose), and nothing else. This is
   what the user hands to their friend/testers alongside the installer.
3. Report back: what's in `send_out/` now, the version number, and a reminder
   that installing over an existing copy preserves their workbook (point at
   `install_tool/README.md` if they want the detail).

## After a successful wrap-up

Update `current_published_installation_package/` to match what was just
shipped — copy the new installer there too — **only after the user confirms
they're actually distributing this build**. Don't do it automatically as part
of Step 4; the baseline should represent what's really out in the world, not
just what was most recently built. If the user doesn't confirm, leave the
baseline as-is and just leave the new build in `send_out/`.
