# Unit of Work Plan — Vocabulary Trainer v2

**Inputs**: `requirements.md` (74 FRs), `stories.md` (42 stories), `application-design/*`
**Autonomy note**: questions are answered with the recommended option per the user's standing
instruction, with rationale recorded.

---

## Questions and Resolved Answers

## Question 1 — Story grouping strategy
How should the 42 stories be clustered into units?

A) **By architectural layer, then by feature within the UI layer** — foundation layers first, then
   feature units *(recommended)*

B) Purely by epic — 8 units, one per epic

C) Purely by layer — 5 units matching the design's five layers

**[Answer]: A**

**Rationale**: Pure epic grouping (B) would put a slice of the repository inside each of eight units,
so eight units would each need their own workbook access — the exact duplication the layered design
exists to prevent. Pure layer grouping (C) makes one enormous UI unit containing all 42 stories'
presentation, which defeats the purpose of decomposing. Layer-first for the foundation (domain, data,
integrations) then feature-first above it gives units that are each independently buildable and
testable, and it puts the three risky pieces first.

## Question 2 — Deployment model
How is the system deployed?

A) **Single deployable desktop application with logical modules** *(recommended)*

B) Multiple independently deployable services

**[Answer]: A**

**Rationale**: The product is one Windows executable. There is no network boundary anywhere inside it.
"Units" here are development and sequencing groupings, not deployment artifacts — so the design's
terminology is **Module** within a single deployable, and **Unit of Work** for planning.

## Question 3 — Unit sequencing driver
What determines the build order?

A) **Dependency order, with the three identified technical risks pulled as early as possible**
   *(recommended)*

B) User-visible value first — ship a working Collect flow before anything else

C) Alphabetical / arbitrary, resolving dependencies as they arise

**[Answer]: A**

**Rationale**: The execution plan named three risks: hybrid UI coexistence, the transparent overlay,
and atomic writes against a locked file. All three are cheapest to discover early, while the approach
can still change. Value-first (B) is attractive but would build the Collect UI on top of an unproven
persistence layer, which is where data loss would actually occur.

## Question 4 — Shared code between units
How do units share code?

A) **Direct imports within one package; lower-layer modules are the shared code** *(recommended)*

B) A separate shared/common library unit

C) Duplicate small helpers per unit to avoid coupling

**[Answer]: A**

**Rationale**: Within a single deployable, the layered structure already is the sharing mechanism.
A separate "common" unit would become a dumping ground with no clear ownership. Duplication (C) is
what `domain.natural_key` exists specifically to avoid.

## Question 5 — Directory structure
Where does code live?

A) **`VocabularyTrainer.V2/src/vocabulary_trainer/` with subpackages per layer** *(recommended)*

B) Flat modules under `VocabularyTrainer.V2/`

**[Answer]: A**

**Rationale**: Matches the structure already specified in `application-design.md` §8. A src-layout
keeps the importable package unambiguous and stops tests accidentally importing from the working
directory instead of the installed package.

## Question 6 — Team alignment
How does team structure affect unit boundaries?

A) **Single developer; boundaries chosen for sequencing and testability, not ownership**
   *(recommended)*

B) Multiple developers working in parallel; boundaries chosen to minimize contention

**[Answer]: A**

**Rationale**: This is a single-developer project (the same reason estimates were disabled at Q8).
Boundaries are therefore optimized for a sensible build order and for each unit being verifiable on
its own, rather than for parallel work avoidance.

## Question 7 — Unit test placement
Where do tests live relative to units?

A) **A mirrored `tests/` tree at the project root, one module per source module** *(recommended)*

B) Tests colocated beside the code they test

**[Answer]: A**

**Rationale**: Matches the structure in `application-design.md` §8 and keeps the shipped package free
of test code. Mirroring makes it immediately obvious which source module lacks tests — relevant given
the 80% coverage gate on new business logic.

---

## Execution Checklist

- [x] 1. Analyze stories, requirements, and application design for natural unit boundaries
- [x] 2. Resolve the decomposition questions above
- [x] 3. Generate `unit-of-work.md` — unit definitions, responsibilities, and code organization
- [x] 4. Generate `unit-of-work-dependency.md` — dependency matrix and build waves
- [x] 5. Generate `unit-of-work-story-map.md` — every story mapped to a unit
- [x] 6. Validate unit boundaries and dependency acyclicity
- [x] 7. Verify all 42 stories are assigned, with none orphaned or double-assigned
