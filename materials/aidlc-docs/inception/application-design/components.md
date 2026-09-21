# Components — Vocabulary Trainer v2

Components are grouped into five layers. The dependency rule is strictly one-way: **UI -> Services ->
Domain <- Data / Integrations**. Nothing in Domain, Data, Services, or Integrations imports anything
from UI. This is what makes NFR-TEST-01 structural rather than aspirational, and it is what keeps the
two UI technologies from growing divergent copies of the same behavior.

```
+-----------------------------------------------------------+
|  UI LAYER                                                 |
|  Qt widgets (widget, popups) | QWebEngineView (Practice,  |
|                              |   Settings)                |
+-----------------------------------------------------------+
                        | depends on
                        v
+-----------------------------------------------------------+
|  SERVICE LAYER                                            |
|  Collect | Practice | Settings | WidgetState | Feedback   |
+-----------------------------------------------------------+
          | depends on            | depends on
          v                       v
+---------------------+  +--------------------------------+
|  DATA LAYER         |  |  INTEGRATION LAYER             |
|  MasterFileRepo     |  |  Lookup clients | TTS | Audio  |
|  PreferencesStore   |  |                                |
|  HistoryStore       |  |                                |
+---------------------+  +--------------------------------+
          |                       |
          v                       v
+-----------------------------------------------------------+
|  DOMAIN LAYER (pure, no I/O, no framework imports)        |
|  Models | NaturalKey | LookupPriority | Shuffle | Scoring |
+-----------------------------------------------------------+
```

---

## Domain Layer

Pure Python. No file access, no network, no Qt imports. Every component here is directly unit
testable and holds the rules that must not vary between UI surfaces.

### `domain.models`
**Purpose**: The data structures the whole application exchanges.

**Responsibilities**
- Define `WordEntry`, `Collection`, `CollectionSummary`, `PartOfSpeech`, `LookupResult`,
  `LookupSource`, `DuplicateAction`, `PracticeWordState`, `SessionSummary`, `AppPreferences`,
  `WidgetState`, `CharacterKind`, `CollectionSortMode`.
- Expose the natural key of a `WordEntry` as a derived value, so no caller re-implements the rule.
- Carry no behavior beyond value semantics and derived properties.

**Interface**: dataclasses and enums, immutable where practical.

### `domain.natural_key`
**Purpose**: The single definition of when two entries are the same word.

**Responsibilities**
- Normalize a word and a collection name into a comparable key (case-folded, whitespace-trimmed).
- Provide the equality test used by duplicate detection and by repository lookups.

**Why it is its own component**: FR-8.9 and FR-4.1 depend on one consistent rule. If normalization
lived in both the repository and the duplicate detector, the two could drift and duplicates would be
detected inconsistently depending on the code path.

### `domain.lookup_priority`
**Purpose**: Decide which lookup result to keep when several arrive.

**Responsibilities**
- Given results from any subset of sources, select the highest-priority non-empty one
  (Free Dictionary > Merriam-Webster > Google Translate).
- Given a source's entries and a requested part of speech, choose the matching definition, falling
  back to the first available.

**Why it is separate from the lookup service**: this is the part with real branching and edge cases
(FR-3.2, FR-3.3) and it is pure. Isolating it means it can be exhaustively tested without any
network.

### `domain.shuffle`
**Purpose**: Practice pool ordering.

**Responsibilities**
- Shuffle a pool into random order (FR-5.9).
- Reinsert a not-yet-mastered word at a position other than the immediate next draw, when the pool
  holds more than one word (FR-6.7).

### `domain.scoring`
**Purpose**: The practice session state machine.

**Responsibilities**
- Judge an answer against a target word (case-insensitive, trimmed) — FR-6.4.
- Apply a correct attempt: increment consecutive-correct, decide mastery, update score — FR-6.5,
  FR-6.6.
- Apply an incorrect attempt: add a penalty, leave consecutive-correct untouched — FR-6.8.
- Compute score as correct attempts minus penalties, and total required attempts as pool size times
  required writes — FR-6.3, FR-6.10.

**Invariant it owns**: an incorrect answer can never reduce a word's mastery progress. This is the
rule most likely to be broken by a careless edit, so it lives in one tested place.

---

## Data Layer

Owns all persistence. Every write goes through the atomic swap.

### `data.master_file_repository`
**Purpose**: The only component that reads or writes the Excel workbook.

**Responsibilities**
- Create a correctly structured workbook with both sheets and a seeded General collection
  (FR-8.1).
- Validate and auto-repair header rows, reporting what changed (FR-8.3, FR-8.4).
- Read all words and collections; look up by natural key (FR-8.9).
- Insert, patch, and delete word rows.
- Create, rename (cascading to word rows), and delete (cascading to word rows) collections
  (FR-7.9, FR-7.11).
- Perform every write as a temp-file-then-swap so the target is never partially written (FR-8.5).
- Serialize all mutating operations so no two overlap (FR-8.7).
- Detect a locked file and raise a distinguishable error so the caller can offer Retry (FR-8.6).
- Watch the file for external modification and signal that a reload is needed (FR-8.8).

**Interface**: a repository protocol so services can be tested against an in-memory fake.

**Note on the Excel library**: openpyxl alone. The design originally called for pandas on the
read path with openpyxl writing, but this component needs cell-level access across both sheets
— repairing a header row in place, preserving columns the user added, deleting individual rows
— and a DataFrame round-trip cannot do that without rewriting whole sheets. That would be
actively harmful for a workbook the product describes as hand-editable. The choice is contained
entirely within this component; no other component knows which library is in use.

