# Units of Work — Vocabulary Trainer v2

**Deployment model**: a single deployable Windows desktop application. Units are **development and
sequencing groupings** (logical modules), not independently deployable services. Terminology follows
the workflow's guidance: *Module* for a logical grouping inside one deployable, *Unit of Work* for
planning.

**Total**: 10 units covering all 42 user stories and all 74 functional requirements.

---

## Code Organization Strategy

```
VocabularyTrainer.V2/
├── pyproject.toml                   deps, build config, pytest + coverage config
├── README.md                        run / build / test instructions
├── src/vocabulary_trainer/
│   ├── __main__.py                  entry point            [U10]
│   ├── domain/                      pure logic             [U1]
│   ├── data/                        persistence            [U2, U3]
│   ├── integrations/                external world         [U4, U5]
│   ├── services/                    orchestration          [U6]
│   ├── ui/
│   │   ├── theme/                   token source + generated .qss / .css   [U7]
│   │   ├── widget/                  Qt overlay windows     [U7, U8]
│   │   └── web/                     QWebEngineView hosts   [U9]
│   └── assets/                      PNGs, fonts, sounds
└── tests/                           mirrors src, one module per source module
    ├── domain/  data/  integrations/  services/
```

Application code lives only under `VocabularyTrainer.V2/`. Nothing is written into `aidlc-docs/`,
and `VocabularyTrainer/` (v1) is never touched.

---

## U1 — Domain Core

**Type**: Module (pure logic)
**Stories**: none directly — underpins all of them
**Requirements**: FR-3.2, FR-3.3, FR-5.9, FR-6.3, FR-6.4, FR-6.7, FR-6.10, FR-8.9

**Scope**
- `domain/models.py` — every dataclass and enum the app exchanges
- `domain/natural_key.py` — the one definition of word identity
- `domain/lookup_priority.py` — definition selection and cross-source priority
- `domain/shuffle.py` — pool randomization and no-immediate-repeat reinsertion
- `domain/scoring.py` — answer matching, score, mastery, required attempts

**Why first**: everything else imports these types. It is also the highest-value unit to test, since
it holds the rules that must not vary between UI surfaces — and it needs no mocks at all.

**Definition of done**: all types defined; every pure function unit tested including edge cases
(empty pool, single-word pool, no part-of-speech match, no source answering, negative score).

---

## U2 — Master File Repository

**Type**: Module (persistence)
**Stories**: E8-S1, E8-S2, E8-S3, E8-S6
**Requirements**: FR-8.1, FR-8.3, FR-8.4, FR-8.5, FR-8.7, FR-8.9

**Scope**
- `data/master_file_repository.py` — workbook creation, header validation and repair, reads,
  natural-key lookup, word and collection mutations, cascading rename and delete
- `data/errors.py` — `MasterFileLockedError`, `MasterFileUnreadableError`
- The atomic write: temp file in the same directory, then swap, with cleanup on both paths
- The write lock serializing all mutating operations

**Why second, and why it carries the locked-file work separately**: this is technical risk #3 from the
execution plan — the one place where data loss would actually happen. Building it early against real
`.xlsx` fixtures means the atomic-swap and cascade behavior is proven before any UI depends on it.
File **watching** is deliberately deferred to U3 so this unit stays focused on correctness of writes.

**Definition of done**: workbook created with both sheets and a seeded General collection; headers
repaired with a report; cascade rename and delete verified to touch only the intended rows; atomic
write verified to leave the target fully old or fully new with no temp residue; concurrent mutation
verified serialized. Tested against real temporary workbook files, not mocks.

---

## U3 — Preferences, History, and File Watching

**Type**: Module (persistence)
**Stories**: E8-S5
**Requirements**: FR-6.16, FR-7.13, FR-8.2, FR-8.8

**Scope**
- `data/preferences_store.py` — JSON preferences with documented first-run defaults
- `data/history_store.py` — appending session records, failing without raising
- File watching added to the repository: detect external change, wait for writes to settle, signal

**Why separate from U2**: different concerns and different failure modes. Preferences and history are
small JSON files where a failure degrades quietly; the workbook is the system of record where a failure
must not lose data. Watching is grouped here because it is a notification concern, not a write concern.

**Definition of done**: preferences round-trip every field; defaults applied on first run; the API key
never appears in a log; history append returns False rather than raising on failure; watcher fires once
after a write settles rather than mid-write.

---

