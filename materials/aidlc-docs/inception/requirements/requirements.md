# Requirements — Vocabulary Trainer v2

## Intent Analysis

| Aspect | Assessment |
|---|---|
| **User Request** | Rebuild the Vocabulary Trainer as a v2, fresh from `specs/output_specs.md` and the `mockup/` UI reference, with requirements restructured as Epic -> User Story (each story carrying an explicit user flow) and UI design detail folded in from the mockups. |
| **Request Type** | New Project (greenfield v2 alongside a frozen v1) |
| **Scope Estimate** | System-wide — a complete desktop application |
| **Complexity Estimate** | Complex — multiple windows, two UI technologies, external API integration, file-based persistence with concurrency and integrity concerns |
| **Requirements Depth** | Comprehensive |

### Scope Boundaries

**In scope**: a new, self-contained Windows desktop application at `VocabularyTrainer.V2/`,
built only from `specs/output_specs.md` (product behavior) and `mockup/` (visual design).

**Explicitly excluded as reference material**, per user instruction:
- `VocabularyTrainer/` — the v1 .NET/WPF implementation. Frozen, untouched, not consulted.
- `.kiro/specs/vocabulary-trainer/` — v1 requirements and design documents.
- `VastWords/` — an unrelated Swift/macOS application in the workspace.
- `.gitignore/` — excluded by workspace steering rule.

---

## Technology Decisions

These were open because v2 carries no implementation reference. Resolved during Requirements
Analysis (see `requirement-verification-questions.md` Q1–Q3 and
`requirements-clarification-questions.md` CQ3–CQ4).