### `data.preferences_store`
**Purpose**: Persist user preferences as JSON under `%AppData%`.

**Responsibilities**
- Load and save widget visibility, position, character, TTS voice, master file path,
  Merriam-Webster API key, and start-with-Windows (FR-7.13).
- Supply documented defaults on first run.
- Never write the API key to a log or an error message (NFR-SEC-01).

### `data.history_store`
**Purpose**: Persist practice session results as JSON under `%AppData%`.

**Responsibilities**
- Append a completed session's score, words practiced, penalties, elapsed time, and timestamp
  (FR-6.16).
- Fail without blocking the summary from displaying.

**Explicitly does not**: write anything into the master workbook. FR-6.16 keeps the workbook a clean
word list.

---

## Integration Layer

Everything that talks to the outside world.

### `integrations.free_dictionary_client`
**Purpose**: Query `api.dictionaryapi.dev`.
**Responsibilities**: issue the request under a bounded timeout, parse the JSON into candidate
entries with parts of speech, return an empty result on any failure rather than raising.

### `integrations.merriam_webster_client`
**Purpose**: Query the Merriam-Webster Dictionary API.
**Responsibilities**: as above, plus report itself unavailable when no API key is configured so the
orchestrator can simply not use it (FR-3.8).

### `integrations.translate_client`
**Purpose**: Translate EN to VI.
**Responsibilities**: return the translation as a meaning with no example (FR-3.4); empty result on
failure.

All three implement one `LookupClient` protocol: a name, an availability check, and a fetch that
returns candidate entries or nothing. None of them decides which result wins — that is
`domain.lookup_priority`.

### `integrations.tts`
**Purpose**: Speak a word aloud.
**Responsibilities**: enumerate installed voices, speak using the selected voice, degrade quietly
when no voice exists or speech fails (FR-7.5, FR-6.5, E7-S4 branches).

### `integrations.audio`
**Purpose**: Play the correct/incorrect feedback sounds.
**Responsibilities**: play short bundled sounds without blocking the drill.

### `integrations.startup_registration`
**Purpose**: Register or remove the start-with-Windows entry.
**Responsibilities**: write or remove a per-user startup entry; report failure so the toggle can
revert rather than showing on while doing nothing (FR-1.8, E1-S5 branch 4a).

---

## Service Layer

Orchestration. Services coordinate domain, data, and integration components, and are the only thing
the UI is allowed to talk to.

### `services.collect_service`
Coordinates the whole capture flow: duplicate detection, concurrent lookup, immediate save,
later patch, duplicate resolution, and inline collection creation.
**Requirements**: FR-2.5, FR-2.8, FR-2.9, FR-3.1, FR-3.3, FR-4.1, FR-4.3, FR-4.4, FR-4.5.

### `services.practice_service`
Owns the collection list (search and sort), pool construction, session lifecycle, attempt
submission, and summary production.
**Requirements**: FR-5.2, FR-5.3, FR-5.4, FR-5.7, FR-5.8, FR-5.9, FR-6.3, FR-6.6, FR-6.7,
FR-6.10, FR-6.13, FR-6.14, FR-6.16.

### `services.settings_service`
Owns preference reads and writes, the master file path change, and collection CRUD with its
validation and cascade semantics.
**Requirements**: FR-7.3 through FR-7.13, FR-8.2.

### `services.widget_state_service`
Owns the widget's runtime state: idle versus active, position, visibility, and character. Notifies
observers on change so the widget view and the Settings view stay in sync.
**Requirements**: FR-1.2, FR-1.3, FR-1.4, FR-1.6, FR-7.4.

### `services.app_context`
The composition root's product: constructs every component once, wires the dependencies, and hands
services to the UI. Also owns first-run workbook creation and the reload-on-external-change signal.

---

## UI Layer

### Qt widget views (`ui.widget`)
`FloatingWidgetWindow`, `WidgetMenuPopup`, `CollectCardPopup`, `DuplicateConflictPopup`,
`TrayIcon`.

**Why Qt widgets and not HTML here**: the floating widget needs a frameless, per-pixel-translucent,
always-on-top window that is draggable — the one requirement an embedded web view cannot satisfy
cleanly. The popups are Qt too, so they can anchor to the widget and share its active/idle state.

**Requirements**: FR-1.1 through FR-1.7, FR-2.1 through FR-2.7, FR-2.10, FR-3.6, FR-3.7,
FR-4.2, FR-4.6, FR-4.7.

### Web-rendered views (`ui.web`)
`PracticeWindow` (setup, drill, summary screens) and `SettingsWindow` (five tabs), each a
`QWebEngineView` loading local HTML derived from `mockup/`, bridged to Python by `QWebChannel`.

**Why HTML here**: these are document-like, layout-heavy screens that already exist as mockups.
Reusing them is what makes strict visual fidelity (NFR-UI-01) achievable without hand-building every
card, and it removes any translation step between the design and the implementation.

**The bridge holds no business logic.** JavaScript captures input and renders state; every decision
is a Python service call.

**Requirements**: FR-5.1 through FR-5.8, FR-6.1, FR-6.2, FR-6.4, FR-6.5, FR-6.8, FR-6.9,
FR-6.11, FR-6.12, FR-6.14, FR-6.15, FR-7.1 through FR-7.12.

### `ui.theme`
The `mockup/styles.css` token set in two forms: a Qt stylesheet for the widget layer and a CSS file
for the web layer, both generated from one source list of tokens so the two surfaces cannot drift
apart (NFR-UI-01, NFR-UI-02).
