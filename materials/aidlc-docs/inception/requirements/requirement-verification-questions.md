# Requirements Verification Questions — Vocabulary Trainer v2

These questions resolve the open items in `specs/output_specs.md` (Section 9), ambiguities
found while reading the `mockup/` UI reference, and the technology decisions that are open
because v2 is being built fresh with no implementation reference.

**How to answer**: fill in the letter choice after each `[Answer]:` tag. If none of the options
fit, choose the last option (Other) and describe your preference after the tag. Let me know
when you're done.

---

## Section A — Technology & Project Setup

## Question 1
v2 is being built fresh from the spec with no code reference. What UI technology should the
native Windows app use?

A) WPF on .NET 8 (C#) — mature always-on-top transparent overlay support, XAML styling maps
   cleanly to the mockup's design tokens

B) WinUI 3 / Windows App SDK (C#) — newer Microsoft stack, more modern controls

C) Avalonia UI (C#) — cross-platform capable, XAML-based

D) Python + PySide6/Qt — lighter tooling, simpler build

E) Electron / Tauri (web tech in a native shell) — reuses the HTML/CSS mockups directly

X) Other (please describe after [Answer]: tag below)

[Answer]: X Python for backend, u can choose light front end.

## Question 2
Where should the v2 project live in the workspace, given v1 (`VocabularyTrainer/`) must stay
untouched?

A) `VocabularyTrainer.V2/` — sibling folder, clearly versioned

B) `v2/` — short, generic top-level folder

C) `src/` at the workspace root — treat v2 as the primary implementation going forward

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 3
Which Excel library / approach should back the `.xlsx` master file?

A) ClosedXML — high-level, easy API, widely used (larger dependency)

B) EPPlus — feature-rich (requires a license declaration for commercial use)

C) OpenXML SDK directly — lowest-level, no third-party dependency, more code

D) Whatever the chosen UI stack's ecosystem standard is (defer to implementation stage)

X) Other (please describe after [Answer]: tag below)

[Answer]: X Pandas or spark using python

---

## Section B — Master File Behavior (Spec Section 9, Q1–Q4)

## Question 4
What should the default master file path be on first run?

A) `%AppData%\VocabularyTrainer\master.xlsx` — auto-created silently on first launch, changeable
   in Settings (matches the path shown in `mockup/settings-general.html`)

B) `Documents\VocabularyTrainer\master.xlsx` — more discoverable for the user to open in Excel

C) Prompt the user on first run to pick or create a location before the app is usable

D) No default — the app starts in a "not configured" state until the user sets a path in Settings

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 5
How should the app behave when the master file is locked because it's open in Excel and a write
is attempted?

A) Show a clear error telling the user to close Excel, keep the pending change in memory, and
   offer a Retry action

B) Retry silently a few times with a short delay, then show an error if still locked

C) Queue the change and auto-write it as soon as the file becomes available (background retry)

D) Block the operation up front — detect the lock before the user submits and disable saving

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 6
What should happen if the master file's header row has been manually altered or is invalid?

A) Refuse to load and show a diagnostic naming the expected columns; user must fix it in Excel

B) Attempt to auto-repair the header row and proceed, warning the user what was changed

C) Offer both: show the diagnostic with an explicit "Repair for me" button

D) Ignore the header row entirely and read/write by fixed column position

X) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 7
Should the app detect external manual edits made to the master file while the app is running
(e.g. the user editing it in Excel mid-session)?

A) Yes — watch the file and reload data automatically when it changes on disk

B) Yes, but only re-read on demand: reload whenever a screen opens (Collect card, Practice
   setup, Settings) rather than actively watching

C) No — read at startup and rely on the app being the only writer during a session

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Section C — Collect & Duplicate Behavior (Spec Section 9, Q7)

## Question 8
When resolving a duplicate with **Delete**, what happens to the word the user just submitted?

A) Discard both — the old row is removed and the new submission is not inserted (Delete means
   "I don't want this word at all")

B) Delete the old row and insert the new submission as a fresh entry

C) Rename the action to make it unambiguous (e.g. "Delete both" vs "Replace") and implement (A)

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 9
The mockups (`widget-collect.html`, `widget-collect-filled.html`) still say "Cambridge
Dictionary" in their status text, but the spec has replaced Cambridge with the Free Dictionary
API -> Merriam-Webster -> Google Translate pipeline. How should the lookup status line read?

A) Name the source being tried, updating live (e.g. "Looking up… / ✓ Found in Free Dictionary" /
   "✓ Found in Merriam-Webster" / "✓ Translated to Vietnamese")

B) Keep it generic — "Looking up…" then "✓ Definition found" with no source named

C) Generic while pending, but always name the source on success so the user can judge quality

X) Other (please describe after [Answer]: tag below)

[Answer]: A, and keep looking at all three sources

## Question 10
The Merriam-Webster API requires a free API key. How should v2 handle that?