| Decision | Choice | Rationale |
|---|---|---|
| Language / runtime | Python 3.12+ | User-specified backend language |
| Widget UI | PySide6 (Qt) | Frameless, per-pixel-translucent, always-on-top windows are first-class in Qt; needed so the character PNG renders with soft edges over the desktop rather than a grey box |
| Practice + Settings UI | `QWebEngineView` (Qt's embedded Chromium) with a `QWebChannel` Python bridge | Lets the `mockup/` HTML/CSS become the UI almost verbatim, which is what strict visual fidelity (Q21) demands. Local files only — no HTTP server, no browser process. **Revised during Application Design**: originally specified as WebView2 via `pywebview`, which was found to be unworkable because `pywebview` and Qt each own a blocking main event loop and cannot both run in one process without fragile interleaving that would compromise widget responsiveness (FR-1.9). `QWebEngineView` keeps the same hybrid split under a single Qt event loop |
| Excel access | **openpyxl only** | **Revised during construction.** Requirements Analysis recorded "pandas for reading/filtering plus openpyxl for writing" (CQ3 = B). Implementation showed pandas was never needed: the repository requires cell-level access across two sheets to repair header rows in place (FR-8.4), preserve user-added columns, and delete individual rows — none of which a DataFrame round-trip expresses without rewriting whole sheets, which is precisely what would endanger a hand-editable workbook. pandas ended up imported nowhere, so declaring it would add a heavy build-from-source dependency for no benefit |
| Project location | `VocabularyTrainer.V2/` | Sibling to the frozen v1 |
| Practice history store | JSON under `%AppData%\VocabularyTrainer\` | Keeps the master workbook a clean word list |

**Architectural constraint (unchanged from spec §1)**: this is a single native Windows
application. Rendering Practice and Settings inside an embedded `QWebEngineView` control does **not**
introduce a web server, a browser process, or any `localhost` traffic — content is loaded from
local files (`qrc:` / `file:` URLs) within the app's own window. The spec's "no web server or browser
is involved" decision holds.

### Extension Configuration

| Extension | Enabled | Note |
|---|---|---|
| Security Baseline | No | Personal-use desktop app. Secret-handling hygiene for the API key is still required — see NFR-SEC-01 |
| Property-Based Testing | No | Standard unit tests apply; unit testing itself remains mandatory |

---

## Epic Map

Functional requirements are grouped into seven epics. The User Stories stage expands each into
user stories with explicit user flows.

| Epic | Title | Requirement IDs |
|---|---|---|
| **E1** | Floating Widget & App Presence | FR-1.x |
| **E2** | Collect a Word | FR-2.x |
| **E3** | Dictionary Lookup & Enrichment | FR-3.x |
| **E4** | Duplicate Detection & Resolution | FR-4.x |
| **E5** | Practice — Session Setup | FR-5.x |
| **E6** | Practice — Drill & Summary | FR-6.x |
| **E7** | Settings & Collection Management | FR-7.x |
| **E8** | Master File Persistence & Integrity | FR-8.x |

---

## Data Model

### Word Entry — `Words` sheet, one row per word

| Column | Type | Required | Description |
|---|---|---|---|
| Words | Text | Yes | The word or phrase being learned |
| Type | Text (enum) | Yes | Part of speech: noun, verb, adjective, adverb, phrase |
| Meaning | Text | No | Definition from the lookup pipeline; blank if all sources failed |
| Example | Text | No | Example sentence; blank when the meaning came from translation |
| Name of collection | Text | Yes | The Collection this word belongs to |
| Date | Date | Yes | Date collected, or date last replaced per FR-4.4 |

### Collection — `Collections` sheet

| Column | Type | Required | Description |
|---|---|---|---|
| Name | Text, unique | Yes | Display name; also the value stored in "Name of collection" |
| Created date | Date | Yes (system-set) | Set on creation; drives the sort modes in FR-5.4 |

### Derived definitions

- **Natural key**: `(Words, Name of collection)`, compared case-insensitively with surrounding
  whitespace trimmed. Two entries with the same natural key are duplicates.
- **Session score**: `total correct attempts − total penalties`.
- **Mastered**: a word whose consecutive-correct count has reached the session's
  Required Correct Writes value.

---

## E1 — Floating Widget & App Presence

**FR-1.1** The widget SHALL render as a frameless, always-on-top overlay window with per-pixel
transparency, sized to roughly 92px wide per `mockup/styles.css` `.mini-ani-widget`, showing no
title bar and no taskbar entry.

**FR-1.2** The widget SHALL display an idle character image when at rest and an active character
image while a menu or popup it owns is open, using the assets in `asset/floating_widget/`.

**FR-1.3** WHEN the user presses and drags the widget, THEN it SHALL follow the cursor
continuously, and on release its new position SHALL be persisted.

**FR-1.4** WHEN the application starts, THEN the widget SHALL appear at its last persisted
position; on first run it SHALL appear near the bottom-right of the primary display, above the
taskbar.

**FR-1.5** WHEN the user clicks the widget, THEN a popup menu SHALL open anchored beside it,
containing: **Collect new word**, **Practice**, a divider, **Settings**, a **Widget on**
toggle, a divider, and **Quit** — matching `mockup/widget-menu.html`.

**FR-1.6** WHEN the user switches the widget toggle off (from the widget menu or Settings), THEN
the widget SHALL hide, and this SHALL persist across restarts.

**FR-1.7** The application SHALL maintain a system tray icon at all times, whose context menu
offers the same entries as the widget menu, so the app remains reachable while the widget is
hidden.

**FR-1.8** The application SHALL offer a "Start with Windows" toggle in Settings, **off by
default**, which registers or removes a per-user startup entry when changed.

**FR-1.9** The widget SHALL remain responsive to drag and click while background dictionary
lookups are in progress.

> **Adds to spec §5 (v3 workflow).** The widget menu gains a direct Quit action, so ending
> the application never requires finding the tray icon.

**FR-1.10** The widget menu SHALL offer a **Quit** action below the widget-visibility toggle,
separated by a divider. WHEN chosen, THEN the application SHALL shut down exactly as it does
from the tray icon's own Quit entry — stopping background work before the process ends.

---

## E2 — Collect a Word

**FR-2.1** WHEN the user chooses **Collect new word**, THEN a Collect card SHALL open anchored to
the widget, containing (per `mockup/widget-collect.html`): a "Word or phrase" text input, a Type
chip row, a Collection dropdown, a **Save word** primary button, a close affordance, and a status
line.

**FR-2.2** The Type chip row SHALL offer noun, verb, adjective, adverb, and phrase as
single-select chips; the selected chip SHALL be visually distinguished from the rest.

**FR-2.3** The Collection dropdown SHALL list all existing collections plus a
**+ New collection…** entry as its last option.

**FR-2.4** WHEN the user selects **+ New collection…**, THEN the dropdown and Save button SHALL be
replaced inline by a name text field with **Create** and **Cancel** buttons, keeping the user
inside the widget.

**FR-2.5** WHEN the user submits a new collection name, THEN the application SHALL reject it with
a visible message if the name is empty or already exists (compared case-insensitively);
otherwise it SHALL create the collection, restore the dropdown, and leave the new collection
selected.

**FR-2.6** WHEN the user cancels inline collection creation, THEN the dropdown and Save button
SHALL be restored with the previous selection intact and no collection created.

**FR-2.7** The **Save word** button SHALL be enabled as soon as a word and a type are present,
regardless of whether lookup has completed.

**FR-2.8** WHEN the user saves a word that is not a duplicate, THEN the application SHALL write
the row immediately using whatever lookup data has arrived, leaving Meaning and Example blank if
none has.

**FR-2.9** WHEN lookup completes after a row was already written, THEN the application SHALL
patch that same row's Meaning and Example rather than inserting a second row.

**FR-2.10** The Collect card SHALL NOT pre-fill the word from the clipboard or the current text
selection; entry is manual.

> **Adds to spec §3.1 (v3 workflow).** The Collect card gains an Auto-lookup / Manual meaning
> toggle so the user can type their own definition instead of waiting on the lookup pipeline.

**FR-2.11** The Collect card SHALL offer an **Auto-lookup / Type it myself** toggle, defaulting
to Auto-lookup. WHEN the user switches to **Type it myself**, THEN the application SHALL cancel
any lookup in progress for the current word, hide the read-only lookup result panel, and show
editable **Your meaning** and **Your example** fields in its place; WHEN the user switches back
to Auto-lookup, THEN a fresh lookup SHALL be started for the word and type currently entered.

**FR-2.12** WHEN the user saves a word while **Type it myself** is selected, THEN the application
SHALL store the typed Meaning and Example (trimmed; either may be blank) and SHALL NOT query any
lookup source or schedule a later enrichment patch for that row — a lookup result that was already
in flight when the mode was switched SHALL NOT be applied to the saved row.

---

## E3 — Dictionary Lookup & Enrichment

> **Revises spec §3.2.** The spec described a sequential fallback chain that stopped at the first
> hit. The user instead chose to query all three sources concurrently on every lookup
> (`requirements-clarification-questions.md` CQ2 = B). Priority ordering is preserved for
> deciding what gets saved.
>
> **Revised again in the v3 workflow.** A machine whose outbound HTTP to both web dictionary
> APIs is blocked or times out made auto-meaning silently return nothing, with no way to
> recover short of a network change. FR-3.1, FR-3.3, and FR-3.5 below are updated in place to
> add a fourth, network-free source — a bundled WordNet-derived JSON dictionary
> (`assets/dictionary/wordnet-2025-dictionary.json`) — ranked above the network dictionaries
> for exactly that reason.

**FR-3.1** WHEN a word and type are entered, THEN the application SHALL query all four sources
**concurrently** on a background thread: a **bundled offline dictionary** (no network
involved), the Free Dictionary API (`api.dictionaryapi.dev`), the Merriam-Webster Dictionary
API, and Google Translate (EN→VI).

**FR-3.2** For each dictionary source that returns entries, the application SHALL prefer the
definition and example whose part of speech matches the user's selected Type, falling back to the
first available definition when no part-of-speech match exists.

**FR-3.3** WHEN more than one source returns a result, THEN the application SHALL save the result
from the highest-priority source available, in the order: **bundled offline dictionary** >
Free Dictionary > Merriam-Webster > Google Translate.

**FR-3.4** WHEN the saved result comes from Google Translate, THEN Meaning SHALL hold the
Vietnamese translation and Example SHALL be left blank.

**FR-3.5** WHEN all four sources fail or return nothing, THEN the word SHALL still be saved with
its Type, with Meaning and Example blank.

**FR-3.6** The status line SHALL name the source of the result on success (for example
"✓ Found in offline dictionary", "✓ Found in Free Dictionary", "✓ Found in Merriam-Webster",
"✓ Translated to Vietnamese") and SHALL show a spinner with in-progress text while lookups
are outstanding.

> The mockups' status text still reads "Cambridge Dictionary". Cambridge was dropped from the
> product before v2; the mockup copy is stale and SHALL NOT be reproduced.

**FR-3.7** WHEN lookup resolves before the user saves, THEN the resolved Meaning and Example SHALL
be displayed read-only in a tinted panel inside the Collect card, per
`mockup/widget-collect-filled.html`.

**FR-3.8** The Merriam-Webster API key SHALL be configurable in Settings. WHEN no key is
configured, THEN the Merriam-Webster source SHALL be skipped and the remaining sources used.

**FR-3.9** Lookup failures SHALL NOT block saving, surface as unhandled errors, or freeze the UI.

---

## E4 — Duplicate Detection & Resolution

**FR-4.1** WHEN the user saves a word whose natural key already exists, THEN the application SHALL
open a conflict popup instead of writing a new row.

**FR-4.2** The conflict popup SHALL display the existing entry's Collection and its collected
Date, styled per `mockup/widget-collect-duplicate.html` (warning-bordered card, warning icon,
title naming the word).

**FR-4.3** WHEN the user chooses **Keep old**, THEN no data SHALL change and the new submission
SHALL be discarded.

**FR-4.4** WHEN the user chooses **Replace**, THEN the existing row's Meaning, Example, and Date
SHALL be overwritten with the new submission's values, while Words and Name of collection remain
unchanged. No new row SHALL be inserted.

**FR-4.5** WHEN the user chooses the delete action, THEN the existing row SHALL be removed **and**
the new submission SHALL be discarded — neither entry survives.

**FR-4.6** The delete action SHALL be labelled so that outcome is unambiguous (for example
"Delete both"), rather than a bare "Delete".

**FR-4.7** WHEN the popup is dismissed without a choice, THEN the application SHALL behave exactly
as **Keep old**. The popup SHALL state this consequence in its hint text.

**FR-4.8** Exactly one of {no change, existing row updated, existing row removed} SHALL occur per
resolution — the incoming word is never inserted as a separate row by any of the three actions.

---

## E5 — Practice: Session Setup

**FR-5.1** WHEN the user chooses **Practice**, THEN a native Practice window SHALL open on the
setup screen, titled "Vocabulary Trainer — Practice" per `mockup/practice-setup.html`.

**FR-5.2** The setup screen SHALL list every collection as a checkbox row showing its name, its
word count, and its creation date; checked rows SHALL be visually highlighted.

**FR-5.3** The setup screen SHALL provide a search box that filters the list live by
case-insensitive substring match on collection name, showing "No collections match your search."
when nothing matches.

**FR-5.4** The setup screen SHALL provide a sort control with **Newest first** (default),
**Oldest first**, and **Name (A–Z)**. Sorting SHALL operate independently of the search filter and
of which rows are checked.

**FR-5.5** WHEN the Practice window is opened, THEN the sort mode SHALL reset to Newest first.

**FR-5.6** The setup screen SHALL provide a **Required correct writes** stepper, defaulting to
**3**, constrained to the range **1–10** inclusive, with its increment and decrement controls
disabled at the bounds.

**FR-5.7** The setup screen SHALL display the combined pool size across all checked collections,
updating as checkboxes change.

**FR-5.8** WHEN the checked collections contain zero words in total, THEN the **Start practice**
button SHALL be disabled and an explanatory message SHALL be shown.

**FR-5.9** WHEN the user starts a session, THEN the pool SHALL be built from all words in the
checked collections and shuffled into random order.

---

## E6 — Practice: Drill & Summary

**FR-6.1** The drill screen SHALL show, per `mockup/practice-drill.html`: a progress counter, a
live **Score** and **Penalties** readout, a progress bar, the current word's Type as a badge, its
Meaning as the prompt, a centred answer input, and a mastery dot row.

**FR-6.2** The drill screen SHALL NOT display the current word's spelling before the user submits
an answer.

**FR-6.3** The progress counter and bar SHALL measure attempts made against the session's total
required attempts, calculated as `pool size × Required Correct Writes`.

**FR-6.4** An answer SHALL be judged correct when it matches the target word case-insensitively
after trimming surrounding whitespace.

**FR-6.5** WHEN an answer is correct, THEN the application SHALL play a success sound, read the
word aloud via system text-to-speech, increment that word's consecutive-correct count, and show
success-styled feedback naming the word.

**FR-6.6** WHEN a word's consecutive-correct count reaches Required Correct Writes, THEN it SHALL
be removed from the pool as mastered for the session.

**FR-6.7** WHEN a correct answer leaves a word short of mastery, THEN it SHALL be reinserted into
the pool at a position other than the immediate next draw, provided at least one other word
remains.

**FR-6.8** WHEN an answer is incorrect, THEN the application SHALL add one penalty, reveal the
correct spelling in danger-styled feedback, leave the word's consecutive-correct count unchanged,
and keep the word in the pool.

**FR-6.9** WHEN an answer is incorrect, THEN the drill SHALL wait for an explicit **Next** action
before advancing, so the user can read the revealed spelling.

**FR-6.10** The score SHALL be displayed live throughout the session and SHALL always equal
`total correct attempts − total penalties`.

**FR-6.11** The mastery dot row SHALL render one dot per required correct write, with filled dots
counting the current word's progress, plus a text line stating progress and whether the word
remains in the pool.

**FR-6.12** The drill screen SHALL provide an **End session** control that goes directly to the
summary. Closing the Practice window mid-session SHALL also route through the summary rather than
discarding it.

**FR-6.13** WHEN every word in the pool is mastered, THEN the summary screen SHALL be shown
automatically.

**FR-6.14** The summary SHALL display the final score prominently plus three statistics — words
practiced, total penalties, and time taken — per `mockup/practice-summary.html`.

**FR-6.15** The summary SHALL offer **Back to setup** and **Practice again**; Practice again SHALL
start a new session reusing the same checked collections and Required Correct Writes value.

**FR-6.16** WHEN a session ends, THEN its results (score, words practiced, penalties, elapsed
time, timestamp) SHALL be appended to a JSON history file under `%AppData%\VocabularyTrainer\`.
Session results SHALL NOT be written into the master workbook.

> **Adds to spec §4.3 (v3 workflow).** A separate, spreadsheet-native practice log was
> requested in addition to the existing JSON history — the JSON store answers "how did
> recent sessions go" (score-focused, capped, machine-read only); this answers "when did I
> practice, on what, and which specific words gave me trouble," meant to be opened directly
> in Excel like the master workbook already is.

**FR-6.17** WHEN a session ends (naturally, via End session, or by closing the window — the
same three routes as FR-6.12/FR-6.13), THEN one row SHALL be appended to a separate Excel
workbook `practice-log.xlsx` under `%AppData%\VocabularyTrainer\`, with columns: **Date**,
**Start Time** (`hh:mm:ss`), **End Time** (`hh:mm:ss`), **Collection** (the chosen collections,
comma-joined), **Penalty** (total penalties that session), **Finish** (`True`/`False`), and
**Word with penalty**. This file SHALL NOT be the master workbook and SHALL NOT be read by
any other feature — it is write-only from the app's perspective, for the user to inspect in
Excel.

**FR-6.18** The **Finish** column SHALL be `True` only when every word in the session's pool
reached mastery before the session ended (the pool was empty); ending early via End session or
by closing the window mid-session SHALL log `False`, even if some words were mastered.

**FR-6.19** The **Word with penalty** column SHALL hold `'|'.join(f"{word}_{count}")` for every
word missed at least once that session, where `count` is the number of times that word was
answered incorrectly — for example `hello_2|goodbye_3`. A session with no misses SHALL leave
this column blank.

---

## E7 — Settings & Collection Management

**FR-7.1** The Settings window SHALL use a two-pane layout — a left sidebar nav and a right
content pane — per `mockup/settings-general.html`, with the active nav item highlighted.

**FR-7.2** The sidebar SHALL contain five items: **General**, **Collections**, **Widget**,
**Audio**, and **About**.

**FR-7.3** The **General** tab SHALL contain the master file path with a **Browse…** button
opening a file picker, and the **Start with Windows** toggle.

**FR-7.4** The **Widget** tab SHALL contain the **Show widget** toggle and a **Character**
dropdown offering Cat and Crocodile, applied live on change.

**FR-7.5** The **Audio** tab SHALL contain a text-to-speech **Voice** dropdown listing the
system's installed voices, with a control to preview the selected voice.

**FR-7.6** The **About** tab SHALL display the application name, version, and the master file
location currently in use.

**FR-7.7** The **Collections** tab SHALL list every collection as a row showing its name, its word
count, and rename and delete actions, plus a **+ New collection** button — per
`mockup/settings-collections.html`.

**FR-7.8** WHEN the user creates a collection, THEN the name SHALL be rejected with a visible
message if empty or already existing (case-insensitive); otherwise the collection SHALL be
created with its creation date set to now.

**FR-7.9** WHEN the user renames a collection, THEN the new name SHALL be validated for
uniqueness, and on success the "Name of collection" value SHALL be updated on every word row
belonging to it. IF the update fails partway, THEN the rename SHALL be reverted so no rows are
left inconsistent.

**FR-7.10** WHEN the user deletes a collection, THEN a modal confirmation SHALL state the exact
number of words that will be permanently deleted and that the action cannot be undone, per the
overlay in `mockup/settings-collections.html`.

**FR-7.11** WHEN the user confirms deletion, THEN the collection and every word row belonging to
it SHALL be removed, and no rows belonging to other collections SHALL be affected.

**FR-7.12** WHEN the user cancels deletion, THEN nothing SHALL change.

**FR-7.13** All preferences — widget visibility, widget position, character, TTS voice, master
file path, Merriam-Webster API key, start-with-Windows — SHALL persist across restarts.

> **Adds to spec §6.2 (v3 workflow).** Each collection row gains a Preview action so the user
> can inspect a collection's contents without leaving the app or opening Excel.

**FR-7.14** Each row in the **Collections** tab SHALL carry a **Preview** action. WHEN chosen,
THEN a read-only modal SHALL display every word belonging to that collection as a table with
columns **Word, Type, Meaning, Example, Date**. A row whose Meaning or Example is blank SHALL
render that cell as "—" rather than leaving it empty. The table SHALL NOT support editing; word
rows are still edited by opening the workbook in Excel.

---

## E8 — Master File Persistence & Integrity

**FR-8.1** On first run the application SHALL create a master workbook at
`%AppData%\VocabularyTrainer\master.xlsx`, containing a `Words` sheet and a `Collections` sheet
with correct header rows, and SHALL seed a default collection named **General** so the first
Collect action has a destination.

**FR-8.2** The master file path SHALL be user-configurable from Settings and SHALL persist.

**FR-8.3** WHEN the workbook is opened, THEN its header rows SHALL be validated against the
expected columns.

**FR-8.4** WHEN a header row is altered or incomplete, THEN the application SHALL auto-repair it to
the expected schema, proceed with loading, and warn the user stating exactly what was changed.

**FR-8.5** All writes to the master file SHALL be atomic: written to a temporary file in the same
directory, then swapped into place, so the target file always contains either the complete old
content or the complete new content. Temporary files SHALL be cleaned up on both success and
failure.

**FR-8.6** WHEN a write fails because the file is locked by another process, THEN the application
SHALL keep the pending change in memory, show a clear message telling the user to close Excel,
and offer a **Retry** action that reattempts the same write.

**FR-8.7** Concurrent mutating operations SHALL be serialized so that no two writes to the master
file overlap.

**FR-8.8** The application SHALL watch the master file for external modification and reload its
in-memory data automatically when the file changes on disk.

**FR-8.9** Natural-key lookups SHALL match case-insensitively and ignore surrounding whitespace.

---

## Non-Functional Requirements

### Usability & Visual Design

**NFR-UI-01** `mockup/` is the visual source of truth. The design tokens in `mockup/styles.css`
SHALL be ported into the application's theme layer and used rather than redefined: the color set
(`--ink` `#1f2430`, `--ink-soft` `#5b6472`, `--ink-faint` `#8a93a3`, `--surface` `#ffffff`,
`--surface-soft` `#f4f6fa`, `--border` `#e1e6ee`, `--brand` `#4d6bfe`, `--brand-dark` `#3450d6`,
`--brand-soft` `#eef1ff`, `--success` `#2fb380`, `--success-soft` `#e6f7ef`, `--danger` `#e2554d`,
`--danger-soft` `#fdecea`, `--warning` `#e0a635`, `--warning-soft` `#fff4e0`), the radii (20px
large, 14px medium, 10px small), and the two shadow definitions (widget and card).

