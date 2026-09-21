# Application Design — Vocabulary Trainer v2

Consolidated design document. Detail lives in the companion files:
`components.md`, `component-methods.md`, `services.md`, `component-dependency.md`.

---

## 1. Architectural Overview

A single-process Python desktop application, layered so that all business logic sits below and
independent of the UI.

```
+-----------------------------------------------------------+
|  UI LAYER                                                 |
|  Qt widgets: widget, menu, collect card, conflict, tray   |
|  QWebEngineView: Practice window, Settings window         |
+-----------------------------------------------------------+
                        | depends on
                        v
+-----------------------------------------------------------+
|  SERVICE LAYER                                            |
|  Collect | Lookup | Practice | Settings | WidgetState      |
|  AppContext (composition root)                            |
+-----------------------------------------------------------+
          |                            |
          v                            v
+---------------------------+  +----------------------------+
|  DATA LAYER               |  |  INTEGRATION LAYER         |
|  MasterFileRepository     |  |  3 lookup clients          |
|  PreferencesStore         |  |  TTS | Audio | Startup     |
|  HistoryStore             |  |                            |
+---------------------------+  +----------------------------+
          |                            |
          v                            v
+-----------------------------------------------------------+
|  DOMAIN LAYER (pure: no I/O, no framework imports)        |
|  models | natural_key | lookup_priority | shuffle | scoring|
+-----------------------------------------------------------+
```

**The single rule that shapes everything**: dependencies point downward only. Nothing below the UI
layer imports anything from it.

Two things follow, and both are requirements rather than preferences:

1. Business logic is testable without a display, a Qt application object, or a window
   (NFR-TEST-01).
2. The two UI technologies consume one shared service layer, so neither can grow its own copy of
   duplicate detection, scoring, or persistence. This was the main risk flagged in the execution plan.

---

## 2. Hybrid UI Split

| Surface | Technology | Why |
|---|---|---|
| Floating widget, its menu, Collect card, duplicate conflict popup, tray icon | PySide6 widgets | Requires a frameless, per-pixel-translucent, always-on-top, draggable window — the one thing an embedded web view cannot do cleanly. Popups are Qt too so they anchor to the widget and share its idle/active state |
| Practice window (setup, drill, summary), Settings window (five tabs) | `QWebEngineView` + `QWebChannel` | Document-like, layout-heavy screens that already exist as mockups. Reusing the HTML/CSS is what makes strict visual fidelity (NFR-UI-01) achievable without hand-building every card, and removes any translation step between design and implementation |

**Design constraint on the bridge**: JavaScript captures input and renders state. Every decision is a
Python service call. No business logic crosses into the web layer, so the web views stay replaceable.

**Theme tokens are generated from one source** into both a Qt stylesheet and a CSS file, so the two
surfaces cannot drift apart visually.

### Deviation from the recorded technology decision

Requirements Analysis recorded *"WebView2 via pywebview"*. Design work found this unworkable:
`pywebview` and Qt each own a blocking main event loop, and one process cannot run both without
fragile interleaving that would compromise exactly the widget responsiveness the product depends on
(FR-1.9, NFR-PERF-01).

`QWebEngineView` preserves the substance of the decision — mockup HTML as the real UI, Python as the
whole backend, one native app, no server, no browser, no `localhost` — under a single Qt event loop.
It also removes the external WebView2 runtime prerequisite, which retired NFR-PLAT-02.
Cost: `PySide6-Addons` is a large dependency, accepted for a Windows desktop app with no stated
install-size constraint.

`requirements.md`, `aidlc-state.md`, and the deviation note in
`inception/plans/application-design-plan.md` all record this; the outdated text was replaced rather
than left standing alongside.

---

## 3. Components at a Glance

### Domain — pure, no I/O
| Component | Owns |
|---|---|
| `models` | All exchanged data structures |
| `natural_key` | The single definition of word identity (FR-8.9) |
| `lookup_priority` | Which definition and which source wins (FR-3.2, FR-3.3) |
| `shuffle` | Pool randomization and no-immediate-repeat reinsertion (FR-5.9, FR-6.7) |
| `scoring` | Answer matching, mastery, penalties, score (FR-6.4 – FR-6.10) |

