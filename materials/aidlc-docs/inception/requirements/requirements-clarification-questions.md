# Requirements Clarification Questions — Round 2

I analyzed your answers in `requirement-verification-questions.md`. Most are clear and I've
recorded them. Four items need resolution before I can write `requirements.md`: one answer
wasn't a valid option, one contradicts the product spec, and two need a concrete decision made
(one of which I think is technically the wrong tool for the job).

**How to answer**: fill in the letter choice after each `[Answer]:` tag.

---

## Invalid Answer 1: Security Extension

You answered **C** for "Security Extensions", but that question only offered **A**, **B**, or
**X** — there was no option C. (The question right after it, Property-Based Testing, *did* have
a C, so this may have been an off-by-one.)

For reference, you answered **C = No, skip all PBT rules** for Property-Based Testing, which I've
recorded as PBT disabled.

### Clarification Question 1
Should security extension rules be enforced as blocking constraints for Vocabulary Trainer v2?

A) Yes — enforce all SECURITY rules as blocking constraints

B) No — skip all SECURITY rules (suitable for a personal-use desktop app; note the app still
   handles a Merriam-Webster API key, so basic secret-handling hygiene will be applied either way)

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Ambiguity 1: "Keep looking at all three sources" (Q9)

You answered **"A, and keep looking at all three sources"**. Option A (name each source live in
the status line) is clear and recorded.

The "keep looking at all three" part contradicts `specs/output_specs.md` §3.2, which describes a
**fallback chain that stops at the first success**: Free Dictionary → (only if it misses)
Merriam-Webster → (only if that misses) Google Translate. "Keep looking at all three" implies
querying all three every time, which raises a question the spec doesn't answer: what happens
when more than one returns a result?

### Clarification Question 2
How should the three lookup sources be used?

A) Keep the spec's behavior — stop at the first source that returns a result (fastest, fewest
   network calls), and just name that source in the status line

B) Query all three in parallel every time, but still save only the highest-priority result that
   came back (Free Dictionary > Merriam-Webster > Translate) — feels faster on a slow first
   source, uses more network

C) Query all three in parallel and show the user all available results in the Collect card, letting
   them pick which Meaning/Example gets saved — richest, but adds a decision step to every collect

D) Query all three and save the best available Meaning **plus** keep the Vietnamese translation as
   an extra field alongside the English definition

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Ambiguity 2: Excel Library (Q3) — plus a correction

You answered **"Pandas or spark using python"**.

**A correction on Spark**: Apache Spark is a distributed cluster-computing engine built for
datasets that don't fit on one machine. This master file is a single local `.xlsx` with hundreds
to a few thousand rows, read and written by one desktop user. Spark would add a JVM dependency,
multi-second startup latency per operation, and hundreds of MB to the install, while making the
atomic single-file-write requirement (spec §8.2) harder rather than easier. I'd advise against it,
so I've left it out of the options below.

**On Pandas**: it works, but it's worth knowing that pandas reads a sheet into a DataFrame and
writes it back out wholesale, which means anything in the workbook it doesn't model (a second
sheet, cell formatting, column widths) has to be handled deliberately or it gets dropped. Since
the spec calls the master file "human-editable" and it needs both a `Words` and a `Collections`
sheet, that matters.

### Clarification Question 3
Which library should back the `.xlsx` master file?

A) **openpyxl** directly — the standard Python xlsx library; reads/writes cell-by-cell, preserves
   both sheets and user formatting, no DataFrame layer. Best fit for a file the user also edits by
   hand

B) **pandas + openpyxl** — pandas for reading/filtering (DataFrame convenience), openpyxl under
   the hood for writing; accepts that full-sheet rewrites are the write model

C) **pandas only**, simplest possible code, accepting that workbook formatting is not preserved

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Ambiguity 3: Frontend Choice (Q1) — you delegated this to me

You answered **"X — Python for backend, u can choose light front end."** Python backend is
recorded. Before I pick the frontend, there's a real tension you should decide on, because it
changes the whole UI implementation:

- **The widget needs a frameless, always-on-top window with true per-pixel transparency** so the
  cat/crocodile PNG has soft anti-aliased edges over the desktop, not a grey box.
- **You answered Q21 = A: strictly match the mockups** — port `mockup/styles.css` tokens (exact
  colors, 10/14/20px radii, soft shadows, Google Sans) and match the layouts closely.
- **"Light"** pulls the other way: the toolkits that make the above easy are the heavier ones.

### Clarification Question 4
Which Python frontend should v2 use?

A) **PySide6 (Qt)** — full support for frameless translucent always-on-top windows, and QSS
   stylesheets map almost 1:1 onto the mockup's CSS tokens, so strict visual fidelity is
   realistic. Cost: ~150MB+ of Qt in the install, LGPL licensing. Best fidelity-per-effort

B) **pywebview + WebView2** — a thin native window hosting the Windows-bundled WebView2 runtime,
   rendering HTML/CSS directly. The mockups become the UI almost verbatim (perfect fidelity, very
   little styling work), Python stays the backend via JS-to-Python bindings, and no web server is
   involved (local files only). Cost: needs care to get a transparent always-on-top overlay for
   the widget; arguably brushes against the spec's "no browser" intent even though nothing is
   served over HTTP

C) **Tkinter / CustomTkinter** — genuinely light, ships with Python, no extra dependency. Cost:
   transparency on Windows is color-key only (hard edges on the widget PNG, no soft shadow), and
   matching the mockup's rounded cards and shadows means hand-drawing them on a canvas. Strict
   fidelity (Q21=A) would be a constant fight

D) **Hybrid** — PySide6 for the floating widget and its popups (where transparency and
   always-on-top matter most), and a WebView2-hosted view for the Practice and Settings windows
   (where the mockup HTML can be reused directly). Cost: two UI technologies to maintain

X) Other (please describe after [Answer]: tag below)

[Answer]: D

---

## Recorded Without Change (no action needed from you)

For transparency, here's what I've locked in from round 1:

| Item | Decision |
|---|---|
| Q2 | v2 lives in `VocabularyTrainer.V2/` |
| Q4 | Master file defaults to `%AppData%\VocabularyTrainer\master.xlsx`, auto-created, changeable in Settings |
| Q5 | Locked file: clear error + keep pending change in memory + Retry action |
| Q6 | Invalid header row: auto-repair and proceed, warning the user what changed |
| Q7 | Watch the master file and reload automatically on external change |
| Q8 | Duplicate "Delete": rename the action so it's unambiguous, and discard both old row and new submission |
| Q10 | Merriam-Webster API key field in Settings; that step is skipped when no key is set |
| Q11 | No clipboard capture — manual typing only |
| Q12 | Practice results in separate app storage (JSON under `%AppData%`) |
| Q13 | Progress = attempts made vs. pool size x required writes |
| Q14 | On a miss: reveal, then require an explicit "Next" before advancing |
| Q15 | Both an "End session" button and window-close route through the summary |
| Q16 | Required correct writes: default 3, range 1-10 |
| Q17 | Character selectable at runtime from Settings |
| Q18 | All five Settings tabs ship: General, Collections, Widget, Audio, About |
| Q19 | Always-present system tray icon with the same menu as the widget |
| Q20 | "Start with Windows" toggle in Settings, off by default |
| Q21 | Strict mockup fidelity — `mockup/` is the visual source of truth |
| Q22 | Accessibility not a focus for v2 |
| PBT | Property-based testing rules disabled |

One note on **Q17 + Q18** together: since Q18 = B moves widget options into their own **Widget**
tab, the character dropdown and the show/hide toggle will live there rather than under General
(where `mockup/settings-general.html` drew them), and the TTS voice moves to **Audio**. General
keeps the master file path and the start-with-Windows toggle. Tell me if you'd rather keep
everything on General instead.