**NFR-UI-02** The UI SHALL use **Google Sans** (Regular 400 / Medium 500 / Bold 700) loaded from
TTF files bundled with the application, never from a CDN, so rendering does not depend on network
access. `Segoe UI` SHALL be the fallback.

**NFR-UI-03** Layout, spacing, and component styling SHALL follow the corresponding mockup file
for each screen closely. Where mockup **copy** contradicts these requirements — notably the
stale "Cambridge Dictionary" status text — these requirements win.

**NFR-UI-04** Destructive and state-changing controls SHALL use the semantic colors from the token
set: danger for deletion, warning for the duplicate conflict, success for correct feedback.

### Performance & Responsiveness

**NFR-PERF-01** The widget SHALL remain draggable and clickable at all times; no network or file
operation may block the UI thread.

**NFR-PERF-02** The Collect card SHALL open in under 300ms from menu click on a machine meeting
minimum requirements.

**NFR-PERF-03** Dictionary lookups SHALL run concurrently with a bounded timeout per source so one
slow or unreachable source cannot stall the others indefinitely.

### Reliability & Data Safety

**NFR-REL-01** No single failure — a failed lookup, a locked file, a malformed workbook, an
unavailable TTS voice — may crash the application or leave the master file corrupt.

**NFR-REL-02** The application SHALL be fully functional offline except for dictionary lookup,
which degrades per FR-3.5.

