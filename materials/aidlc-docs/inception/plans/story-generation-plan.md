# Story Generation Plan — Vocabulary Trainer v2

**Role**: Product Owner
**Inputs**: `aidlc-docs/inception/requirements/requirements.md` (8 epics, 74 FRs), `mockup/`
**Assessment**: `aidlc-docs/inception/plans/user-stories-assessment.md` — Execute = Yes

This plan defines **how** user stories will be produced. Please answer the questions in
Section 2 before I generate anything; the plan's execution checklist in Section 3 then runs
against your answers.

---

## 1. Story Breakdown Approach Options

Your request already fixes the top-level structure as **Epic -> User Story**, so the question is
how stories are organized *within* each epic. The five standard approaches, with trade-offs:

| Approach | How it works here | Benefit | Trade-off |
|---|---|---|---|
| **Epic-Based (hierarchical)** | Stories nest under the 8 existing epics (E1–E8) | Directly matches your requested structure and the existing FR numbering | Says nothing about ordering *within* an epic |
| **User Journey-Based** | Stories follow the user's path: first launch -> collect a word -> practice it -> manage collections | Flows read naturally; dependencies surface early | Cuts across epics, so one journey touches several epics |
| **Feature-Based** | Stories map to system capabilities (lookup, duplicate handling, scoring) | Clean technical boundaries, easy to estimate | Can drift toward implementation-speak rather than user value |
| **Persona-Based** | Stories grouped by user type | Useful when serving distinct audiences | This app has essentially one user, so grouping adds little |
| **Domain-Based** | Stories grouped by business domain (vocabulary, practice, configuration) | Good for large multi-team systems | Overkill at this size; overlaps the epic split |

**My recommendation**: **Epic-Based as the outer structure** (as you asked) with **User
Journey ordering inside each epic** — stories sequenced the way a user actually encounters them,
which makes the per-story user flows connect end to end rather than reading as disconnected
fragments.

---

## 2. Questions

Please fill in each `[Answer]:` tag with a letter choice. If none fit, pick the last option and
describe your preference.

## Question 1
Confirm the story organization approach.

A) Epic-Based outer structure with User Journey ordering inside each epic (recommended)

B) Epic-Based outer structure with Feature-Based grouping inside each epic

C) Pure User Journey-Based, letting journeys cross epic boundaries

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 2
What granularity should stories have? This drives how many you get.

A) **Medium** — one story per coherent user capability; roughly 20–28 stories across 8 epics.
   Example: "Collect a word into a collection" is one story covering the form, the type chips, and
   the save

B) **Fine** — one story per discrete interaction; roughly 40–55 stories. Example: the above splits
   into "enter a word", "select a part of speech", "pick a collection", "save the entry"

C) **Coarse** — one story per epic; 8 large stories. Example: "Collect vocabulary" is a single story

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 3
What format should each user flow take? This is the artifact you specifically asked for.

A) **Numbered steps with branches** — a happy-path step list, then labelled alternate and error
   branches (e.g. "3a. If the word already exists -> ...") with the mockup file named per step

B) **Numbered steps only** — happy path per story; error cases live in acceptance criteria instead

C) **Numbered steps plus a Mermaid flow diagram** per story — most visual, longest documents

D) **Given/When/Then scenarios** used as the flow, one scenario per branch

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 4
What acceptance criteria format should each story carry?

A) **Given/When/Then** (Gherkin-style) — directly translatable into test cases

B) **Checklist of verifiable statements** — shorter, easier to scan

C) **Both** — a checklist for scanning, plus Given/When/Then for the non-obvious branches

X) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 5
How should stories reference the requirements and mockups?

A) Every story cites its FR IDs **and** its mockup file(s); every flow step that renders UI names
   the mockup element it maps to

B) FR IDs only — keep mockup references at the epic level

C) Prose references without explicit IDs

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 6
How many personas should `personas.md` define? The shipped app has one real end user, but
distinct *motivations* exist.

A) **One primary persona** — the self-directed English learner who both collects and practices

B) **Two personas** split by mode — the "Collector" (capturing words while reading/working) and the
   "Driller" (sitting down to practice), acknowledging they're the same human in different contexts

C) **Three personas** — add the "Curator" who maintains collections and edits the workbook in Excel

X) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 7
Should stories carry priority labels to guide construction sequencing?

A) Yes — MoSCoW (Must / Should / Could / Won't) per story

B) Yes — simple P1/P2/P3

C) Yes — MVP vs Post-MVP, a single binary split

