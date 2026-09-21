# Application Design Plan — Vocabulary Trainer v2

**Inputs**: `requirements.md` (74 FRs, 8 epics), `stories.md` (42 stories), `mockup/`
**Autonomy note**: The user granted autonomous execution with a standing instruction to choose the
recommended option for any clarification. The questions below are therefore answered with the
recommended option and the rationale recorded, rather than blocking for input.

---

## Questions and Resolved Answers

## Question 1 — Component organization
How should components be grouped?

A) **Layered by technical concern** — domain, data, integrations, services, ui *(recommended)*

B) Feature-sliced — each epic gets its own vertical folder containing its own models, data and UI

C) Flat module set with no layer grouping

**[Answer]: A**

**Rationale**: NFR-TEST-01 requires business logic to be testable without instantiating a window.
A layered split makes that boundary structural rather than a convention someone has to remember.
It also directly serves the hybrid-UI risk: with one shared service layer beneath two UI
technologies, layering is what stops PySide6 and the HTML views growing divergent copies of the same
logic. Feature slicing would fragment the workbook access across eight folders, which is the
opposite of what a single-file data store needs.

## Question 2 — Repository granularity
How should master-file access be exposed?

A) **One repository for the whole workbook** — words and collections together *(recommended)*

B) Separate WordRepository and CollectionRepository

C) Direct pandas/openpyxl calls from each service

**[Answer]: A**

**Rationale**: FR-8.5 and FR-8.7 require every write to be atomic and serialized against a single
file. Two repositories writing the same workbook would each need their own copy of the swap
sequence and would have to coordinate a shared lock — two chances to get it wrong. Cascading
operations (FR-7.9 rename, FR-7.11 delete) span both sheets in one atomic write, which a split
repository could not express without a transaction concept it does not have.

## Question 3 — Lookup client abstraction
How should the three lookup sources be modelled?

A) **A common protocol implemented by three clients, orchestrated by one service** *(recommended)*

B) One service with three hardcoded methods

C) A plugin registry discovered at runtime

**[Answer]: A**

**Rationale**: The three sources differ in transport and shape but answer the same question, and
FR-3.3's priority selection needs them to be uniformly comparable. A shared protocol also makes
FR-3.8's "skip Merriam-Webster when no key is configured" a matter of not registering that client,
rather than a conditional threaded through the orchestration. A runtime registry would be
unjustified machinery for a fixed set of three.

## Question 4 — UI-to-service communication
How do the UI layers reach the services?

A) **Constructor injection from a single composition root; UI holds service references** *(recommended)*

B) A global service locator / singleton registry

C) An event bus with no direct references

**[Answer]: A**

**Rationale**: Explicit injection is what makes the services independently testable with fakes, and
it keeps the dependency direction one-way (UI depends on services; services never import UI). A
singleton registry would hide dependencies and make test isolation awkward. An event bus would add
indirection that obscures the call graph without solving a problem this app has — though a narrow
observer channel *is* used for genuinely cross-cutting state changes (widget state, data reloaded),
which is noted in `services.md`.

## Question 5 — Hybrid UI boundary
How should the PySide6 and HTML-rendered views be bridged?

A) **Qt's own embedded Chromium (QWebEngineView) with a QWebChannel bridge to Python** *(recommended)*

B) pywebview with the WebView2 backend, in a separate event loop

C) Render every screen in PySide6 widgets, abandoning HTML reuse

**[Answer]: A** — with a documented deviation, see below.

**Rationale**: This preserves the substance of the approved hybrid decision — the mockup HTML/CSS
becomes the Practice and Settings UI, Python stays the backend — while fixing a real defect in the
mechanism. See the deviation note below.

---

## Documented Deviation from the Approved Technology Decision

The Requirements Analysis recorded the hybrid UI as *"PySide6 for the widget; WebView2-hosted
HTML/CSS via pywebview for Practice and Settings"*. Design work surfaced a blocking problem with the
`pywebview` half of that:

**The problem**: `pywebview` owns and runs its own blocking event loop (`webview.start()`), and so
does Qt (`QApplication.exec()`). One process cannot run both as the main loop. Workarounds — running
one in a background thread, or interleaving loops — are exactly the kind of fragile coupling that
makes a UI intermittently unresponsive, and the floating widget's whole value is that it stays
responsive (FR-1.9, NFR-PERF-01).

**The resolution**: use `QWebEngineView`, Qt's own embedded Chromium, for the Practice and Settings
windows, with `QWebChannel` as the JavaScript-to-Python bridge.

**What this preserves**:
- The mockup HTML and CSS are still the actual UI for Practice and Settings, so strict visual
  fidelity (Q21 = A, NFR-UI-01) is still achieved almost for free.
- Python remains the entire backend; the web layer holds no business logic.
- Still one native application, still no HTTP server, still no browser process, still no
  `localhost` — content is loaded from local files via `qrc:` / `file:` URLs inside the app's own
  window. The spec's architectural constraint holds.
- The hybrid split is unchanged: Qt widgets for the transparent overlay where per-pixel
  transparency is required, HTML for the document-like windows where the mockups already exist.

**What changes**:
- One event loop instead of two, and one dependency stack (Qt) instead of two (Qt + pywebview +
  WebView2 runtime).
- The WebView2 runtime prerequisite disappears, which also retires NFR-PLAT-02 and the
  runtime-missing branches in stories E5-S1 and E7-S1.
- `PySide6-Addons` (QtWebEngine) is added, which is a large dependency. This is the real cost of the
  choice and is accepted for a Windows desktop application where install size is not a stated
  constraint.

`requirements.md` and `aidlc-state.md` are updated to reflect this, per the rule that reversed
decisions replace the outdated text rather than sitting alongside it.

---

## Execution Checklist

- [x] 1. Analyze requirements and stories; identify capabilities and functional areas
- [x] 2. Resolve the design questions above
- [x] 3. Generate `components.md` — component definitions and responsibilities
- [x] 4. Generate `component-methods.md` — method signatures with input/output types
- [x] 5. Generate `services.md` — service definitions and orchestration patterns
- [x] 6. Generate `component-dependency.md` — dependency matrix, communication patterns, data flows
- [x] 7. Generate `application-design.md` — consolidated design document
- [x] 8. Validate design completeness against all 74 FRs
- [x] 9. Update `requirements.md` and `aidlc-state.md` with the QWebEngineView deviation