**NFR-REL-03** Destructive actions (collection deletion, duplicate delete-both) SHALL require
explicit confirmation.

### Security

**NFR-SEC-01** The Merriam-Webster API key SHALL be stored in the local user preferences file and
SHALL NOT be logged, echoed in error messages, or committed to the repository. No other secrets
are handled by the application.

**NFR-SEC-02** The application SHALL make outbound network requests only to the three configured
lookup endpoints, and SHALL transmit only the single word being looked up.

### Maintainability & Testability

**NFR-TEST-01** Business logic (natural-key matching, duplicate resolution, lookup priority
selection, shuffle and reinsertion, scoring and mastery, collection cascade operations) SHALL be
implemented independently of the UI layer so it is unit-testable without instantiating a window.

**NFR-TEST-02** ~~Unit tests SHALL accompany every unit of business logic in the same increment
as the code, with a minimum of **80% line coverage** on new business logic. Missing or failing
tests block completion.~~

> ⛔ **WITHDRAWN by explicit user instruction (v3).** Superseded by: **new unit tests SHALL NOT
> be written unless the user explicitly asks for them.** The suite that already exists is
> retained and SHALL keep passing (`python -m pytest`), and existing tests SHALL NOT be deleted
> or weakened to make a change pass — but authoring new tests is opt-in, on request only,
> regardless of the size or risk of a change. Verification SHALL instead be done by running the
> affected code and launching the application, reporting explicitly what was and was not
> checked. See `.kiro/steering/product-decisions.md` and `../../../../PROJECT.md` §4.2.