## U4 — Lookup Clients and Orchestration

**Type**: Module (integrations + one service)
**Stories**: E3-S1, E3-S2, E3-S3, E3-S4 (E3-S5's key-entry field is a Settings surface, so that story
is primary to U9; this unit supplies the skip-when-no-key behavior it relies on)
**Requirements**: FR-3.1 – FR-3.6, FR-3.8, FR-3.9, NFR-PERF-03, NFR-SEC-02

**Scope**
- `integrations/lookup_client.py` — the shared protocol
- Three clients: Free Dictionary, Merriam-Webster (unavailable without a key), Translate
- `services/lookup_service.py` — concurrent dispatch under a bounded per-source timeout, then
  priority selection via U1

**Definition of done**: each client returns candidates or an empty list and never raises; all
available clients run concurrently; a slow source cannot delay the result past the timeout; priority
selection verified for every combination of sources answering; no key means Merriam-Webster is simply
not used. Tested with stub clients and stubbed transports — no live network calls in tests.

---

## U5 — Feedback and OS Integration

**Type**: Module (integrations)
**Stories**: contributes to E6-S2, E7-S4, E1-S5
**Requirements**: FR-1.8, FR-6.5, FR-7.5

**Scope**
- `integrations/tts.py` — voice enumeration, selection, speech, quiet degradation
- `integrations/audio.py` — correct/incorrect sounds
- `integrations/startup_registration.py` — per-user startup entry, reporting success honestly

**Definition of done**: voices enumerate on a machine with voices installed; `speak` returns False
rather than raising when unavailable; sounds play without blocking; startup registration reports its
achieved state so the Settings toggle can revert.

---

## U6 — Application Services

**Type**: Module (orchestration)
**Stories**: contributes to E1–E7 (behavior beneath the UI)
**Requirements**: FR-2.5, FR-2.8, FR-2.9, FR-4.1 – FR-4.5, FR-4.8, FR-5.2 – FR-5.4, FR-5.7 – FR-5.9,
FR-6.6, FR-6.13 – FR-6.16, FR-7.3 – FR-7.13, FR-1.2 – FR-1.4, FR-1.6

**Scope**
- `services/collect_service.py` — save-then-patch, duplicate resolution, inline collection creation
- `services/practice_service.py` — collection list, pool, session, attempts, summary
- `services/settings_service.py` — preferences, master file path, collection CRUD
- `services/widget_state_service.py` — widget runtime state plus observer channel

**Why after U1–U5 and before any UI**: this is where the UI-independence claim gets proven. Every
service here is exercised by tests with no Qt application object in the process. If that is achievable,
the hybrid UI risk is largely defused, because both UI technologies become thin consumers.

**Definition of done**: every service unit tested with an in-memory repository fake, stub TTS and
audio, and a fixed clock; the save-then-patch ordering verified including the patch-after-delete case;
duplicate resolution verified to produce exactly one of three outcomes and never insert the incoming
word; search and sort verified independent of each other and of selection; the progress denominator
verified fixed across a session.

---

## U7 — Theme and Floating Widget Shell

**Type**: Module (UI, Qt)
**Stories**: E1-S1, E1-S2, E1-S3, E1-S4
**Requirements**: FR-1.1 – FR-1.7, NFR-UI-01, NFR-UI-02

**Scope**
- `ui/theme/` — the token source, plus generation of a Qt stylesheet and a CSS file from it
- `ui/widget/floating_widget_window.py` — frameless, translucent, always-on-top, draggable
- `ui/widget/widget_menu_popup.py` — the four-entry menu with edge flipping
- `ui/widget/tray_icon.py` — permanent fallback with the same menu

**Why this is the first UI unit**: technical risk #2. Per-pixel transparency plus always-on-top plus
drag is the most platform-sensitive thing in the product. Building it before the feature popups means a
fundamental problem surfaces while the approach can still change, rather than at integration time.
Generating both token formats from one source here also means the web layer inherits a proven theme.

**Definition of done**: widget renders with soft edges over the desktop, not a grey box; stays above
other windows; no taskbar entry; drag persists position and clamps onto a visible display; menu anchors
correctly and flips near edges; tray icon present whenever the app runs; the widget cannot hide when
the tray icon could not be created.

---

## U8 — Collect and Duplicate Popups

