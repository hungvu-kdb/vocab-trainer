# Vocabulary Trainer v3

A Windows desktop app for collecting and practising English vocabulary. An
always-on-top floating character captures words the moment you meet them, with
automatic dictionary lookup or a manual meaning you type yourself; a native Practice
window drills you on what you have collected. All data lives in one human-editable
`.xlsx` workbook you can open in Excel.

Refactored from v2, which — along with the unrelated v1 C#/.NET implementation — has
been archived to `../archive/` and frozen. This folder is the active implementation
and is self-contained: reference materials (mockups, artwork, requirements, specs)
live in `materials/`, and `PROJECT.md` is the consolidated current-state reference.

Packaged as **`vocab-v2`** (distinct from v2's own `vocabulary-trainer` package name)
specifically so the two can be installed side by side without one silently replacing
the other's editable install, and so the command to launch this version is unambiguous:
just `vocab-v2` in any cmd prompt once installed.

## Requirements

- Windows 10 (1809+) or Windows 11, x64
- Python 3.12 or newer (verified on 3.14)

## Install

For anyone who just wants to use the app, build and send the single-file
installer — see `install_tool/README.md`:

```cmd
python install_tool\build_exe.py
```

That produces `install_tool\Install-VocabularyTrainer.exe`, which installs
per-user with no admin rights and needs nothing else on the target machine.

For development, install the package in place. `python -m vocabulary_trainer`
fails with `No module named vocabulary_trainer` until you do, because the code
lives under `src/`.

```cmd
cd VocabularyTrainer.V3
python -m pip install -e ".[dev]"
```

## Run

```cmd
vocab-v2
```

This is the console script the install puts on your PATH — works from any directory,
in any cmd prompt, once installed. Equivalently:

```cmd
python -m vocabulary_trainer
```

(the module name stays `vocabulary_trainer` since that is the importable package under
`src/`; only the distribution name and the launch command changed to `vocab-v2`.)

### If you'd rather not install

Run it straight from the source tree by pointing Python at `src/`:

```cmd
cd VocabularyTrainer.V3
set PYTHONPATH=src
python -m vocabulary_trainer
```

### Nothing appears?

The app has no main window by design — it starts as a floating character plus a system
tray icon. Look for the character near the bottom-right of your primary screen, above the
taskbar, and for the tray icon in the notification area. If the widget was switched off in
a previous session, the tray icon is the only visible sign; click it for the menu.

On first launch the app creates its workbook at
`%AppData%\VocabularyTrainer\master.xlsx`, seeds a `General` collection, and places the
character near the bottom-right of your screen. Click it for the menu; drag it anywhere.

## Test

```cmd
python -m pytest
```

With coverage:

```cmd
python -m pytest --cov=vocabulary_trainer --cov-report=term-missing
```

**757 tests, 89% line coverage.** The `ui/` package is excluded from coverage: those
modules need live Windows compositing and installed speech voices, so they are verified
manually. Business logic is deliberately kept out of them, which is what makes the rest
exercisable without a display.

> **Note on adding tests**: by explicit project decision, **new unit tests are not
> written unless specifically requested**. The existing suite is kept and should keep
> passing — run it after changes — but there is no coverage quota to satisfy, and
> tests are not added automatically alongside new code. See `PROJECT.md` §4.2.

## Architecture

Layered, with dependencies pointing one way only:

```
ui            Qt widgets (floating overlay) + QWebEngineView (Practice, Settings)
services      orchestration; the only layer the UI may call
data          Excel workbook, preferences, practice history
integrations  dictionary/translation clients, TTS, audio, OS startup
domain        pure logic: identity, lookup priority, shuffle, scoring
```

Nothing below `ui` imports anything from it. That is why the whole service layer can be
exercised in a process with no Qt application object, and why the two UI technologies
cannot grow divergent copies of the same behaviour.

### Why two UI technologies

The floating widget needs a frameless, per-pixel-translucent, always-on-top window so
the character's edges blend with the desktop instead of sitting in a grey box. That is
Qt's job and an embedded web view cannot do it cleanly.

Practice and Settings are document-like, layout-heavy screens that already existed as
HTML mockups. Rendering that markup directly in a `QWebEngineView` gets close visual
fidelity without hand-building every card, and removes any translation step between
design and implementation.

**No web server, no browser process, no `localhost`.** The web-rendered windows load
local files inside the app's own window. The JavaScript layer captures input and renders
state; every decision is a Python service call.

### Design tokens

Colours, radii, shadows and the font stack live once in
`ui/theme/tokens.py`, transcribed from `mockup/styles.css`. The Qt stylesheet and the
web layer's CSS variables are both generated from it, so the two surfaces cannot drift
apart.

## Data

### Master workbook

Two sheets. Safe to edit by hand in Excel.

**`Words`** — `Words`, `Type`, `Meaning`, `Example`, `Name of collection`, `Date`
**`Collections`** — `Name`, `Created date`

Every write is atomic: the new content goes to a temporary file beside the target, then
swaps into place, so a crash mid-write leaves either the complete old file or the
complete new one. Concurrent writes are serialised. If you have the workbook open in
Excel when the app tries to write, your pending change is held in memory and you are
offered a retry rather than losing it.

Header rows are validated on open and repaired if you have renamed a column, with the
change reported. Malformed cells are coerced rather than dropping rows — a word with a
broken date is still a word you collected. Only a blank word discards a row.

External edits are noticed: the app watches the file and reloads when it settles.

### App data

Under `%AppData%\VocabularyTrainer\`:

- `preferences.json` — widget position, visibility and size, character, TTS voice,
  master file path, Merriam-Webster key, start-with-Windows. Read with
  `utf-8-sig`, so a byte-order mark left by a Windows editor does not discard the
  file
- `practice-history.json` — session results (score, words practiced, penalties,
  elapsed time), capped at 500 entries; read back by the app for statistics
- `practice-log.xlsx` — a separate, spreadsheet-native session log (user-requested),
  one row per session, meant to be opened directly in Excel. Write-only from the
  app's side — nothing reads it back. Columns: Date, Start Time, End Time
  (`hh:mm:ss`), Collection (comma-joined), Penalty, Finish (`True`/`False` — only
  `True` if every word was mastered before the session ended), and Word with
  penalty (`word_count|word_count`, e.g. `hello_2|goodbye_3`, blank if nothing was
  missed)

Practice results are kept here rather than in the master workbook, so the workbook
stays a clean word list.

## Dictionary lookup

All available sources are queried **concurrently** on every lookup, and the
highest-priority result that came back is stored:

1. **Local AI model (Ollama)** — *off by default*, and skipped entirely unless you
   switch it on and pick a model. See below.
2. **Bundled offline dictionary** — a WordNet-derived JSON file shipped with the app
   (`assets/dictionary/wordnet-2025-dictionary.json`, ~127k entries). No network
   involved, so it works even on a machine where outbound HTTP to the two web
   dictionaries below is blocked or unreliable. Ranked above them for exactly that
   reason.
3. **Free Dictionary API** — keyless, always available
4. **Merriam-Webster** — needs a free API key (Settings → General); skipped without one
5. **Google Translate** — EN→VI fallback; the translation becomes the meaning, with no
   example

If they all fail — the offline dictionary has no entry and the network ones fail or
find nothing — the word still saves with its type, and you can fill in the meaning
later in Excel. Lookup never blocks saving, and the widget stays responsive
throughout.

### Local AI meanings with Ollama (optional)

Instead of looking a word up, the app can ask a language model running **on your own
computer** to write the English meaning and an example sentence. Nothing leaves the
machine: the request goes to `127.0.0.1:11434` and no other address is accepted.

**Ollama is not installed by this app and is not part of the installer.** It is a
separate program you install yourself; without it the feature simply stays off and
everything behaves exactly as it did before.

Setting it up:

1. Install Ollama from [ollama.com](https://ollama.com/download).
2. Pull a model. Anything works; smaller is faster:
   ```cmd
   ollama pull llama3.2
   ```
3. Make sure Ollama is running (`ollama serve`, or its tray app).
4. In Vocabulary Trainer: **Settings → General → Local AI model**, switch it on and
   pick a model from the list.

Only models **already installed** in Ollama are listed, so the dropdown can never
offer one that would fail on first use. Run `ollama pull` for a new one, then press
**Refresh**. If the list is empty the app says which of the two reasons applies —
Ollama not detected, or running with no models pulled.

Notes worth knowing:

- **It ranks above the dictionaries when on.** Switching it on is taken as a
  statement that you prefer its phrasing. If the model declines a word — it is asked
  to return nothing when the word is not used as the part of speech you chose — the
  dictionaries answer instead, so you never get a wrong-part-of-speech definition
  ranked first.
- **It is slower than a dictionary.** A small model takes roughly 5–15 seconds on
  CPU, so lookups are given up to 60 seconds to finish while it is switched on
  (8 seconds otherwise). That is a ceiling, not a wait: a lookup that resolves in
  three seconds still takes three seconds. And it costs you nothing either way — the
  word is saved immediately and the row is patched when the meaning arrives, so you
  can close the card and carry on.
- **A model you selected and later deleted is reported**, not silently ignored — the
  Settings tab tells you to pick another rather than quietly falling back.
- Meanings are generated, so they are occasionally loose. The status line says
  "Generated by local AI model" so you always know which source wrote what.

The Collect card also offers a **Type it myself** toggle: switching to it cancels any
lookup for the current word and swaps the read-only result panel for editable Meaning
and Example fields, so the user's own definition is never overwritten by a late
dictionary response.

### Collecting several words at once

Switch the **One word / Several** toggle above the input and type words separated by
commas:

```
serene, mountain, give up
```

Each word is trimmed, its internal spacing collapsed, and **lowercased**, then saved
with the type you picked and looked up independently — all lookups run at once, so ten
words take about as long as one. A hint under the field shows exactly what your commas
parsed into before you save, which is worth glancing at: repeats collapse silently and
capitals are dropped.

Words already in the collection are **skipped** rather than prompting for each one, and
the result line says which ("Saved 3, skipped 2 already there"). The card stays open so
you can read that.

Two things to know: proper nouns lose their capitals in this mode, and "Type it myself"
is unavailable — one typed meaning cannot be correct for several different words.

### The character tells you how it went

When a lookup finishes, a small speech bubble appears next to the character: **"I found
it!"** or **"I couldn't find it"**, with the word underneath. It never takes focus,
disappears on its own after a few seconds, and closes if you click it.

This matters because the Collect card closes as soon as you save, so most lookups
finish after it is gone — the bubble is how you find out whether a word ended up with a
meaning without opening the workbook. In a batch each word reports separately, so you
learn exactly which ones the dictionaries and the model could not handle.

In Auto mode you can **save straight away without waiting** — the row is written
immediately and the lookup keeps running in the background after the card closes,
filling in the Meaning and Example as soon as it resolves. Only discarding the entry
(closing without saving) abandons the lookup.

## Project layout

```
src/vocabulary_trainer/
├── domain/        pure logic, no I/O
├── data/          workbook, preferences, history, file watching
├── integrations/  lookup clients, TTS, audio, startup registration
├── services/      orchestration + composition root
├── ui/
│   ├── theme/     design tokens, generated Qt and web styling
│   ├── widget/    Qt overlay windows and popups
│   └── web/       QWebEngineView hosts, HTML/CSS/JS, bridges
└── assets/        character art, fonts, sounds
tests/             mirrors src
```

## Notes and limitations

- **Accessibility** is not a focus for this version. Standard keyboard behaviour from
  the toolkits is retained, but no additional keyboard navigation, screen-reader
  annotation, or contrast verification work was done. This was a recorded decision, not
  an oversight.
- **Crocodile character**: the code supports it, but only cat artwork ships. Drop
  `mini_ani_idle_crocodile.png` and `mini_ani_active_crocodile.png` into
  `assets/floating_widget/` and it appears in Settings. Until then it is listed as
  unavailable rather than silently rendering a cat.
- **Feedback sounds** fall back to Windows system sounds; no custom `.wav` files ship.
- The Google Translate endpoint is the keyless one its web client uses, which Google
  does not formally guarantee. If it stops working, lookups degrade to the dictionaries.
- **No pandas.** The design recorded "pandas for reading, openpyxl for writing", but the
  repository needs cell-level access across two sheets — to repair header rows in place,
  preserve columns you added yourself, and delete individual rows. A DataFrame round-trip
  cannot express that without rewriting whole sheets, which would defeat the point of
  keeping the workbook hand-editable. pandas ended up unused, so it is not a dependency;
  carrying it would mean a multi-minute build-from-source for no benefit.
- Dependency versions are declared as compatible ranges rather than exact pins.
  `pywin32` in particular publishes per-interpreter builds, so an exact pin fails to
  resolve on any Python version it does not target.