### Data
| Component | Owns |
|---|---|
| `MasterFileRepository` | Every workbook read and write; atomic swaps; write serialization; header repair; file watching |
| `PreferencesStore` | JSON preferences under `%AppData%` |
| `HistoryStore` | JSON practice-session history |

### Integrations
| Component | Owns |
|---|---|
| `FreeDictionaryClient`, `MerriamWebsterClient`, `TranslateClient` | One `LookupClient` protocol each; return candidates or nothing, never raise |
| `TextToSpeechService` | Voice enumeration and speech, degrading quietly |
| `AudioFeedbackService` | Correct/incorrect sounds |
| `StartupRegistration` | Per-user start-with-Windows entry |

### Services
| Component | Owns |
|---|---|
| `CollectService` | Capture, duplicate resolution, inline collection creation |
| `LookupService` | Concurrent fetch across available clients, priority selection |
| `PracticeService` | Collection list, pool, in-flight session, summary |
| `SettingsService` | Preferences, master file path, collection CRUD |
| `WidgetStateService` | Widget runtime state plus observer notification |
| `AppContext` | Composition root, startup sequence, reload signal |

---

## 4. Design Decisions and Their Reasons

| Decision | Reason |
|---|---|
| One repository for the whole workbook, not one per entity | FR-8.5/FR-8.7 need atomic, serialized writes to a single file. Two repositories would each need their own swap logic and a shared lock. Cascading rename and delete span both sheets in one write, which split repositories could not express without a transaction concept |
| Selection logic in `domain.lookup_priority`, not in `LookupService` | The branching (no part-of-speech match, several sources answering, none answering) is where bugs live. Pure and isolated means exhaustively testable with no network |
| Cascade rename/delete as one repository call | FR-7.9 forbids leaving rows inconsistent. Doing it in one atomic write means there is no partial state to revert, rather than reverting one after the fact |
| `WidgetStateService` as a service, not view state | The same state is shown in three places (widget, its menu, Settings). Observation removes any direct coupling between them |
| Toggles return their achieved state | A toggle showing "on" while registration silently failed is a lie the UI would display. `set_start_with_windows` and `set_character` report reality so the view can revert |
| `Clock` injected | FR-2.8 stamps dates and FR-6.14 measures elapsed time. Without injection both are untestable without sleeping |
| `patch_word_enrichment` returns a bool | A lookup finishing after its row was deleted must not resurrect the row (E2-S4 branch 6c) |
| Progress denominator fixed at session start | Words leave the pool as they are mastered. A live denominator would make the bar jump backward |
| Lookup clients never raise | Failure is normal here (offline, no entry, timeout). Returning empty keeps the orchestrator free of exception plumbing |

---

## 5. Concurrency Model

| Concern | Approach |
|---|---|
| Dictionary lookups | All available clients dispatched concurrently under a bounded per-source timeout. Results gathered, then priority-selected. A slow source cannot stall the others (FR-3.1, NFR-PERF-03) |
| UI responsiveness | No network or file I/O on the UI thread. Lookups return an observable handle the UI reacts to (FR-1.9, NFR-PERF-01) |
| Workbook writes | Serialized through a single lock in the repository, so no two mutating operations overlap (FR-8.7) |
| Write atomicity | Write to a temp file in the same directory, then swap. The target is only ever fully old or fully new. Temp files cleaned up on success and failure, and orphans removed at next launch (FR-8.5) |
| External file changes | Watched; the app waits for writes to settle before reloading, then signals views. An in-flight practice session keeps its original pool; unsaved Collect input is preserved (FR-8.8) |

---

## 6. Error Handling Strategy

Errors are translated at the service boundary. Raw file-system, HTTP, or library exceptions never
reach the UI (NFR-REL-01).

| Error | Raised by | UI response |
|---|---|---|
| `MasterFileLockedError` | repository | Hold the pending change in memory, explain the file is open elsewhere, offer Retry (FR-8.6) |
| `MasterFileUnreadableError` | repository | Reject a path change, keep the previous path in effect (E7-S2 branch 4b) |
| `ValidationError` | services | Inline message beside the offending field; nothing written |
| `EmptyPoolError` | `PracticeService` | Should be unreachable — `can_start()` disables the button first. Defensive backstop (FR-5.8) |
| Lookup failure | never raised | Empty result; the word saves with blank Meaning and Example (FR-3.5) |
| TTS unavailable | never raised | `speak()` returns False; the success sound still plays (E7-S4 branch) |
| History write failure | never raised | `append()` returns False; the summary still displays (E6-S6 branch 4a) |