D) No — all stories are in scope for v2; ordering is decided in Workflow Planning instead

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 8
Should stories carry effort estimates?

A) Yes — relative story points (1/2/3/5/8)

B) Yes — T-shirt sizes (S/M/L)

C) No — estimation adds little for a single-developer project

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 9
The requirements deliberately exclude some things (accessibility work, editing word rows in-app,
SRS scheduling). Should `stories.md` include explicit **non-goal** notes where a reader would
plausibly expect a story to exist?

A) Yes — add a short "Not covered" note in the relevant epic so gaps read as decisions, not
   oversights

B) No — the requirements' Out of Scope section already covers it

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## 2b. Resolved Answers (final)

| Q | Decision |
|---|---|
| Q1 | Epic-Based outer structure, User Journey ordering within each epic |
| Q2 | **Medium granularity** — resolved in round 2 (CQ1 = A) after `Q2 = C` was found to fail the mandatory INVEST check, void the MoSCoW labels, and make per-story flow diagrams unreadable. See `story-plan-clarification-questions.md` |
| Q3 | Numbered steps **with labelled branches**, **plus** a Mermaid flow diagram per story |
| Q4 | Acceptance criteria as a checklist of verifiable statements |
| Q5 | Full traceability — every story cites FR IDs and mockup files; UI-rendering flow steps name the mockup element |
| Q6 | Two personas — the Collector and the Driller |
| Q7 | MoSCoW priority per story |
| Q8 | No effort estimates |
| Q9 | No non-goal notes in stories.md |

**Note on round-2 CQ2**: that question was explicitly scoped to "only relevant if you pick B in
Question 1", and Question 1 was answered A, making it not applicable. The answer given (C — use
numbered steps with branches) is nonetheless honored in substance: each story carries numbered
steps **with labelled alternate/error branches** *and* a Mermaid diagram, which is a superset of
both Q3 = C and CQ2 = C. No conflict remains and no further clarification is required.

---

## 3. Execution Checklist

### Phase A — Foundation
- [x] A1. Re-read `requirements.md` in full and build an FR -> epic coverage map
- [x] A2. Re-read each `mockup/*.html` file and index every screen, region, and control by name
- [x] A3. Confirm the resolved answers from Section 2 and note any that alter the plan

### Phase B — Personas
- [x] B1. Draft personas at the count chosen in Q6, each with goals, context of use, frustrations,
      and success criteria
- [x] B2. Write `aidlc-docs/inception/user-stories/personas.md`

### Phase C — Story Generation (per epic, E1 through E8)
- [x] C1. E1 — Floating Widget & App Presence
- [x] C2. E2 — Collect a Word
- [x] C3. E3 — Dictionary Lookup & Enrichment
- [x] C4. E4 — Duplicate Detection & Resolution
- [x] C5. E5 — Practice: Session Setup
- [x] C6. E6 — Practice: Drill & Summary
- [x] C7. E7 — Settings & Collection Management
- [x] C8. E8 — Master File Persistence & Integrity

Each story produced in C1–C8 must carry:
- [x] A story ID and title
- [x] The "As a / I want / So that" narrative
- [x] A **user flow** in the Q3 format
- [x] Acceptance criteria in the Q4 format
- [x] Traceability per Q5
- [x] Priority per Q7 (estimates disabled per Q8)

### Phase D — Mandatory Story Artifacts (required by the workflow)
- [x] D1. Write `aidlc-docs/inception/user-stories/stories.md`
- [x] D2. Verify every story satisfies INVEST — Independent, Negotiable, Valuable, Estimable,
      Small, Testable — and record the check
- [x] D3. Confirm every story has acceptance criteria
- [x] D4. Map personas to the stories they drive
- [x] D5. Build a traceability table proving all 74 FRs are covered by at least one story, and
      flag any FR that is not

### Phase E — Validation
- [x] E1. Cross-check every story's flow against its mockup for contradictions
- [x] E2. Confirm no story depends on an implementation detail from v1 or any excluded source
- [x] E3. Verify Mermaid content passes the content-validation rules
- [x] E4. Update `aidlc-docs/aidlc-state.md` and log completion in `audit.md`

---

## 4. Out of Scope for This Stage

Deliberately excluded here, to be handled later in the workflow:
- Technical design, component structure, class or module decisions (Application Design)
- Sprint planning, timelines, developer assignment
- Test implementation — only the criteria that tests will verify are defined here
- Unit-of-work decomposition (Units Generation)