**Type**: Module (UI, Qt)
**Stories**: E2-S1, E2-S2, E2-S3, E2-S4, E4-S1, E4-S2, E4-S3, E4-S4, E8-S4
**Requirements**: FR-2.1 – FR-2.4, FR-2.6, FR-2.7, FR-2.10, FR-3.6, FR-3.7, FR-4.2, FR-4.6, FR-4.7

**Scope**
- `ui/widget/collect_card_popup.py` — word input, type chips, collection dropdown, inline creation,
  lookup status line, read-only result panel
- `ui/widget/duplicate_conflict_popup.py` — existing-entry context and the three actions

**Definition of done**: card anchors to the widget with focus in the word field; type chips are
single-select; Save enabled only with a word and a type; inline creation validates and returns to the
dropdown with the new collection selected; status line names the actual source and never says
"Cambridge"; conflict popup shows the existing collection and date; dismissal maps to Keep old; the
delete action's label makes clear neither entry survives.

---

## U9 — Practice and Settings Windows

**Type**: Module (UI, web-rendered)
**Stories**: E5-S1 – E5-S4, E6-S1 – E6-S6, E7-S1 – E7-S8, plus E1-S5 and E3-S5 (both surface as
Settings controls)
**Requirements**: FR-5.1 – FR-5.8, FR-6.1, FR-6.2, FR-6.5, FR-6.8, FR-6.9, FR-6.11, FR-6.12,
FR-6.14, FR-6.15, FR-7.1 – FR-7.12

**Scope**
- `ui/web/practice_window.py` + HTML/JS for the setup, drill, and summary screens
- `ui/web/settings_window.py` + HTML/JS for the five tabs
- `ui/web/bridge.py` — the `QWebChannel` surface exposed to JavaScript

**Why the largest unit is still one unit**: both windows share a single host mechanism and a single
bridge. Splitting them would duplicate that plumbing. Within the unit, Practice is built before
Settings because the drill is the harder interaction.

**Constraint**: the JavaScript layer captures input and renders state. Every decision is a service
call. No business logic crosses the bridge.

**Definition of done**: markup derived from the mockups renders with the shared token set; setup
search and sort work and preserve checks; Start disabled on an empty pool; the drill never reveals the
word before submission; a miss reveals the spelling and waits for Next; score and mastery dots update
live; End session and window close both route to the summary; all five Settings tabs functional
including the delete confirmation stating the exact word count.

---

## U10 — Composition Root and Startup

**Type**: Module (wiring)
**Stories**: none primary — contributes the startup path to E1-S1, E1-S5, and E8-S1
**Requirements**: FR-1.4, FR-1.8, FR-8.1, FR-8.2, FR-8.8

**Scope**
- `services/app_context.py` — construct and wire the entire object graph
- `__main__.py` — entry point
- The ten-step startup sequence from `services.md`
- Shutdown: stop the watcher, cancel background tasks, flush pending preference writes
- `README.md` — run, build, and test instructions

**Definition of done**: the app starts from a clean machine state, creates its workbook, applies
preferences, shows the tray icon and widget, and shuts down without leaving orphaned temp files or
background threads.

---

## Unit Summary

| Unit | Name | Type | Stories | Risk addressed |
|---|---|---|---|---|
| U1 | Domain Core | pure logic | — | — |
| U2 | Master File Repository | persistence | 4 | #3 atomic writes / locked file |
| U3 | Preferences, History, Watching | persistence | 1 | — |
| U4 | Lookup Clients & Orchestration | integrations | 4 | — |
| U5 | Feedback & OS Integration | integrations | — | — |
| U6 | Application Services | orchestration | — | #1 hybrid UI (proves UI-independence) |
| U7 | Theme & Widget Shell | UI (Qt) | 4 | #2 transparent overlay |
| U8 | Collect & Duplicate Popups | UI (Qt) | 9 | — |
| U9 | Practice & Settings Windows | UI (web) | 20 | #1 hybrid UI (the other half) |
| U10 | Composition Root & Startup | wiring | — | — |

Primary story assignments: U2=4, U3=1, U4=4, U7=4, U8=9, U9=20 -> **42 total**. U1, U5, U6, and U10
are enabling units with no primary stories — no user observes "the service layer" directly, so their
stories are primary to the UI unit that completes them. Consequence worth noting: those four units
cannot be validated by acceptance criteria and rest entirely on unit tests, which is why the coverage
gate matters most for U1, U4, and U6. `unit-of-work-story-map.md` is the authoritative mapping.
