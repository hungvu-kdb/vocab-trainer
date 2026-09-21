# Story Plan Clarification — Round 2

Eight of your nine answers are clear and recorded. **Q2 (granularity = C, one story per epic)**
conflicts with two other things you chose, and with a check the workflow requires me to pass. I
need one decision from you rather than picking for you.

---

## The conflict

You chose **Q2 = C — coarse, one story per epic, 8 large stories**. Three problems follow:

**1. It fails the mandatory INVEST check.** Phase D2 of the plan requires me to verify every story
is **I**ndependent, **N**egotiable, **V**aluable, **E**stimable, **S**mall, **T**estable. An
epic-sized story fails two of those outright:
- *Small* — "Collect a word" as one story spans the card UI, the type chips, the inline collection
  creation flow, the save path, and the lookup-patch behavior. That is not small by any definition.
- *Independent* — that same story bundles capabilities that genuinely are independent of each
  other (inline collection creation doesn't depend on the lookup pipeline), so it can't be
  delivered or tested in isolation.

If I generate 8 epic-sized stories, I have to report a blocking INVEST failure at D2 — which
means the stage can't complete. I'd rather surface that now than hand you artifacts that fail
their own gate.

**2. It weakens your Q7 = A (MoSCoW priority).** With one story per epic, all 8 stories are
necessarily "Must" — no epic is optional. Priority labels only carry information at a finer grain,
where you can say "the drill loop is Must, the TTS preview button is Could."

**3. It makes the user flow you asked for unwieldy.** Your original request was a user flow *per
user story*. Combined with Q3 = C (Mermaid diagram per story), an epic-sized story means one
diagram covering an entire epic — E6 (Practice Drill & Summary) alone spans the drill loop,
mastery, penalties, reveal-and-next, early exit, and the summary screen. That is a diagram nobody
can read, and it loses exactly the step-by-step clarity that made you ask for flows.

---

## Clarification Question 1
How should granularity be resolved?

A) **Medium granularity (~20–28 stories)** — one story per coherent user capability. Satisfies
   INVEST, makes MoSCoW meaningful, and keeps each Mermaid flow readable. Epics remain the outer
   structure exactly as you asked, so you still read the document as 8 epics — just with 2–5
   stories under each *(recommended)*

B) **Keep 8 epic-level stories, and I lower the INVEST bar** — I explicitly record that "Small"
   and "Independent" are waived for this project, with the waiver noted in the stage completion
   message. You get a much shorter document; the cost is that stories aren't independently
   deliverable and the later task breakdown has to re-decompose them anyway

C) **Two-level structure** — 8 epic-level stories as written, each containing named sub-stories
   that carry the actual flows, acceptance criteria, and MoSCoW labels. Reads coarse at the top,
   fine underneath. Slightly more document structure than (A), same total content

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Clarification Question 2
Only relevant if you pick B above. With 8 epic-sized stories, where should the Mermaid flow live?

A) One diagram per epic-story, accepting it will be large

B) Break each epic-story's flow into several smaller diagrams by scenario (happy path, error
   branches) — visually equivalent to medium granularity without renaming anything

C) Drop the Mermaid diagrams for epic-sized stories and use numbered steps with branches instead
   (what Q3 = A would have given)

X) Not applicable — I picked A or C in Question 1

[Answer]: C

---

## Recorded from round 1 (no action needed)

| Q | Decision |
|---|---|
| Q1 | Epic-Based outer structure, User Journey ordering within each epic |
| Q3 | Numbered steps **plus** a Mermaid flow diagram per story |
| Q4 | Acceptance criteria as a checklist of verifiable statements |
| Q5 | Full traceability — every story cites FR IDs and mockup files; UI-rendering flow steps name the mockup element |
| Q6 | Two personas — the Collector and the Driller, same human in different contexts |
| Q7 | MoSCoW priority per story |
| Q8 | No effort estimates |
| Q9 | No non-goal notes in stories.md; the requirements' Out of Scope section covers it |
