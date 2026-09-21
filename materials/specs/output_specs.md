# Vocabulary Trainer — Output Specification

> This is the living, consolidated specification for the Windows vocabulary trainer app.
>
> **Note on this file's history**: it was removed from the workspace externally partway
> through the v2 AI-DLC workflow. It has been reconstructed here from its own prior
> content plus every product decision made during that workflow, because
> `.kiro/steering/product-decisions.md` requires it to be kept current. The detailed v2
> artifacts it summarises live in `aidlc-docs/`:
>
> - `aidlc-docs/inception/requirements/requirements.md` — 74 numbered requirements across
>   8 epics, with full traceability
> - `aidlc-docs/inception/user-stories/stories.md` — 42 user stories, each with a user
>   flow
> - `aidlc-docs/inception/application-design/` — components, methods, services,
>   dependencies
> - `.kiro/specs/vocabulary-trainer-v2/tasks.md` — implementation task list
>
> Where an earlier document conflicts with this one, **this file wins**.

## 1. Product Overview

A Windows desktop application that helps a user build and practice an English vocabulary
list. It has two pillars:

- **Learn** — a lightweight, always-on-top floating widget ("mini-ani") for capturing new
  words the moment the user encounters them, with automatic dictionary lookup.
- **Practice** — a native writing drill window that tests recall of previously collected
  words, organized by collection, with scoring and audio feedback.

All vocabulary data lives in a single, human-editable **Excel master file**.

- **Platform**: Windows only (desktop). Windows 10 (1809+) or Windows 11, x64.
- **Architecture**: a single native Windows application. The floating widget, the Practice
  screen, and Settings are all native windows/overlays within the same app — **no web
  server or browser is involved anywhere** (explicitly decided after an earlier draft
  proposed a localhost-served Practice website; that was reverted in favor of a native
  Practice window, merged alongside Settings).
- **Primary data store**: a single `.xlsx` "master file", editable both by the app and
  manually by the user in Excel.

### 1.1 Implementation Stack (decided during the v2 workflow)

Python 3.12+ with a **hybrid UI**:

- The **floating widget and its popups** are **Qt widgets (PySide6)**, because they need a
  frameless, per-pixel-translucent, always-on-top window — the one thing an embedded web
  view cannot do cleanly.