**NFR-TEST-03** Repository behavior SHALL be verifiable against real temporary `.xlsx` fixtures,
including the atomic-write and cascade paths.

### Accessibility

**NFR-A11Y-01** Accessibility is **not a focus for v2** (per Q22). Standard keyboard behavior
provided by the toolkits is retained where it comes for free, but no additional keyboard
navigation, screen-reader annotation, or contrast verification work is required. This is a
deliberate, recorded scope reduction rather than an oversight.

### Platform

**NFR-PLAT-01** Windows 10 (1809 or later) and Windows 11 on x64.

**NFR-PLAT-02** *(Retired during Application Design.)* This requirement covered detecting a missing
WebView2 runtime. Adopting `QWebEngineView` bundles the rendering engine with the application, so
there is no external runtime prerequisite to detect. The requirement no longer applies, and the
runtime-missing branches it drove in stories E5-S1 and E7-S1 are likewise void.

---

## Resolved Open Questions

All seven open questions from `specs/output_specs.md` §9 are now closed.

| Spec §9 | Question | Resolution | Requirement |
|---|---|---|---|
| 1 | Default master file path | `%AppData%\VocabularyTrainer\master.xlsx`, auto-created, configurable | FR-8.1, FR-8.2 |
| 2 | Master file locked in Excel | Clear error, pending change held in memory, Retry action | FR-8.6 |
| 3 | Altered header row | Auto-repair, proceed, warn the user what changed | FR-8.4 |
| 4 | External edits while running | Watch the file, reload automatically | FR-8.8 |
| 5 | Character selectable at runtime | Yes, from the Widget tab in Settings | FR-7.4 |
| 6 | Practice results in master file | No — separate JSON store under `%AppData%` | FR-6.16 |
| 7 | Duplicate "Delete" and the new submission | Neither survives; action relabelled for clarity | FR-4.5, FR-4.6 |

## Out of Scope

- Cloud sync or multi-device support.
- Languages beyond English (word) and Vietnamese (translation fallback).
- macOS, Linux, or mobile.
- Spaced-repetition scheduling — Practice remains manual collection selection.
- A browser-hosted or HTTP-served Practice mode.
- Accessibility work beyond what the toolkits provide by default (NFR-A11Y-01).
- Editing existing word rows from within the app — the master file is edited in Excel for that.
