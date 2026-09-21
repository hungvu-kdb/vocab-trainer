# AI-DLC State Tracking

## Project Information
- **Project Name**: Vocabulary Trainer v2
- **Project Type**: Greenfield (by explicit user instruction — see Scope Decision)
- **Start Date**: 2026-09-12T00:00:00Z
- **Current Stage**: INCEPTION - Application Design
- **Autonomy Mode**: User granted autonomous execution through to a complete product, instructing
  that recommended options be chosen for any further clarification. Stage approval gates are
  therefore self-approved with the recommended option and logged in audit.md.
- **Specification Source**: `specs/output_specs.md`
- **UI Reference Source**: `mockup/` (static HTML/CSS mockups + `mockup/styles.css`)

## Workspace State
- **Existing Code**: Yes in workspace, but EXCLUDED from this project's scope
- **Reverse Engineering Needed**: No — SKIPPED by explicit user instruction
- **Workspace Root**: `d:\random\LearnEnglish`

## Scope Decision (from user request)
- **v2 is built FRESH from the spec + mockups only.** No code, design docs, or architecture
  from any existing implementation are used as a reference.
- **Explicitly excluded as references**:
  - `VocabularyTrainer/` (v1 .NET/WPF implementation) — left completely untouched and frozen.
  - `.kiro/specs/vocabulary-trainer/` (v1 requirements.md / design.md) — not consulted.
  - `VastWords/` (unrelated Swift/macOS app in the workspace).
  - `.gitignore/` folder contents (per workspace steering rule).
- **Only inputs**: `specs/output_specs.md` and `mockup/`.
- Requirements are rebuilt as **Epic -> User Story**, each user story carrying an explicit
  **user flow**.
- **UI design details** are extracted from `mockup/*.html` + `mockup/styles.css` into the
  requirements.
- Old `.kiro/specs/vocabulary-trainer/tasks.md` is **archived** to `.gitignore/archive/` and
  tasks are rebuilt fresh.

## Code Location Rules
- **Application Code**: Workspace root subfolders (NEVER in aidlc-docs/)
- **Documentation**: aidlc-docs/ only
- **Structure patterns**: See code-generation.md Critical Rules

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | No | Requirements Analysis (round 2, CQ1 = B) |
| Property-Based Testing | No | Requirements Analysis (round 1, PBT = C) |

Note: although the Security Baseline extension is disabled, basic secret-handling hygiene still
applies to the Merriam-Webster API key (never logged, never committed) as an ordinary
requirement — see requirements.md NFR-SEC-01.

## Technology Decisions (locked at Requirements Analysis)
- **Language/Runtime**: Python 3.12+ (backend and application logic)
- **UI**: Hybrid — PySide6 (Qt) widgets for the floating widget and its popups; `QWebEngineView`
  (Qt's embedded Chromium) with a `QWebChannel` bridge for the Practice and Settings windows,
  reusing `mockup/` markup directly. No HTTP server; local files only.
  *(Revised during Application Design from the originally recorded "WebView2 via pywebview", which
  could not work: pywebview and Qt each own a blocking main event loop. See
  `inception/plans/application-design-plan.md` for the full deviation note.)*
- **Excel access**: **openpyxl only**
  *(Revised during construction from the recorded "pandas + openpyxl". The repository needs
  cell-level access across two sheets — in-place header repair, preserving user-added
  columns, deleting individual rows — which a DataFrame round-trip cannot do without
  rewriting whole sheets. pandas was imported nowhere and is not a dependency.)*
- **Project location**: `VocabularyTrainer.V2/`

## Stage Progress

### INCEPTION
- [x] Workspace Detection - Completed 2026-09-12
- [-] Reverse Engineering - SKIPPED (user instruction: no v1 code reference; treat as greenfield)
- [x] Requirements Analysis - Completed 2026-09-12 (comprehensive depth; 2 question rounds)
- [x] User Stories - Completed 2026-09-12 (42 stories, 8 epics, 2 personas; 2 planning rounds)
- [x] Workflow Planning - Completed 2026-09-12 (risk: Medium; 4 stages to skip with rationale)
- [x] Application Design - Completed 2026-09-12 (5 artifacts; QWebEngineView deviation documented)
- [x] Units Generation - Completed 2026-09-12 (10 units, 42 stories mapped, 7 build waves)

### CONSTRUCTION — Unit Progress
Build order: U1 -> U2 -> U4 -> U5 -> U3 -> U6 -> U7 -> U8 -> U9 -> U10

- [x] U1 Domain Core — 205 tests, 100% coverage
- [x] U2 Master File Repository — 66 tests, 96% coverage
- [x] U3 Preferences, History, Watching — 49 tests
- [x] U4 Lookup Clients & Orchestration — 49 tests (fixed a real MW parsing bug)
- [x] U5 Feedback & OS Integration — 29 tests
- [x] U6 Application Services — 150 tests, 96-99% per module (UI-independence proven)
- [x] U7 Theme & Widget Shell — 47 tests (fixed a real character-fallback bug)
- [x] U8 Collect & Duplicate Popups — presentation tests
- [x] U9 Practice & Settings Windows — bridges + pages, all five Settings tabs
- [x] U10 Composition Root & Startup — 27 tests (fixed a real data-dir override bug)

### CONSTRUCTION — Stage flags
- [x] Functional Design - EXECUTED for U1 and U2 (the units with real algorithms)
- [-] NFR Requirements - SKIPPED (tech stack and NFRs already fixed in Requirements Analysis)
- [-] NFR Design - SKIPPED (conditional on NFR Requirements)
- [-] Infrastructure Design - SKIPPED (local desktop app, no infrastructure)
- [x] Code Generation - COMPLETE for all 10 units
- [x] Build and Test - COMPLETE: 662 tests passing, 88% coverage, launch verified

### OPERATIONS
- [-] Operations - PLACEHOLDER (no deployment surface for a locally-installed desktop app)

## Additional Deliverables (outside AI-DLC stages)
- [x] Archive old tasks.md — the `.kiro/specs/vocabulary-trainer/` directory had already
      been removed externally, so nothing existed to move. Recorded in
      `.gitignore/archive/README.md` rather than claiming a move that did not happen.
- [x] Rebuilt `tasks.md` at `.kiro/specs/vocabulary-trainer-v2/tasks.md`
- [x] Reconstructed `specs/output_specs.md` — it was also deleted externally mid-session;
      rebuilt from its prior content plus every decision made in this workflow

## Final Result
- **662 tests passing, 0 failing. 88% line coverage on 1870 statements.**
- Application launches; every window constructs and renders (verified, scaffolding removed).
- v1 `VocabularyTrainer/` byte-identical — zero files modified.
- Three real bugs caught by tests during construction: Merriam-Webster example extraction
  (tagged pair-lists, not dict keys), character artwork fallback, and the data-directory
  override silently sharing one workbook.