A) Add a Merriam-Webster API key field in Settings; skip that fallback step when no key is set

B) Bundle a key in config at build time

C) Drop Merriam-Webster from v2 — pipeline becomes Free Dictionary -> Google Translate only

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 11
The Collect card in the mockup shows the Word field as the first input with Type chips and a
Collection picker. Should the word being collected also be capturable from the current
clipboard / selected text as a shortcut?

A) No — manual typing only, exactly as the mockup shows (keeps v2 scope tight)

B) Yes — pre-fill the Word field from the clipboard when the Collect card opens, still editable

C) Yes, plus a global hotkey that opens Collect pre-filled with the current clipboard contents

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Section D — Practice Behavior (Spec Section 9, Q6)

## Question 12
Are Practice session results written back into the master `.xlsx` file, or kept only in separate
app storage?

A) Separate app storage only (JSON under `%AppData%`) — the master file stays a clean word list

B) Written into the master file as extra columns (e.g. Last practiced, Times correct)

C) Separate app storage now, with a dedicated "Practice history" sheet in the workbook later

D) Not persisted at all — the summary is shown then discarded when the window closes

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 13
The drill screen's top bar shows "Word 14 of 170" and a progress bar. Since not-yet-mastered
words re-enter the pool, what should that counter and bar actually measure?

A) Attempts made vs. total correct writes required for the whole pool (pool size x required
   writes) — the bar fills steadily toward session completion

B) Words mastered vs. total words in the pool — the bar tracks true remaining work

C) Current attempt number vs. words remaining in the pool, recalculated live

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 14
The spec says a word is revealed after a miss and stays in the pool. Does the user get to retype
it immediately, or does the drill advance to the next word?

A) Advance to the next word — the missed word reappears later via the shuffle

B) Retype the same word immediately until correct, then continue

C) Show the reveal, then require an explicit "Next" action before advancing

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 15
How does the user end a Practice session early (the spec mentions early exit leads to the
summary)?

A) An explicit "End session" button in the drill top bar, going straight to the summary

B) Closing the Practice window shows the summary before closing

C) Both — an End session button, and window-close also routes through the summary

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 16
What is the default and allowed range for the "Required correct writes" stepper (the mockup
shows 3)?

A) Default 3, range 1–10

B) Default 3, range 1–5

C) Default 1, range 1–10 — fastest sessions by default

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Section E — Widget & Settings (Spec Section 9, Q5)

## Question 17
Is the mini-ani character (cat vs crocodile) selectable at runtime?

A) Yes — a Settings dropdown switches it live, as `mockup/settings-general.html` shows

B) Fixed per install; the dropdown is removed from Settings

C) Yes, and additional characters can be dropped into the assets folder to appear in the list

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 18
The Settings mockup's sidebar lists General, Collections, Widget, Audio, About, but only General
and Collections have content designed. What should v2 ship?

A) General + Collections only — the two designed tabs (widget/audio options already live under
   General)

B) All five tabs, splitting widget options out of General into Widget, TTS into Audio, and adding
   an About pane

C) General + Collections + About (About is cheap and useful for version info)

X) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 19
How is the app reached when the floating widget is toggled off (the widget is the only entry
point in the mockups)?

A) A system tray icon, always present, with the same menu as the widget

B) Relaunching the app's executable reopens Settings so the widget can be re-enabled

C) The widget never fully hides — it shrinks to a small edge tab that can be clicked

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 20
Should the app start automatically with Windows?

A) No, and no option for it in v2

B) No by default, but offer a "Start with Windows" toggle in Settings

C) Yes by default, with a toggle to turn it off

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Section F — Quality & Process

## Question 21
The mockups define an exact design-token set (`mockup/styles.css`: colors, radii, shadows,
Google Sans). How strictly should the v2 UI match them?

A) Strictly — port the tokens into the app's theme resources and match the mockups closely,
   treating `mockup/` as the visual source of truth

B) Approximately — use the tokens as a guide but prefer native OS-standard controls where they
   conflict

C) Native-first — use standard Windows styling; take only the color accents from the mockups

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 22
Accessibility scope for v2?

A) Keyboard navigation plus screen-reader labels on all interactive controls (baseline a11y)

B) Baseline a11y plus verified contrast ratios and a scalable font-size setting

C) Not a focus for v2 — mouse-driven only

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question: Security Extensions
Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for production-grade applications)

B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental projects)

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question: Property-Based Testing Extension
Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints (recommended for projects with business logic, data transformations, serialization, or stateful components)

B) Partial — enforce PBT rules only for pure functions and serialization round-trips (suitable for projects with limited algorithmic complexity)

C) No — skip all PBT rules (suitable for simple CRUD applications, UI-only projects, or thin integration layers with no significant business logic)

X) Other (please describe after [Answer]: tag below)

[Answer]: C