The pattern: failures that the user must act on become typed errors; failures the user can do nothing
about degrade quietly and never interrupt.

---

## 7. Requirements Coverage

All 74 functional requirements map to at least one component. Full traceability is in the companion
files; summarized by epic:

| Epic | Primary components |
|---|---|
| E1 Widget & presence | `FloatingWidgetWindow`, `WidgetMenuPopup`, `TrayIcon`, `WidgetStateService`, `StartupRegistration` |
| E2 Collect | `CollectCardPopup`, `CollectService`, `MasterFileRepository` |
| E3 Lookup | `LookupService`, three clients, `domain.lookup_priority` |
| E4 Duplicates | `DuplicateConflictPopup`, `CollectService`, `domain.natural_key` |
| E5 Practice setup | `PracticeWindow`, `PracticeService`, `domain.shuffle` |
| E6 Drill & summary | `PracticeWindow`, `PracticeService`, `domain.scoring`, TTS, Audio, `HistoryStore` |
| E7 Settings | `SettingsWindow`, `SettingsService`, `PreferencesStore` |
| E8 Persistence | `MasterFileRepository` |

Non-functional coverage:

| NFR group | How the design addresses it |
|---|---|
| UI (01–04) | `ui.theme` generates Qt and CSS token sets from one source; web views reuse mockup markup |
| Performance (01–03) | Background lookups, bounded timeouts, no I/O on the UI thread |
| Reliability (01–03) | Atomic swaps, typed errors, quiet degradation, confirmation on destructive actions |
| Security (01–02) | API key in preferences only, never logged; outbound calls limited to three endpoints, carrying only the word |
| Testability (01–03) | Downward-only dependencies, injected `Clock`, repository protocol for fakes, real `.xlsx` fixtures |
| Accessibility (01) | Recorded scope reduction; no additional work planned |
| Platform (01) | Windows 10 1809+ / 11 x64. **NFR-PLAT-02 retired** — no external runtime prerequisite remains |

---

## 8. Project Structure

```
VocabularyTrainer.V2/
├── pyproject.toml
├── README.md
├── src/vocabulary_trainer/
│   ├── __main__.py                  entry point
│   ├── domain/
│   │   ├── models.py
│   │   ├── natural_key.py
│   │   ├── lookup_priority.py
│   │   ├── shuffle.py
│   │   └── scoring.py
│   ├── data/
│   │   ├── master_file_repository.py
│   │   ├── preferences_store.py
│   │   ├── history_store.py
│   │   └── errors.py
│   ├── integrations/
│   │   ├── lookup_client.py         protocol
│   │   ├── free_dictionary_client.py
│   │   ├── merriam_webster_client.py
│   │   ├── translate_client.py
│   │   ├── tts.py
│   │   ├── audio.py
│   │   └── startup_registration.py
│   ├── services/
│   │   ├── app_context.py
│   │   ├── collect_service.py
│   │   ├── lookup_service.py
│   │   ├── practice_service.py
│   │   ├── settings_service.py
│   │   └── widget_state_service.py
│   ├── ui/
│   │   ├── theme/                   token source, generated .qss and .css
│   │   ├── widget/                  Qt windows and popups
│   │   └── web/                     QWebEngineView hosts, HTML, JS bridge
│   └── assets/
│       ├── floating_widget/         character PNGs
│       ├── fonts/                   Google Sans TTFs
│       └── sounds/                  correct / incorrect
└── tests/
    ├── domain/
    ├── data/
    ├── integrations/
    └── services/
```

Application code sits under `VocabularyTrainer.V2/`, never in `aidlc-docs/`.

---

## 9. Open Design Points Deferred to Functional Design

Deliberately left for per-unit Functional Design, where they belong:

1. The exact openpyxl write sequence that preserves both sheets on round-trip.
2. The reinsertion index distribution in `reinsert_avoiding_next` — any non-zero index, or weighted.
3. The concrete JSON shapes for the preferences and history files.
4. The `QWebChannel` method surface exposed to JavaScript, per web view.
5. Debounce timing for the file watcher's settle detection.
