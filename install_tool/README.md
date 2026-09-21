# Installer

Builds **`Install-VocabularyTrainer.exe`** — one file to send to someone who just
wants to run the app. They double-click it; nothing else needed.

## Rebuild

```cmd
python install_tool\build_exe.py
```

Rebuild after any source change: the app is baked into the .exe, so a stale
installer ships stale code. The build regenerates the wheel from `src/` every
time so that cannot happen silently, then checks the finished binary.

Build-time requirements (the recipient needs none of this):

```cmd
python -m pip install "pyinstaller>=6.10,<7" pillow
```

Pillow is optional — without it the .exe and its shortcuts fall back to default
icons, which is cosmetic only.

## What the recipient gets

- Per-user install to `%LocalAppData%\VocabularyTrainer`. **No admin rights**,
  nothing written outside their profile.
- Its own private Python environment, so the app cannot disturb any Python they
  use for their own work.
- Start Menu and desktop shortcuts carrying the character artwork as the icon.
  They point at `pythonw.exe`, not the `vocab-v2` console script, so no black
  console window sits on the taskbar while the app runs.
- An entry in Settings → Apps, and an `uninstall.cmd`.
- Python 3.12+ is used if present; otherwise the installer offers to fetch it
  from python.org and install it for that user only.

Uninstalling removes the app but **keeps** `%AppData%\VocabularyTrainer` — the
workbook, preferences and practice log. That is the user's data, so it is never
deleted without them choosing to.

They need an internet connection on first install: Qt and the other dependencies
(~150 MB) come from PyPI. Only the app itself is embedded in the .exe.

Windows SmartScreen will warn about an unrecognised publisher, since the binary
is unsigned. They click **More info → Run anyway**. Unavoidable without a
code-signing certificate.

## Files

| File | Role |
|---|---|
| `build_exe.py` | The build. Run this. |
| `installer_main.py` | The installer program, frozen into the .exe. Not run directly. |
| `Install-VocabularyTrainer.exe` | Generated output, ~19 MB. The file to send. |

## Three things that will bite you if you change the installer

All three were found by actually running it, and all three look like working
code:

- **A process search for `vocabulary_trainer` matches the searcher.** The
  detection query runs via PowerShell, whose own command line contains the
  search string, so it finds itself and reports a running app on a machine with
  nothing running — and the installer then refuses to proceed. Require
  `Name -like 'python*'` as well. The uninstaller had the same flaw, where it
  killed its own shell mid-run.
- **A venv's `pythonw.exe` is a redirector.** It re-execs the base interpreter,
  so the process really running the app lives *outside* the install folder while
  still holding the venv's DLLs open. Matching processes by path alone finds the
  redirector and misses the real one, so "close the running app before replacing
  it" silently does nothing and pip then fails on files in use.
- **The uninstaller must relocate before deleting.** It lives inside the folder
  it removes, and cmd reads a batch file as it executes — delete it mid-run and
  cmd aborts with "The system cannot find the path specified". It copies itself
  to `%TEMP%` and hands over, keyed off its own location so running it in place
  by hand still takes the safe path.

## Why Python, not PowerShell

An earlier version of this installer was a self-extracting `.cmd` wrapping a
PowerShell script. Three of its bugs traced to PowerShell 5.1 specifically:

- It mangles double quotes when rebuilding a native command line, so a
  `python -c "..."` probe returned nothing and every interpreter on the machine
  looked absent.
- Under `$ErrorActionPreference = 'Stop'`, anything a native command writes to
  stderr becomes a terminating error. pip uses stderr for routine notices, so a
  healthy install aborted on a warning.
- Pipe characters inside a quoted `-Command` argument are still interpreted by
  cmd, which broke the uninstaller's process cleanup.

`subprocess` takes an argument list, and an exit code is the only failure
signal. PyInstaller also needs a real program to freeze, so the rewrite was
required for the `.exe` regardless.