- **Practice and Settings** are rendered by **`QWebEngineView`** (Qt's embedded Chromium)
  loading local HTML/CSS derived from `mockup/`, bridged to Python by `QWebChannel`. This
  keeps the architectural constraint above intact: content loads from local files inside
  the app's own window — no HTTP server, no browser process, no `localhost`.
- The Excel workbook is accessed with **openpyxl**.
  > **Decision history**: an earlier draft specified pandas for reading with openpyxl
  > writing. **Revised during construction** — the repository needs cell-level access
  > across both sheets to repair header rows in place, preserve columns the user added,
  > and delete individual rows. A DataFrame round-trip cannot express that without
  > rewriting whole sheets, which is exactly what would endanger a hand-editable
  > workbook. pandas is not a dependency.

> **Decision history**: an earlier v2 draft specified WebView2 via `pywebview` for these
> windows. That was **reverted during design** — `pywebview` and Qt each own a blocking
> main event loop and cannot coexist in one process without fragile interleaving that
> would compromise the widget responsiveness the product depends on. `QWebEngineView`
> preserves the same hybrid split under a single event loop and removes the external
> WebView2 runtime prerequisite.

**Code location**: v2 lives in `VocabularyTrainer.V2/`. The earlier `VocabularyTrainer/`
implementation is frozen, unrelated, and was not used as a reference.

**Layering** (dependencies point one way only): `ui` → `services` → `data` /
`integrations` → `domain`. Nothing below `ui` imports from it, which is what makes the
entire service layer testable without a display and prevents the two UI technologies from
growing divergent copies of the same behavior.

## 2. Data Model — Master File

### 2.1 Word Entry (one row per word, `Words` sheet)

| Column | Type | Required | Description |
|---|---|---|---|
| Words | Text | Yes | The word or phrase being learned. Natural key together with Collection. |
| Type | Enum (Text) | Yes | Part of speech: noun, verb, adjective, adverb, phrase. |
| Meaning | Text | No | Definition from the lookup pipeline; blank if all sources failed. |
| Example | Text | No | Example sentence; blank when the meaning came from translation. |
| Name of collection | Text | Yes | Name of the Collection this word belongs to. |
| Date | Date | Yes | Date collected (or last replaced, per duplicate-resolution rules). |

- Word matching is case-insensitive, whitespace-trimmed, and collapses internal
  whitespace runs (so `"give  up"` and `"give up"` are the same phrase). Punctuation is
  **not** normalized — `"well"` and `"well,"` remain distinct.
- `(Words, Name of collection)` is the natural key used to detect duplicates.

### 2.2 Collection (`Collections` sheet)

| Field | Type | Required | Notes |
|---|---|---|---|
| Name | Text, unique | Yes | Display name and the value stored in "Name of collection". |
| Created date | Date | Yes (system-set) | Set on creation; drives the sort modes in Section 4.1. |

- **Create**: via Settings, or inline from the Collect widget (Section 3.1).
- **Rename**: updates "Name of collection" on all belonging word rows. The collection row
  and every word row change in **one atomic write**, so a partial rename is impossible.
  Recasing a collection's own name (e.g. `ielts` → `IELTS`) is permitted.
- **Delete**: cascades to all belonging word rows, in one atomic write. Requires an
  explicit confirmation dialog stating the exact word count. Deleting the last collection
  re-seeds `General`.
- A default collection **General** exists out of the box.

### 2.3 Application Data

Under `%AppData%\VocabularyTrainer\`:

- `preferences.json` — widget position/visibility, character, TTS voice, master file path,
  Merriam-Webster API key, start-with-Windows, last-used practice settings.
- `practice-history.json` — session results, capped at 500 entries.

## 3. Feature: Learn → Collect New Vocabulary

### 3.1 Entry Point & Form

- Initiated by clicking the floating widget and choosing **Collect** (Section 5), or from
  the system tray menu.
- Minimal UI: a text input for Word/phrase, Type selected via single-select chips (noun,
  verb, adjective, adverb, phrase), and a Collection picker.
- **Creating a collection inline**: the picker includes "+ New collection…", which swaps
  the dropdown for a name field with Create/Cancel. Names are validated for emptiness and
  case-insensitive uniqueness. The new collection is immediately selected.
- **No clipboard capture** — entry is manual (decided in the v2 workflow, to keep scope
  tight).
- **Meaning source toggle — Auto-lookup vs Manual** (decided in the v3 workflow): the
  Collect card carries an **Auto-lookup / Type it myself** switch, defaulting to
  Auto-lookup. Switching to **Manual** cancels any in-flight lookup for the current
  word and replaces the read-only lookup result panel with two editable fields —
  **Your meaning** and **Your example** (optional) — typed by the user instead of
  fetched. Switching back to Auto-lookup re-starts the lookup for the word/type
  currently entered.
  - A word saved in Manual mode stores exactly what the user typed (trimmed; blank
    meaning is permitted and behaves like an unresolved Auto-lookup — the word saves
    with Type only).
  - **The lookup pipeline is never queried while Manual is selected**, and a lookup
    that was already running when the user switched is abandoned rather than
    patching the row later. This is deliberate: without it, a slow dictionary
    response could arrive after save and silently overwrite a meaning the user
    explicitly chose to write themselves — a race that does not exist for
    Auto-lookup today.
  - Duplicate detection and resolution (Section 3.3) are unaffected by which mode
    produced the incoming word; the natural key and the three resolution outcomes
    are identical either way.

### 3.2 Lookup Pipeline

> **Decision history**: originally specced against Cambridge Dictionary via HTML scraping,
> then reverted to a structured-API pipeline. The v2 workflow made a further change:
> the pipeline was a *sequential* fallback chain stopping at the first hit, and is now
> **concurrent** — all sources are queried on every lookup, with priority deciding what
> gets stored. The v3 workflow added a fourth source: a **bundled offline dictionary**,
> because the two web dictionaries can both fail identically on a machine where
> outbound HTTP to their APIs is blocked or times out — which made auto-meaning
> silently return nothing with no way to recover short of network access changing.
>
> The mockups' status text still reads "Cambridge Dictionary". That copy is stale and is
> deliberately not reproduced in the implementation.

WHEN the user enters a Word + Type:

1. The app queries **all four sources concurrently** in the background, under one
   bounded deadline: a **bundled offline dictionary** (WordNet-derived JSON shipped
   with the app, no network involved), the **Free Dictionary API** (keyless), the
   **Merriam-Webster API**, and **Google Translate** (EN→VI).
2. For each dictionary source, the definition whose part of speech matches the selected
   Type is preferred, falling back to the first available definition.
3. WHEN more than one source answers, the highest-priority result is stored:
   **bundled offline dictionary > Free Dictionary > Merriam-Webster > Google
   Translate**. The offline dictionary ranks highest because it cannot fail for
   network reasons the way the other two dictionaries can. A source that responded
   but returned nothing usable counts as not having answered.
4. WHEN the stored result came from Translate, Meaning holds the Vietnamese translation
   and Example is blank.
5. WHEN all sources fail (offline dictionary has no entry and both web dictionaries
   fail or find nothing), the word is still saved with its Type; Meaning and Example
   stay blank.
6. The status line names the actual source on success. Lookup never blocks saving, and the
   widget stays responsive throughout.
7. **Merriam-Webster requires a free API key**, configurable in Settings. Without a key
   that source is skipped and the remaining sources are used.

### 3.3 Duplicate Detection & Resolution

WHEN the submitted word already exists (same Word + Collection):

1. A popup appears inside the floating widget showing the existing entry's **Collection**
   and **Date**.
2. Three actions: **Keep old** (nothing changes), **Replace** (overwrites
   Meaning/Example/Date on the existing row, preserving Word and Collection), and
   **Delete both**.
3. **Delete both** removes the existing row **and** discards the new submission — neither
   entry survives. The label says "Delete both" precisely so that is unambiguous.
4. Dismissing the popup without a choice behaves exactly as **Keep old**, and the popup
   states this.
5. Exactly one of {no change, row updated, row removed} occurs; the incoming word is never
   inserted as a separate row by any action.

## 4. Feature: Practice → Writing Mode (Native Window)

> **Decision history**: Practice was originally a website served by a local HTTP server.
> **Reverted** — it is a native app window. No local server, no browser, no `localhost`.

### 4.1 Session Setup

- **Collection multi-select**: checkbox list with each collection's word count and creation
  date.
- **Search**: filters by case-insensitive substring on name, live. Shows "No collections
  match your search." on zero results.
- **Sort**: Newest first (default), Oldest first, Name (A–Z). Operates independently of the
  search filter and of which collections are checked — a checked collection filtered out
  of view stays checked and still counts toward the pool. Sort resets to Newest first each
  time the window opens.
- **Required correct writes**: stepper, **default 3, range 1–10**, disabled at the bounds.
- The combined pool size is shown before starting.
- IF the checked collections total zero words, Start is disabled with an explanation.

### 4.2 Drill Loop

1. Words are presented in **random shuffle order**.
2. For each word the app shows its **Type** and **Meaning** and prompts the user to type
   the Word. The Word's spelling is never shown before submission. A word with no recorded
   meaning is presented with an explicit note rather than a blank prompt.
3. **Progress** is measured as attempts made against `pool size × required writes`,
   computed once at session start so the bar only ever advances.
4. WHEN the user submits an answer:
   - **Correct** (case-insensitive, trimmed, whitespace-collapsed match):
     - Plays a success sound and reads the word aloud via system text-to-speech.
     - Increments the word's consecutive-correct counter, shown as mastery dots.
     - At the required count the word is **mastered** and leaves the pool; otherwise it is
       reinserted at a position other than the immediate next draw.
   - **Incorrect**:
     - Applies **1 penalty**; live score is `total correct attempts − total penalties`,
       displayed throughout and **not clamped at zero**.
     - The word's mastery progress is **not reset** — only the penalty accumulates.
     - The correct spelling is revealed, and the drill **waits for an explicit Next**
       before advancing, so the user can read it.
     - An empty submission is ignored rather than penalized.

### 4.3 Session Summary

- Shown when all words are mastered, when the user clicks **End session**, or when the
  Practice window is closed mid-session (all three routes produce the summary).
- Displays final score, words practiced, total penalties, and time taken.
- Actions: **Back to setup** (restoring the previous selections) and **Practice again**
  (same collections and threshold, freshly shuffled).
- Results are appended to `practice-history.json`. **Nothing is written into the master
  workbook** — it stays a clean word list.
- **Separate practice log workbook** (decided in the v3 workflow, user-requested): each
  session ending also appends one row to a second, dedicated Excel file
  `%AppData%\VocabularyTrainer\practice-log.xlsx`, meant to be opened directly in Excel.
  Distinct from `practice-history.json` — that JSON store is the capped, score-focused
  figures the in-app summary reads back; this workbook is a spreadsheet-native record
  aimed at "when did I practice, on what, and which words gave me trouble." Columns:
  - **Date** — the session's start date.
  - **Start Time** / **End Time** — `hh:mm:ss` Excel time cells (sortable, not text).
  - **Collection** — the chosen collections for that session, comma-joined (e.g.
    `"IELTS, Daily Reading"`).
  - **Penalty** — total penalties accumulated that session.
  - **Finish** — `True` only if the pool emptied naturally (every word mastered) before
    the session ended; ending early via **End session** or by closing the window
    mid-session logs `False`, even if some words were mastered.
  - **Word with penalty** — `'|'.join(f"{word}_{count}")` for every word missed at
    least once, e.g. `hello_2|goodbye_3`; blank for a session with zero misses.
  - This file is write-only from the app's perspective — nothing else in the app reads
    it back, and it is never the master workbook.

## 5. Component: Floating Widget ("mini-ani")

- A small animated character in a frameless, per-pixel-translucent, always-on-top window,
  with no taskbar entry and never stealing focus.
- Character is a **cat or a crocodile**, selectable at runtime from Settings and applied
  live. Only cat artwork currently ships; the crocodile is listed as unavailable rather
  than silently rendering a cat.
- Draggable anywhere; position persists across restarts and is clamped back on-screen if a
  monitor is removed or the resolution changes.
- **Click** opens a popup menu: **Collect new word**, **Practice**, **Settings**, a
  quick widget on/off toggle, and **Quit** (decided in the v3 workflow — ends the
  application directly, the same action already available from the tray icon's menu,
  so quitting never requires hunting for the notification area). The menu flips to
  the widget's other side near a screen edge.
- The character switches between idle and active poses depending on whether a popup it
  owns is open.
- **System tray icon**: always present while the app runs, carrying the same menu. The
  widget is only permitted to hide itself if a tray icon exists, so the app can never be
  running yet unreachable.

## 6. Component: Settings (Native Window)

Two-pane layout — left sidebar nav, right content pane — with **five tabs**.

> **Decision history**: the mockups draw five nav items but design only two panes. The v2
> workflow decided to ship all five, which moves the widget toggle and character picker
> out of General into **Widget**, and the TTS voice into **Audio**, so each pane holds what
> its label promises.

### 6.1 General
- **Master file** path with a Browse dialog. An unreadable file is rejected and the
  previous path stays in effect; naming a non-existent file creates a correctly structured
  workbook there.
- **Start with Windows** toggle, **off by default**. Reports its achieved state, so a
  failed registration reverts the switch rather than displaying a lie.
- **Merriam-Webster API key**. Stored locally, never logged or read back.

### 6.2 Collections (CRUD)
- List with word counts, plus create, rename, and delete.
- **Delete** shows a modal confirmation naming the exact number of words to be permanently
  deleted, with the count repeated on the confirm button.
- **Preview** (decided in the v3 workflow): each collection row carries a Preview action
  that opens a read-only modal showing every word in that collection as a table, columns
  **Word, Type, Meaning, Example, Date**. A blank Meaning or Example (all lookup sources
  failed, or a manual-meaning entry left it blank) renders as "—" rather than an empty
  cell. The table is read-only — editing a row still requires opening the workbook in
  Excel, per Section 10's existing scope boundary.

### 6.3 Widget
- **Show widget** toggle (kept in sync with the widget's own menu).
- **Character** dropdown, applied live.

### 6.4 Audio
- **Voice** dropdown listing installed Windows speech voices, with a preview. A machine
  with no voices is explained rather than shown as broken — practice plays its success
  sound without speech.

### 6.5 About
- Application name, version, and the master file location in use.

## 7. Visual Design

- **Typeface**: Google Sans (Regular/Medium/Bold), bundled as local TTF files rather than
  loaded from a CDN, so the UI renders correctly with no internet connection. Segoe UI is
  the fallback.
- **Style**: light theme, rounded cards (10/14/20px radii), soft shadows, a blue primary
  accent, with soft-tinted success/danger/warning colors.
- **Single token source**: the full token set from `mockup/styles.css` lives once in
  `ui/theme/tokens.py`. The Qt stylesheet and the web layer's CSS variables are both
  **generated** from it, so the two surfaces cannot drift apart.
- **Reference implementation**: the mockups in `mockup/` are the visual source of truth.
  Where mockup *copy* conflicts with these requirements — notably the stale "Cambridge
  Dictionary" status text and the leftover "delegated entirely to the local website"
  framing — these requirements win.

## 8. Non-Functional Requirements

1. **Offline resilience**: only the two web dictionaries and translation need the
   network; the bundled offline dictionary and everything else work fully offline.
   Auto-meaning degrades per Section 3.2 step 5 only if the offline dictionary also
   has no entry for the word.
2. **Data safety**: every write to the master file is **atomic** — written to a temporary
   file beside the target, then swapped, so the file always holds either the complete old
   or complete new content. Temp files are cleaned up on success and failure, and orphans
   from an interrupted run are removed at next launch.
3. **Write serialization**: no two mutating operations write concurrently.
4. **Locked file**: WHEN the workbook is open in Excel and a write is attempted, the
   pending change is held in memory, the user is told to close Excel, and a **Retry** is
   offered. Nothing is partially applied.
5. **Header repair**: header rows are validated on open. An altered or missing header is
   **auto-repaired positionally** (preserving the data beneath it) and the user is told
   exactly what changed. Extra user-added columns are preserved. A file that is not a
   readable workbook is reported as such, with no repair attempted.
6. **External edits**: the app watches the master file and reloads when it settles. An
   in-flight practice session keeps its original pool, and unsaved Collect input is
   preserved.
7. **Responsiveness**: no network or file I/O on the UI thread; the widget stays
   draggable and clickable during lookups.
8. **Persistence of preferences**: widget state/position/character, TTS voice, master file
   path, and API key persist across restarts.
9. **Destructive-action safety**: collection deletion and duplicate "Delete both" both
   require explicit confirmation.
10. **Security**: the API key is stored only in the local preferences file, never logged or
    surfaced in errors. Outbound requests go only to the three network lookup endpoints
    and carry only the word being looked up. The bundled offline dictionary makes no
    outbound request at all.
11. **Testability**: business logic is independent of the UI layer. The service layer is
    exercised with no Qt application object in the process. ~~Minimum 80% line coverage on
    new business logic~~ — the coverage minimum was **withdrawn by explicit user
    instruction in v3**: new unit tests are not written unless the user asks for them. The
    existing suite is kept and must keep passing; the one-way layering above is retained
    because it keeps the code reviewable and directly exercisable, not as a testing quota.
    See `.kiro/steering/product-decisions.md`.
12. **Accessibility**: **not a focus for v2.** Toolkit keyboard behavior is retained, but
    no additional keyboard navigation, screen-reader annotation, or contrast verification
    work was done. A deliberate, recorded scope reduction.

## 9. Resolved Questions

All seven previously open questions are now closed.

| Question | Resolution |
|---|---|
| Default master file path | `%AppData%\VocabularyTrainer\master.xlsx`, auto-created, configurable in Settings |
| Master file locked in Excel | Clear message, change held in memory, Retry offered |
| Altered header row | Auto-repair positionally, proceed, report what changed |
| External edits while running | Watch the file and reload once writes settle |
| Character selectable at runtime | Yes, from Settings → Widget, applied live |
| Practice results in master file | No — separate JSON store under `%AppData%` |
| Duplicate "Delete" and the new submission | Neither survives; action relabelled "Delete both" |

## 10. Out of Scope

- Cloud sync or multi-device support.
- Languages beyond English (word) and Vietnamese (translation fallback).
- macOS, Linux, or mobile.
- Spaced-repetition scheduling — Practice is manual collection selection.
- A web-based or browser-hosted Practice mode (explicitly reverted — see Section 4).
- Accessibility work beyond toolkit defaults (Section 8.12).
- Editing existing word rows from within the app — the workbook is edited in Excel for
  that.
- Clipboard or hotkey capture of words (Section 3.1).
