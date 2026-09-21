# AI-DLC Audit Log

## Initial User Request
**Timestamp**: 2026-09-12T00:00:00Z
**User Input**: "keep the current version of VocabularyTrainer. make another v2, aidlc it, given specs in d:\random\LearnEnglish\specs\output_specs.md and mockup UI in d:\random\LearnEnglish\mockup
1. rebuild Requirement, split into Epic -> User Story, add me user flow for each user story.
2. refer to d:\random\LearnEnglish\mockup to add up info to requirement for UI design.
3. archive old tasks.md by moving it `.gitignore/archive`, rebuild tasks.md from fresh."
**AI Response**: "AIDLC skill triggered. Resolved spec file `specs/output_specs.md`. Resolved rule details to bundled reference copy at `~/.kiro/skills/aidlc/reference/aws-aidlc-rule-details/` (no workspace override found). Loaded core-workflow.md and mandatory common rules. Proceeding to Workspace Detection."
**Context**: AIDLC trigger / workflow entry

---

## Resolved Specification File (Initial Request Content)
**Timestamp**: 2026-09-12T00:00:00Z
**Spec File Path**: `d:\random\LearnEnglish\specs\output_specs.md`
**Spec File Content** (full, treated as the raw user request for Workspace Detection):

```markdown
# Vocabulary Trainer — Output Specification

> This is the living, consolidated specification for the Windows vocabulary trainer app.
> It merges every requirement and decision made across the design conversation — starting
> from `.ignore/raw_requirements.md`, refined through two clarification rounds, expanded in
> `.ignore/requirements_comprehensive.md`, and further revised while building the UI mockups
> in `mockup/`. Where an earlier document conflicts with this one, **this file wins** — it
> reflects the final, current state of product decisions.
>
> This file is meant to be kept up to date. See `.kiro/steering/product-decisions.md` for the
> standing instruction that keeps it in sync as new decisions are made in conversation.

## 1. Product Overview

A Windows desktop application that helps a user build and practice an English vocabulary
list. It has two pillars:

- **Learn** — a lightweight, always-on-top floating widget ("mini-ani") for capturing new
  words the moment the user encounters them, with automatic dictionary lookup.
- **Practice** — a native writing drill window that tests recall of previously collected
  words, organized by collection, with scoring and audio feedback.

All vocabulary data lives in a single, human-editable **Excel master file**.

- **Platform**: Windows only (desktop).
- **Architecture**: a single native Windows application. The floating widget, the Practice
  screen, and Settings are all native windows/overlays within the same app — **no web
  server or browser is involved anywhere** (this was explicitly decided after an earlier
  draft proposed a localhost-served Practice website; that approach was reverted in favor of
  a native Practice window, merged alongside Settings).
- **Primary data store**: a single `.xlsx` "master file", editable both by the app and
  manually by the user in Excel.
- **Visual design**: UI mockups (`mockup/*.html`) use **Google Sans** as the default typeface
  (self-hosted TTF, downloaded from Google Fonts) over a light, rounded, card-based visual
  style. See Section 7.

## 2. Data Model — Master File

### 2.1 Word Entry (one row per word)

| Column | Type | Required | Description |
|---|---|---|---|
| Words | Text | Yes | The word or phrase being learned. Natural key together with Collection. |
| Type | Enum (Text) | Yes | Part of speech: noun, verb, adjective, adverb, phrase, etc. |
| Meaning | Text | No | Definition — from the Free Dictionary API, Merriam-Webster fallback, or Google Translate fallback. |
| Example | Text | No | Example sentence from the Free Dictionary API or Merriam-Webster; blank on Translate fallback. |
| Name of collection | Text | Yes | Name of the Collection this word belongs to. |
| Date | Date | Yes | Date collected (or last replaced, per duplicate-resolution rules). |

- Word matching for duplicates is case-insensitive and whitespace-trimmed.
- `(Words, Name of collection)` is the natural key used to detect duplicates.

### 2.2 Collection (managed entity)

Collections are a first-class entity, not just a free-text column value:

| Field | Type | Required | Notes |
|---|---|---|---|
| Name | Text, unique | Yes | Display name and the value stored in "Name of collection". |
| Created date | Date | Yes (system-set) | Set automatically when the collection is created; used for sorting (Section 4.1). |

- **Create**: via general Settings, or inline from the Collect widget (Section 3.1) without
  leaving the widget.
- **Rename**: updates the "Name of collection" value on all existing word rows that belong to
  it, to keep referential consistency.
- **Delete**: cascades — deletes all word rows belonging to that collection. Requires an
  explicit confirmation dialog stating how many words will be deleted (destructive action).
- A default collection (e.g. "General") exists out of the box so first-time Collect actions
  have somewhere to save before the user creates any collections manually.

## 3. Feature: Learn → Collect New Vocabulary

### 3.1 Entry Point & Form

- Collection is initiated by clicking the floating widget ("mini-ani") and choosing
  **Collect** from the popup menu (Section 5).
- The Collect UI is minimal: a text input for Word/phrase, Type selected via chips (noun,
  verb, adjective, adverb, phrase, at minimum), and a Collection picker.
- **Creating a new collection inline**: the Collection picker includes a "+ New collection…"
  option. Selecting it swaps the dropdown for an inline name field with Create/Cancel
  buttons, directly inside the widget — the user never has to leave the widget or open
  Settings to create a collection on the fly. The newly created collection is immediately
  selected and available for future Collect actions.

### 3.2 Lookup Pipeline

> **Decision history**: Meaning/Example lookup was originally specced against Cambridge
> Dictionary, scraped via HTML parsing since it has no official public API. This was
> **reverted** in favor of a structured-API-first pipeline (Free Dictionary API →
> Merriam-Webster), which removes the fragile HTML-scraping dependency.

WHEN the user submits a Word + Type:

1. The app queries the **Free Dictionary API** (`api.dictionaryapi.dev`) in the background
   (non-blocking; the widget stays usable during lookup). This is a free, keyless, structured
   JSON dictionary API.
2. IF the Free Dictionary API returns a match, Meaning and Example are populated from its
   response, preferring the definition/example whose part of speech matches the Type the
   user selected (falling back to the first available definition if no part-of-speech match
   exists).
3. IF the Free Dictionary API has no entry for the word (or the request fails), the app falls
   back to the **Merriam-Webster Dictionary API**: Meaning and Example are populated from its
   response using the same part-of-speech preference as step 2.
4. IF Merriam-Webster also has no entry (or fails), the app falls back to **Google
   Translate**: translate the word to **Vietnamese**, store the translation as Meaning, and
   leave Example blank.
5. IF all three lookups fail (e.g. offline), the word is still saved with Type only, flagged
   for later manual enrichment.
6. Lookup results are shown read-only in the widget before the word is written to the
   master file; the user can save immediately even if lookup is still pending.

### 3.3 Duplicate Detection & Resolution

WHEN the submitted word already exists (same Word + Collection):

1. A small popup appears **inside the floating widget** showing the existing entry's current
   **Date** and **Collection**.
2. Three explicit actions are offered: **Keep** (discard new submission, existing row
   untouched), **Replace** (overwrite Meaning/Example/Date on the existing row with the new
   lookup results), **Delete** (remove the existing row).
3. IF the popup is dismissed without a choice, the app defaults to **"Keep old, discard
   new"** — no data is modified.

## 4. Feature: Practice → Writing Mode (Native Window)

> **Decision history**: Practice was originally specced as a website served by a local HTTP
> server and opened in the default browser. This was **reverted** — Practice is now a native
> app window, consistent with Settings and the rest of the app. No local server, no browser,
> no `localhost` involved.

### 4.1 Session Setup

- Opened as its own native window when "Practice" is chosen from the widget menu.
- **Collection multi-select**: the user selects one or many collections to combine into the
  practice word pool, shown as a checkbox list with each collection's word count.
- **Search collections by name**: a search box above the list filters collections by
  case-insensitive substring match against their name, live as the user types. A "no
  collections match" message is shown when the filter yields zero results.
- **Sort collections**: a sort control reorders the list independently of the search filter
  and of which collections are checked, with these modes:
  - Newest first (by collection creation date, descending) — default.
  - Oldest first (by collection creation date, ascending).
  - Name (A–Z).
- **Required correct writes**: a stepper control lets the user configure, before starting,
  how many consecutive correct writes are required per word to consider it "mastered" this
  session.
- IF the selected collection(s) resolve to zero words, the Start button is disabled with an
  explanatory message.
- The pool size (total word count from all selected collections) is shown before starting.

### 4.2 Drill Loop

1. Words are presented in **random shuffle order** from the practice pool.
2. For each word, the app shows its **Type** and **Meaning** (never the Word itself) and
   prompts the user to type the Word from memory.
3. WHEN the user submits an answer:
   - **Correct** (case-insensitive, trimmed match):
     - Plays a short success sound and reads the word aloud via system/OS text-to-speech.
     - Increments the word's correct-write counter, shown as mastery progress dots.
     - IF the word reaches its required correct-write count, it's removed from the pool
       (mastered) for this session; otherwise it's shuffled back in to appear again later.
   - **Incorrect**:
     - Applies **1 penalty**; the live score updates immediately:
       `score = total correct attempts − total penalties`, shown at the top of the screen
       throughout the session.
     - The word's mastery progress is **not reset** by a wrong attempt — only the penalty
       accumulates. The word stays in the pool.
     - The correct spelling is revealed to the user after a miss.

### 4.3 Session Summary

- Shown when all words in the pool are mastered, or the user ends the session early.
- Displays: final score, total words practiced, total penalties, and time taken.
- Actions: return to setup, or start practicing again.
- Results are recorded by the app into its own storage (whether this is also mirrored back
  into the master `.xlsx` file, e.g. as a "last practiced" stat, remains an open question —
  see Section 9).

## 5. Component: Floating Widget ("mini-ani")

- A small, decorative animated character rendered as an always-on-top overlay window,
  visible above other application windows unless turned off.
- Character is a cat or a crocodile (asset pipeline: source art was background-removed using
  `rembg` via the `remove_bg.py` tool from the `D:\random\Pic\background\` project, producing
  transparent cutouts stored in `asset/floating_widget/`).
- Draggable anywhere on screen; position persists across app restarts.
- Toggleable on/off entirely (Settings, or a quick toggle in the widget's own menu).
- **Click interaction**: clicking the mini-ani opens a popup menu with:
  - **Collect** — switches into the minimal Collect input UI (Section 3.1), inline in/around
    the widget.
  - **Practice** — opens the native Practice window (Section 4). No browser/server involved.
  - **Settings** — opens the native Settings window (Section 6).
  - A quick widget on/off toggle.
- The widget's animation changes to reflect its current state (idle vs. active/menu-open).

## 6. Component: Settings (Native Window)

- **Layout**: a two-pane window — a left sidebar nav (General, Collections) and a right
  content pane showing the selected tab, matching `mockup/settings-general.html` /
  `settings-collections.html`'s `native-nav` + `native-content` layout. (The mockups also
  sketch Widget/Audio/About as further nav items; only General and Collections are
  implemented so far — the nav list is built to add more items later without restructuring.)

### 6.1 General

- **Master file**: configurable file path to the `.xlsx` workbook, with a Browse dialog.
- **Floating widget**: on/off toggle; character choice (Cat / Crocodile).
- **Text-to-speech**: voice selection for reading words aloud during Practice.

### 6.2 Collections (CRUD)

- List of all collections with their word counts.
- **Create**: "+ New collection" button (also available inline from the Collect widget,
  Section 3.1).
- **Rename**: updates the collection name and propagates to all its word rows.
- **Delete**: shows a confirmation dialog naming the exact number of words that will be
  permanently deleted (cascade), requiring explicit confirmation before proceeding.

## 7. Visual Design

- **Typeface**: Google Sans (Regular/Medium/Bold), self-hosted as local TTF files rather than
  loaded from Google's CDN, so the app UI doesn't depend on an internet connection to render
  correctly. Downloaded from Google's font CSS API (`fonts.googleapis.com/css2?family=Google+Sans`).
- **Style**: light theme, rounded cards (`border-radius` in the 10–20px range), soft shadows,
  a blue primary accent color, with dedicated soft-tinted colors for success/danger/warning
  states. Full token set (colors, spacing, radii) is defined in `mockup/styles.css`.
- **Reference implementation**: static HTML/CSS mockups for every screen described in this
  spec live in `mockup/` (see `mockup/index.html` for the full catalog), and should be treated
  as the visual source of truth when implementing the real UI.

## 8. Non-Functional Requirements

1. **Offline resilience**: the Free Dictionary API, Merriam-Webster, and Google Translate
   lookups all require network access; the Collect flow degrades gracefully (Section 3.2
   step 5) without network. Practice and the rest of the app work fully offline since there's
   no web/server dependency.
2. **Data safety**: writes to the master `.xlsx` file should be atomic where possible (write
   to a temp file then swap) to avoid corrupting the workbook on a crash mid-write.
3. **Responsiveness**: the floating widget stays responsive to drag/click while background
   dictionary lookups are in progress (non-blocking async operations).
4. **Persistence of preferences**: widget on/off state, widget position, and TTS/voice choice
   persist across app restarts.
5. **Destructive-action safety**: deleting a Collection and resolving duplicate conflicts with
   "Delete" both require explicit confirmation.

## 9. Open Questions (Not Yet Resolved)

Carried forward from `requirements_comprehensive.md`, still unresolved:

1. What is the default master file path, and is it user-configurable at first run?
2. How does the app handle the master file being locked/open in Excel during a write?
3. Does the app validate/repair the master file header row if it's been manually altered?
4. Does the app detect external manual edits to the master file made while the app is
   running (e.g. user editing it directly in Excel mid-session)?
5. Is the mini-ani animation (cat vs crocodile) user-selectable at runtime, or fixed per
   install?
6. Are Practice session results (score/penalties) written back into the master file, or kept
   only in separate app storage?
7. When resolving a duplicate with "Delete", does the new submission still get inserted
   afterward, or is it discarded along with the old row?

## 10. Out of Scope

- Cloud sync or multi-device support for the master file.
- Any language other than English (word) / Vietnamese (fallback meaning).
- Mobile or macOS versions (Windows only).
- Spaced-repetition scheduling algorithms (Practice is manual collection-selection based, not
  automatic SRS).
- A web-based or browser-hosted Practice mode (explicitly reverted — see Section 4).
```

**Context**: Spec file content logged as initial request per AIDLC skill Step 3

---
## Workspace Detection
**Timestamp**: 2026-09-12T00:05:00Z
**User Input**: "dont use codebase of v1, approach it fresh without any coding refernce, just from specs and mockup UI"
**AI Response**: "Scope constraint accepted. v2 is treated as a GREENFIELD project: the existing `VocabularyTrainer/` (v1) .NET codebase, its `.kiro/specs/vocabulary-trainer/` design/requirements artifacts, and the `VastWords/` Swift app are all excluded as implementation references. Reverse Engineering stage is SKIPPED (no brownfield analysis of v1). The only inputs are `specs/output_specs.md` (product spec) and `mockup/` (UI/visual reference). Proceeding directly to Requirements Analysis."
**Context**: Workspace Detection — greenfield override by explicit user instruction; Reverse Engineering skipped

---
## Requirements Analysis — Intent Analysis & Questions Created
**Timestamp**: 2026-09-12T00:10:00Z
**User Input**: N/A (AI-initiated stage execution)
**AI Response**: "Intent analysis: Request Type = New Project (v2 rebuild); Clarity = Clear on scope/process, incomplete on tech stack and 7 spec-level open questions; Scope = System-wide (whole new app); Complexity = Complex. Requirements depth determined: COMPREHENSIVE. Read `specs/output_specs.md` and all 13 files in `mockup/` (index, styles.css, widget-idle, widget-menu, widget-collect, widget-collect-filled, widget-collect-duplicate, practice-setup, practice-drill, practice-drill-wrong, practice-summary, settings-general, settings-collections) to extract UI design detail. Created `aidlc-docs/inception/requirements/requirement-verification-questions.md` with 22 numbered questions across 6 sections (Technology & Project Setup, Master File Behavior, Collect & Duplicate, Practice Behavior, Widget & Settings, Quality & Process) plus 2 extension opt-in questions (Security Baseline, Property-Based Testing). Awaiting answers at the Step 6 gate."
**Context**: Requirements Analysis — Steps 2-6; gate awaiting user answers

---
## Requirements Analysis — Round 1 Answers Received
**Timestamp**: 2026-09-12T00:20:00Z
**User Input**: "done"
**AI Response**: "Read all 24 answers from requirement-verification-questions.md. Recorded: Q1=X (Python backend, frontend delegated to AI), Q2=A, Q3=X (pandas or spark), Q4=A, Q5=A, Q6=B, Q7=A, Q8=C, Q9='A, and keep looking at all three sources', Q10=A, Q11=A, Q12=A, Q13=A, Q14=C, Q15=C, Q16=A, Q17=A, Q18=B, Q19=A, Q20=B, Q21=A, Q22=C, Security=C (INVALID - no option C existed), PBT=C (disabled). Detected 1 invalid answer (Security ext.), 1 spec contradiction (Q9 'all three sources' vs spec 3.2 first-success fallback chain), and 2 answers requiring concrete decisions (Q3 library choice - advised against Spark as wrong tool for a single local xlsx; Q1 frontend choice delegated to AI but in tension with Q21 strict-fidelity requirement). Created round-2 file `requirements-clarification-questions.md` with 4 clarification questions plus a table of the 20 decisions already locked in. Awaiting answers."
**Context**: Requirements Analysis — Step 6 contradiction/ambiguity detection; second gate awaiting user answers

---
## Requirements Analysis — Round 2 Answers Received
**Timestamp**: 2026-09-12T00:30:00Z
**User Input**: "done"
**AI Response**: "Read round-2 answers: CQ1=B (Security extension DISABLED), CQ2=B (query all three lookup sources in parallel every time, save highest-priority result: Free Dictionary > Merriam-Webster > Translate — this REVISES spec 3.2's sequential first-success fallback chain), CQ3=B (pandas for reading/filtering + openpyxl engine for writing), CQ4=D (Hybrid frontend: PySide6/Qt for floating widget + popups, WebView2-hosted HTML/CSS via pywebview for Practice and Settings windows). No contradictions remain. Recorded Extension Configuration (Security=No, PBT=No) and Technology Decisions in aidlc-state.md. Proceeding to Step 7: generate requirements.md."
**Context**: Requirements Analysis — round 2 gate passed, all ambiguities resolved

---
## Requirements Analysis — Requirements Document Generated
**Timestamp**: 2026-09-12T00:40:00Z
**User Input**: "try again"
**AI Response**: "Generated `aidlc-docs/inception/requirements/requirements.md` at comprehensive depth. Structure: Intent Analysis, Scope Boundaries (v1/VastWords/.gitignore excluded), Technology Decisions table, Extension Configuration, Epic Map (E1-E8), Data Model (Words + Collections sheets, natural key, score, mastery definitions), 8 epics containing 74 numbered functional requirements (FR-1.1..FR-8.9), Non-Functional Requirements across 7 categories (UI/visual with full mockup token set inlined, Performance, Reliability, Security, Maintainability/Testability, Accessibility, Platform), a Resolved Open Questions table closing all 7 spec 9 items with requirement traceability, and Out of Scope. Notable: FR-3.x explicitly documents that CQ2=B REVISES spec 3.2 from a sequential first-success fallback chain to concurrent querying of all three sources with priority-ordered result selection; NFR-UI-03 records that stale mockup copy ('Cambridge Dictionary') must not be reproduced; NFR-A11Y-01 records the accessibility scope reduction as deliberate. Updated aidlc-state.md marking Requirements Analysis complete. Presenting for approval before User Stories."
**Context**: Requirements Analysis — Step 7-9 complete; approval gate

---

## Requirements Analysis — Approval Prompt
**Timestamp**: 2026-09-12T00:41:00Z
**AI Response**: "Presented completion message with review location and Request Changes / Approve & Continue options. Assessed User Stories stage as REQUIRED (new user-facing product, multiple flows, user explicitly requested Epic -> User Story split with per-story user flows), so the 'Add User Stories' option is not offered — it is already planned."
**Context**: Requirements Analysis — awaiting explicit user approval

---
## Requirements Analysis — Approved
**Timestamp**: 2026-09-12T00:50:00Z
**User Input**: "approve and continue"
**AI Response**: "Requirements approved. Marked Requirements Analysis complete in aidlc-state.md. Proceeding to User Stories stage, Part 1 (Planning)."
**Context**: Requirements Analysis — explicit user approval received

---

## User Stories — Part 1 Planning
**Timestamp**: 2026-09-12T00:52:00Z
**User Input**: N/A (AI-initiated stage execution)
**AI Response**: "Performed mandatory intelligent assessment per user-stories.md Step 1. Decision: EXECUTE (3 High Priority criteria met - new user features, UX changes, complex business logic; plus explicit user directive requesting Epic -> User Story split with per-story user flows). Documented in `aidlc-docs/inception/plans/user-stories-assessment.md`. Created `aidlc-docs/inception/plans/story-generation-plan.md` containing: Section 1 comparing all five standard breakdown approaches (Epic/Journey/Feature/Persona/Domain) with trade-offs and a recommendation; Section 2 with 9 planning questions (organization approach, granularity, user-flow format, acceptance-criteria format, traceability depth, persona count, priority labels, estimates, non-goal notes); Section 3 a 5-phase execution checklist (Foundation, Personas, per-epic Story Generation C1-C8, Mandatory Artifacts incl. INVEST verification and FR coverage table, Validation) with all boxes unchecked; Section 4 listing what is deliberately deferred to later stages. Awaiting answers at the Step 8 gate."
**Context**: User Stories — Part 1 Planning; gate awaiting user answers

---
## User Stories — Part 1 Planning Answers Received (Round 1)
**Timestamp**: 2026-09-12T01:00:00Z
**User Input**: "done"
**AI Response**: "Read all 9 answers from story-generation-plan.md: Q1=A (Epic outer + Journey ordering within), Q2=C (COARSE - one story per epic, 8 stories), Q3=C (numbered steps + Mermaid diagram per story), Q4=B (checklist acceptance criteria), Q5=A (full FR + mockup traceability), Q6=B (two personas: Collector, Driller), Q7=A (MoSCoW), Q8=C (no estimates), Q9=B (no non-goal notes). Per Step 9 mandatory answer analysis, detected a blocking conflict on Q2=C: (1) epic-sized stories fail the mandatory Phase D2 INVEST verification on 'Small' and 'Independent', which would force a blocking finding and prevent stage completion; (2) Q7=A MoSCoW becomes information-free since all 8 epics are necessarily 'Must'; (3) Q3=C Mermaid-per-story combined with epic-sized stories yields unreadable diagrams (E6 alone spans drill loop, mastery, penalties, reveal-next, early exit, summary), defeating the purpose of the per-story user flow the user originally requested. Created `story-plan-clarification-questions.md` with 2 questions offering: (A) medium granularity ~20-28 stories keeping epics as outer structure, (B) keep 8 epic-stories with an explicitly recorded INVEST waiver, (C) two-level epic/sub-story structure. Did NOT self-resolve. Awaiting answer."
**Context**: User Stories — Part 1 Step 9/10 ambiguity analysis; blocking conflict raised, second gate awaiting user answer

---
## User Stories — Part 1 Planning Approved (Round 2)
**Timestamp**: 2026-09-12T01:10:00Z
**User Input**: "done"
**AI Response**: "Read round-2 answers: CQ1=A (MEDIUM granularity - resolves the INVEST/MoSCoW/diagram conflict), CQ2=C (numbered steps with branches). Noted that CQ2 was explicitly scoped to 'only if you pick B in Question 1' and Q1 was answered A, making it not applicable; its substance is nonetheless honored by giving each story BOTH numbered steps with labelled branches AND a Mermaid diagram, a superset of Q3=C and CQ2=C. No further clarification round needed. Updated story-generation-plan.md with a resolved-answers table (Section 2b) recording the round-2 override and the CQ2 reconciliation note."
**Context**: User Stories — Part 1 approved, all ambiguities resolved

---

## User Stories — Part 2 Generation Complete
**Timestamp**: 2026-09-12T01:25:00Z
**User Input**: N/A (executing approved plan)
**AI Response**: "Executed the approved plan's Phases A-E, marking each checkbox [x] in story-generation-plan.md. Generated:
(1) `aidlc-docs/inception/user-stories/personas.md` — two personas per Q6=B: the Collector (mid-task capture, 10-30 second sessions, divided attention) and the Driller (dedicated 10-30 minute study sessions, focused). Each carries profile, goals, design-driving frustrations, success criteria, and the stories it drives. Includes a Shared Concerns table documenting the sharpest product tension: the Collector wants the widget always present while the Driller wants it gone, which is precisely why the widget is toggleable and a tray icon exists as a permanent fallback.
(2) `aidlc-docs/inception/user-stories/stories.md` — 42 user stories across the 8 epics (E1:5, E2:4, E3:5, E4:4, E5:4, E6:6, E7:8, E8:6), journey-ordered within each epic per Q1=A. Every story carries: story ID and title, As-a/I-want/So-that narrative, MoSCoW priority, persona, numbered user flow with labelled alternate/error branches, a Mermaid flowchart, a verifiable acceptance-criteria checklist, and FR + mockup traceability per Q5=A.
Verification section includes: INVEST compliance table (42/42 pass, with the note that 'Small' was the criterion that failed at epic granularity and drove the round-2 re-decision); acceptance criteria coverage; persona mapping (24 Collector-only, 11 Driller-only, 7 shared, summing to 42); full FR traceability table proving all 74 FRs covered with zero orphans plus an explicit list of which NFRs are cross-cutting rather than story-bound; priority distribution (34 Must, 7 Should, 1 Could, summing to 42); mockup cross-check documenting 3 stale-mockup discrepancies (Cambridge Dictionary naming, Settings tab placement under the 5-tab decision, and leftover 'delegated entirely to the local website' framing from the reverted web-Practice approach) all resolved in favor of requirements; and an excluded-source confirmation that no story references v1, VastWords, or .gitignore content.
Self-corrected four arithmetic errors in my own verification tables before presenting (story count stated as 29 when 42 were written, INVEST total, criteria count, and the priority/persona sums)."
**Context**: User Stories — Part 2 Generation complete; approval gate

---

## User Stories — Approval Prompt
**Timestamp**: 2026-09-12T01:26:00Z
**AI Response**: "Presented completion message with review locations (stories.md, personas.md) and Request Changes / Approve & Continue options, next stage Workflow Planning."
**Context**: User Stories — awaiting explicit user approval

---
## User Stories — Approved + Autonomy Granted
**Timestamp**: 2026-09-12T01:35:00Z
**User Input**: "approve & now ur free to go (alway choose recommend option if you need any further clarification) until you build complete product. stop process only when u use more than 1000 credit."
**AI Response**: "User Stories approved. User granted autonomous execution through to a complete product, with a standing instruction to choose the recommended option for any further clarification rather than stopping to ask. Recording this as the autonomy mode in aidlc-state.md: remaining stage approval gates are self-approved with the recommended option and logged here, rather than blocking on user input. Proceeding through Workflow Planning, Application Design, Units Generation, and the per-unit Construction loop without pausing."
**Context**: User Stories — approval received; autonomy mode granted for remaining workflow

---

## Workflow Planning — Complete
**Timestamp**: 2026-09-12T01:40:00Z
**User Input**: N/A (autonomous execution)
**AI Response**: "Created `aidlc-docs/inception/plans/execution-plan.md`. Analysis: Greenfield, Risk = Medium, Rollback = Easy (v2 isolated in its own folder), Testing = Moderate. Identified 3 concrete technical risks with mitigations: (1) hybrid PySide6 + WebView2 coexistence sharing one service layer - mitigated by UI-free domain/service layers and early validation; (2) transparent always-on-top overlay being the most platform-sensitive feature - mitigated by building it as the first UI unit so problems surface while the approach can still change; (3) atomic writes against a user-held-open file - mitigated by building persistence first against real workbook fixtures.
Stage decisions: EXECUTE Application Design (all components new; hybrid UI needs an explicit boundary or the two UI technologies will grow divergent copies of the same logic), EXECUTE Units Generation (42 stories / 8 epics / 2 UI technologies exceeds one unit), EXECUTE Functional Design per unit (5 precise algorithms worth settling before code), EXECUTE Code Generation and Build and Test (always).
SKIP NFR Requirements (its purpose is determining NFRs and selecting a tech stack - both already settled in Requirements Analysis; re-deriving risks drift), SKIP NFR Design (conditional on NFR Requirements), SKIP Infrastructure Design (local desktop app - no cloud resources, deployment topology, or IaC).
Also recorded the user's tasks.md archive/rebuild request as an explicit deliverable outside the AI-DLC stages so it is not lost, sequenced after Units Generation since the task list derives from the units, plus the steering-rule obligation to update specs/output_specs.md. Included both a Mermaid workflow diagram and a text alternative per content-validation rules. Self-approved per autonomy grant; proceeding to Application Design."
**Context**: Workflow Planning — complete, self-approved under autonomy mode

---
## Application Design — Complete
**Timestamp**: 2026-09-12T02:00:00Z
**User Input**: N/A (autonomous execution)
**AI Response**: "Created `aidlc-docs/inception/plans/application-design-plan.md` with 5 design questions, each answered with the recommended option per the autonomy grant and each carrying a rationale: Q1=A layered organization (makes NFR-TEST-01 structural, prevents the two UI technologies growing divergent logic), Q2=A single workbook repository (atomic+serialized writes to one file; split repositories couldn't express cross-sheet cascades without a transaction concept), Q3=A common LookupClient protocol (uniform comparability for priority selection; FR-3.8 becomes non-registration rather than a conditional), Q4=A constructor injection from a composition root (testability, one-way dependencies), Q5=A QWebEngineView.

DOCUMENTED DEVIATION: Q5 deviates from the technology decision recorded in Requirements Analysis ('WebView2 via pywebview'). Design work found that unworkable — pywebview and Qt each own a blocking main event loop and cannot coexist in one process without fragile interleaving that would compromise the widget responsiveness FR-1.9/NFR-PERF-01 depend on. Resolved by using QWebEngineView (Qt's embedded Chromium) with a QWebChannel bridge, which preserves every substantive property of the approved decision (mockup HTML as the real UI, Python as the whole backend, single native app, no server/browser/localhost) under one event loop. Side effects: NFR-PLAT-02 (WebView2 runtime detection) RETIRED since the engine now ships with the app, voiding the runtime-missing branches in stories E5-S1 and E7-S1; PySide6-Addons added as a large dependency, accepted. Per the reversal rule, outdated text in requirements.md and aidlc-state.md was REPLACED rather than left alongside.

Generated all five mandatory artifacts in `aidlc-docs/inception/application-design/`: components.md (5 layers, ~25 components, each with purpose/responsibilities/requirement refs and explicit reasoning for why several are separate components), component-methods.md (full signatures with types for every component across all layers), services.md (orchestration flows for each service including the save-then-patch ordering, duplicate resolution table, drill loop, and the AppContext 10-step startup sequence), component-dependency.md (dependency matrix showing an empty upper-right triangle, Mermaid component graph plus text alternative, 4 communication patterns with justification, 4 sequence diagrams, explicit circular-dependency check across 5 plausible cycles, and a testability table), application-design.md (consolidated: architecture, hybrid UI split, decisions-and-reasons table, concurrency model, error-handling strategy table, full FR/NFR coverage, project structure, and 5 design points deferred to Functional Design).

Self-approved per autonomy grant; proceeding to Units Generation."
**Context**: Application Design — complete, self-approved under autonomy mode; technology deviation documented and propagated

---
## Units Generation — Complete
**Timestamp**: 2026-09-12T02:20:00Z
**User Input**: N/A (autonomous execution)
**AI Response**: "Created `aidlc-docs/inception/plans/unit-of-work-plan.md` with 7 decomposition questions, each answered with the recommended option and rationale: Q1=A layer-first for foundation then feature-first above it (pure epic grouping would put repository slices in 8 units — the duplication the layered design exists to prevent; pure layer grouping would make one enormous UI unit), Q2=A single deployable with logical modules (no network boundary exists inside the app, so 'units' are sequencing groupings not services), Q3=A dependency order with the 3 technical risks pulled earliest, Q4=A direct imports (a separate 'common' unit becomes an unowned dumping ground), Q5=A src-layout, Q6=A single developer so boundaries optimize sequencing and testability not contention, Q7=A mirrored tests tree.

Generated all three mandatory artifacts in `aidlc-docs/inception/application-design/`:
- unit-of-work.md — 10 units (U1 Domain Core, U2 Master File Repository, U3 Preferences/History/Watching, U4 Lookup Clients & Orchestration, U5 Feedback & OS Integration, U6 Application Services, U7 Theme & Widget Shell, U8 Collect & Duplicate Popups, U9 Practice & Settings Windows, U10 Composition Root), each with scope, requirement refs, an explicit 'why this unit exists / why now' rationale, and a definition of done. Includes the greenfield code organization strategy.
- unit-of-work-dependency.md — dependency matrix (lower-left triangle only, so the numbering is itself a valid build order), 7 build waves with Mermaid plus text alternative, a recommended sequence table mapping each of the 3 technical risks to the unit position that confronts it, acyclicity verification across 4 candidate cycles, and 5 integration checkpoints.
- unit-of-work-story-map.md — all 42 stories mapped to exactly one primary unit plus contributing units.

Applied a strict assignment rule (primary unit = the unit containing the last work needed to make the story observably true) which eliminated the double-counting present in my first draft. Self-corrected the story arithmetic across both unit-of-work.md and the map: initial per-unit counts summed to 41 with E1-S5 ambiguously placed; final reconciliation is U2=4, U3=1, U4=4, U7=4, U8=9, U9=20 = 42 exactly. Also documented three non-obvious assignments and why (E1-S5 and E3-S5 to U9 because their observable surface is a Settings control; E8-S4 to U8 because the story is about preserving the user's typed word, not about the error the repository raises).

Noted explicitly that U1/U5/U6/U10 have zero primary stories because no user observes a service layer directly, and that the consequence is those units cannot be validated by acceptance criteria — their correctness rests entirely on unit tests, which is why the 80% coverage gate matters most for U1, U4, U6.

Self-approved per autonomy grant; proceeding to CONSTRUCTION PHASE, U1 Domain Core."
**Context**: Units Generation — complete, self-approved under autonomy mode

---
## CONSTRUCTION U1 Domain Core — Complete
**Timestamp**: 2026-09-12T02:50:00Z
**User Input**: N/A (autonomous execution)
**AI Response**: "Functional Design: created `aidlc-docs/construction/U1-domain-core/functional-design/functional-design.md` specifying all 8 algorithms in pseudocode with explicit rationale for each non-obvious choice — casefold vs lower (Unicode-correct caseless matching), internal whitespace collapse (phrases are stored, so double-spacing must not create a new entry), punctuation deliberately NOT normalized (would guess at intent), select_definition order preservation (sources order by commonness so 'first' is meaningful), is_empty treated as no-answer (else an empty high-priority response beats a good low-priority one), the reinsertion index-0 boundary case, negative scores not clamped, and >= for mastery (an off-by-one elsewhere must not strand the session).

Scaffolded `VocabularyTrainer.V2/` with pyproject.toml. Verified Python 3.14.0 is the active interpreter and that PySide6 6.11.2 is available; pinned PySide6 6.8.1.1 plus pandas/openpyxl/httpx/watchdog/pywin32. Coverage config omits ui/ and __main__.py with the reason recorded inline (they need live Windows compositing; NFR-TEST-01 keeps business logic out of them).

Code Generation: implemented 5 domain modules — natural_key.py, models.py, lookup_priority.py, shuffle.py, scoring.py — plus package __init__ files documenting the layering rule.

Tests: 205 tests across 5 test modules. Notable coverage of the specified edge cases: exhaustive 50-seed verification that reinsert_avoiding_next never lands at index 0 when other words remain; verification it DOES reach every valid position over 300 seeds (guards against a stuck distribution); permutation preservation via multiset equality; empty-high-priority-defers-to-lower; frozen-dataclass immutability; and that AppPreferences defaults match the mockup (required_correct_writes=3) and FR-1.8 (start_with_windows off).

RESULT: 205 passed, 0 failed, 100% line coverage on U1 (175 statements). Exceeds the 80% mandatory gate. Unit test compliance verified — no blocking findings.

Proceeding to U2 Master File Repository."
**Context**: CONSTRUCTION U1 — Functional Design + Code Generation complete, tests passing

---
## CONSTRUCTION U2-U6 — Complete
**Timestamp**: 2026-09-12T04:00:00Z
**User Input**: N/A (autonomous execution)
**AI Response**: "Completed five units. Cumulative: 344 tests passing, 92% line coverage on 1689 statements.

U2 Master File Repository (66 tests, 96%): Functional Design written first specifying the atomic write, header repair, and both cascades in pseudocode with rationale. Implemented atomic temp-then-swap using os.replace with the temp file created as a SIBLING of the target (os.replace is only atomic within one volume; a %TEMP% temp file could be on another drive, degrading the swap into copy-then-delete with a truncation window). RLock rather than Lock because cascade operations re-enter from the same thread. Cascade rename and delete each execute in ONE atomic write so a partial state is never written and the service layer needs no compensating revert. Header repair is positional so a renamed column keeps its data; extra user columns are preserved; case/whitespace header variants accepted silently to avoid training users to ignore warnings. Cell coercion never drops a row except for a blank word. Tests use real .xlsx fixtures throughout per NFR-TEST-03, including 12-thread concurrent insert verification and a monkeypatched PermissionError proving the target keeps prior content.

U3 Preferences/History/Watching (49 tests): both JSON stores use the same temp-then-swap discipline and degrade quietly (save/append return bool, never raise). Corruption tolerance is per-field so one bad value cannot lock the user out. required_correct_writes is clamped 1-10 on read because a hand-edited 0 would make a session impossible and 500 endless; bool is explicitly rejected since bool subclasses int in Python. File watcher debounces on a settle timer because Excel emits a multi-event burst per save and reading mid-burst yields a truncated file; a raising listener is caught so one bad callback cannot silently end all future reloads.

U4 Lookup (49 tests): three clients behind one protocol, all guaranteeing fetch never raises. LookupService queries every AVAILABLE client concurrently under one shared deadline, then delegates selection to domain.lookup_priority. Merriam-Webster reports is_available()=False without a key, which is how FR-3.8's skip is implemented — by not calling it rather than a conditional in the orchestrator. FOUND AND FIXED A REAL BUG during testing: Merriam-Webster nests examples as tagged pair-lists (['vis', [...]]) not as dicts with a 'vis' key, so my original dict-only walker never found examples. Corrected the walker to yield lists as well and handle both forms.

U5 Feedback/OS (29 tests): TTS speaks on a worker thread because SAPI's Speak blocks for the utterance duration and would freeze the drill on every correct answer. Audio falls back through bundled WAV -> Windows system alias -> silence. Startup registration returns the achieved state so a Settings toggle can revert rather than displaying a lie.

U6 Application Services (150 tests, 96-99% per module): the UI-independence checkpoint — every service test runs with NO Qt application object in the process, which defuses the hybrid-UI risk by proving both UI technologies will be thin consumers. CollectService implements the save-then-patch ordering (insert immediately with whatever lookup produced, patch the same row later, abandon the patch quietly if the row was deleted meanwhile). resolve_duplicate enforces FR-4.8 with a parametrized test asserting no action ever inserts the incoming word separately. PracticeService protects the FR-6.8 invariant (a miss never reduces mastery progress) with a dedicated test, and two full-session runs prove termination with and without misses. Injected Clock throughout makes date stamping and elapsed time exactly assertable.

Also fixed a test-infrastructure problem: a per-directory conftest with relative imports failed because test dirs are not packages; consolidated shared fakes into tests/conftest.py and added 'tests' to pytest pythonpath.

Proceeding to U7 Theme & Widget Shell."
**Context**: CONSTRUCTION U2-U6 complete; 344 tests passing, 92% coverage, no blocking findings

---
## CONSTRUCTION U7-U10 + Build and Test — Complete
**Timestamp**: 2026-09-12T07:00:00Z
**User Input**: "get back to your work"
**AI Response**: "Completed the remaining four units and the Build and Test stage. FINAL: 662 tests passing, 88% line coverage on 1870 statements, application verified launching with all windows rendering.

U7 Theme & Widget Shell (47 tests): design tokens transcribed from mockup/styles.css into ONE source generating both the Qt stylesheet and the web CSS variables, so the two surfaces cannot drift (NFR-UI-01). FloatingWidgetWindow combines FramelessWindowHint + WA_TranslucentBackground + WindowStaysOnTopHint + Tool — the Tool flag being the non-obvious one that keeps it out of the taskbar and stops it stealing focus. Drag uses a 4px threshold so a hand tremor during a click does not register as a drag. Position clamping handles both a disconnected monitor and an over-edge drag. TrayIcon.is_available gates the widget's hide action so the app can never be running yet unreachable. FOUND AND FIXED A REAL BUG: the crocodile character fell back to the unsuffixed cat artwork, so it reported as available and Settings would have offered it then rendered a cat; non-cat characters now resolve strictly against their own suffixed files.

U8 Collect & Duplicate Popups: CollectCardPopup marshals worker-thread lookup completion onto the UI thread via a signal (touching widgets from a worker is undefined behaviour in Qt). Save is enabled on word+type alone regardless of lookup state. DuplicateConflictPopup labels the destructive action 'Delete both' per FR-4.6, and routes every dismissal path (X, Escape, click-away) through the same Keep-old resolution so a conflict is never left ambiguous. Tests assert the stale 'Cambridge Dictionary' mockup copy is never reproduced.

U9 Practice & Settings Windows: QWebChannel bridges where every slot returns JSON primitives and catches its own exceptions (an exception crossing the channel surfaces in JS as an opaque failure). Practice and Settings pages derived from the mockups with all five Settings tabs. pick_master_file opens a native Qt dialog because the web layer's file input only reports a sandboxed name. WebWindow stages assets plus Qt's qwebchannel.js into one writable directory and injects theme tokens at load. PracticeWindow.closeEvent ends the session so results are recorded per FR-6.12.

U10 Composition Root: AppContext with the explicit 10-step startup sequence; tray created before widget so hide-availability is known. FOUND AND FIXED A REAL BUG via test: a custom app_data_dir moved preferences but left the workbook pointing at the real %AppData%, so a portable install or a test would silently share one workbook. Now the default master path derives from the data directory while a user-chosen path is still honoured.

Build and Test: wrote a temporary launch check that built the real QApplication and exercised every window — all 11 checks passed (widget frameless/translucent, tray available, workbook created, menu/collect/practice/settings all opening and titled). Removed it afterwards as it was verification scaffolding, not shipped code. Wrote README.md with install/run/test/architecture and an explicit notes-and-limitations section.

Deliverables outside the AI-DLC stages: (1) tasks.md archive — the .kiro/specs/vocabulary-trainer/ directory had already been removed from the workspace externally, so there was nothing to move; recorded that honestly in .gitignore/archive/README.md rather than reporting a move that did not happen. (2) Rebuilt .kiro/specs/vocabulary-trainer-v2/tasks.md from the v2 artifacts, including a Deferred section giving reasons for each unchecked item. (3) specs/output_specs.md had ALSO been deleted externally mid-session; since the steering rule requires it maintained, reconstructed it from its prior content plus every decision made in this workflow, with the reconstruction noted at the top.

Verified v1 (VocabularyTrainer/) is byte-identical — zero files modified."
**Context**: CONSTRUCTION complete; Build and Test complete; all deliverables closed

---
