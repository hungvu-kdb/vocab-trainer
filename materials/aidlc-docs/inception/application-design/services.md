# Services — Vocabulary Trainer v2

Services are the only layer the UI may call. Each owns one user-facing capability area, coordinates
domain rules with data and integration components, and never imports UI code.

---

## Design rules that apply to all services

1. **Dependencies are injected**, never constructed internally and never resolved from a global.
   Every service is testable with in-memory fakes.
2. **Services hold no persistent state that belongs in the data layer.** The exception is
   `PracticeService`, which owns the in-flight session — deliberately transient, because a session is
   not persisted until it ends.
3. **Services never block the UI thread.** Network work is dispatched to background tasks; results
   arrive via callbacks or observable handles.
4. **Errors are translated at the service boundary.** Raw file-system, HTTP, or library exceptions
   never reach the UI. Services raise a small set of intentional errors carrying user-facing messages
   (NFR-REL-01).

---

## `CollectService`

**Owns**: the capture flow end to end.

**Depends on**: `MasterFileRepository`, `LookupService`, `Clock`.

**Orchestration — the save path**

The ordering here is the whole point of the service, and it is what makes FR-2.8's "save
immediately" compatible with FR-3.1's concurrent lookup:

```
1. UI reports word + part of speech entered
2. begin_lookup() dispatches all available clients concurrently -> returns a handle
   (UI is never blocked; the handle is observable)
3. UI reports save requested
4. check_duplicate() runs against the repository
   |
   +-- duplicate found  -> return DUPLICATE_DETECTED; write nothing; UI shows conflict popup
   |
   +-- no duplicate     -> insert_word() now, using whatever the handle currently holds
                           (Meaning/Example may be blank)
5. When the lookup handle later completes:
   patch_word_enrichment() on the same natural key
   |
   +-- row still present -> Meaning/Example filled in
   +-- row gone          -> abandon quietly; never recreate a deleted row
```

**Orchestration — duplicate resolution**

One entry point, `resolve_duplicate`, switching on the action. The invariant it enforces (FR-4.8) is
that exactly one of three outcomes occurs and the incoming word is never separately inserted:

| Action | Repository call | Incoming word |
|---|---|---|
| `KEEP_OLD` | none | discarded |
| `REPLACE` | `replace_word` — Meaning/Example/Date only | consumed by the replace, not inserted |
| `DELETE_BOTH` | `delete_word` | discarded |

Dismissal without a choice is mapped by the UI to `KEEP_OLD` before it reaches the service, so the
service never has to model "no decision".

**Errors raised**: `ValidationError` (inline collection name empty or colliding),
`MasterFileLockedError` (propagated so the UI can offer Retry with the entry preserved).

---

## `LookupService`

**Owns**: running the three sources and picking a winner.

**Depends on**: a sequence of `LookupClient` implementations, a timeout value.

**Orchestration**

```
1. Filter clients to those reporting is_available()
   (drops Merriam-Webster when no API key is set — FR-3.8)
2. Dispatch every remaining client concurrently, each under the bounded timeout
3. Gather results; a timeout or failure counts as "no answer", never an exception
4. For each source that answered, ask domain.lookup_priority.select_definition()
   for the entry best matching the requested part of speech
5. Ask domain.lookup_priority.select_result() to pick across sources by priority
6. Return the winner, or an empty LookupSource.NONE result if nobody answered
```

**Why the selection logic is not in this service**: steps 4 and 5 are pure branching with many edge
cases (no part-of-speech match, several sources answering, none answering). Keeping them in
`domain.lookup_priority` means they are exhaustively unit testable without a network stub, and this
service stays a thin concurrency coordinator.

**Concurrency note**: all three run in parallel and the slowest cannot hold up the others past the
timeout. This is the CQ2 = B decision, and it is why the service gathers rather than short-circuits.

---

## `PracticeService`

**Owns**: the collection picker's data, the pool, the in-flight session, and the summary.

**Depends on**: `MasterFileRepository`, `HistoryStore`, `TextToSpeechService`,
`AudioFeedbackService`, `Clock`.

**Orchestration — setup**

`list_collections(search, sort)` composes two independent operations: filter by case-insensitive
substring, then order by the chosen mode. Neither touches which collections the user has checked —
selection lives in the UI and is passed back in as names. This separation is what makes E5-S2's
"a checked collection filtered out of view stays checked" fall out naturally instead of needing
special handling.

**Orchestration — the drill loop**

```
start_session(names, required_correct)
  -> gather words from the named collections
  -> reject an empty pool (EmptyPoolError)
  -> domain.shuffle.shuffled() to randomize
  -> record total_required_attempts = pool_size x required_correct  [fixed for the session]

submit_attempt(answer)
  -> domain.scoring.answer_matches()
     |
     +-- correct   -> audio.play_correct(); tts.speak(word)
     |               increment consecutive_correct; score += 1
     |               |
     |               +-- reached required -> master it; remove from pool
     |               +-- still short      -> domain.shuffle.reinsert_avoiding_next()
     |
     +-- incorrect -> audio.play_incorrect()
                     penalties += 1; consecutive_correct UNCHANGED
                     word stays in the pool
                     outcome carries the correct spelling for the reveal
  -> return AttemptOutcome

advance()          -> next word (used after a miss, which waits for acknowledgement)
end_session()      -> SessionSummary; history.append(); failure to append does not
                      block the summary from being shown
```

**The invariant this service protects**: an incorrect attempt must never reduce
`consecutive_correct`. It is delegated to `domain.scoring` rather than implemented inline, precisely
because it is the rule most easily broken by a later edit.

**Progress semantics**: the denominator is captured once at session start. As words are mastered the
pool shrinks, but the denominator does not, so the bar advances monotonically instead of jumping
backward — the concrete reason E6-S5 branch 2a exists.

---

## `SettingsService`

**Owns**: preferences, the master file location, and collection lifecycle management.

**Depends on**: `MasterFileRepository`, `PreferencesStore`, `WidgetStateService`,
`TextToSpeechService`.

**Orchestration — collection rename (the interesting one)**

FR-7.9 requires that a rename cascade to every word row and that a partial failure leave nothing
inconsistent. Rather than renaming and then patching rows — which can fail halfway — the service
delegates to a single repository call that performs both changes inside one atomic write. Either the
whole rename lands or none of it does. There is no partial state to revert, because a partial state
is never written.

**Orchestration — collection delete**

```
word_count_for_deletion(name)   -> exact count, shown in the confirmation dialog
                                   (the dialog must state a real number, not an estimate)
[user confirms]
delete_collection(name)         -> collection + its word rows, one atomic write
                                -> if it was the last collection, re-seed General so
                                   Collect always has a destination
```

**Toggle honesty**: `set_start_with_windows` and `set_character` both return the achieved state
rather than `None`. A toggle that reports success while the underlying registration failed is a lie
the UI would then display, so the service reports what actually happened and the view reverts.

---

## `WidgetStateService`

**Owns**: the widget's runtime state, and notifying anyone who displays it.

**Depends on**: `PreferencesStore`.

**Why this is a service and not just fields on the widget view**: the same state is displayed and
mutated from three places — the widget itself, its menu's toggle, and the Settings Widget tab. If the
view owned the state, those three would have to push updates to each other. Instead each observes
this service, so switching the widget off from Settings updates the menu's toggle with no direct
coupling between them (E1-S4's "the two stay in sync").

**Observer channel**: `subscribe()` returns an unsubscribe callable. This is the one place an
event-style pattern is used, and it is justified because the notification genuinely is
one-to-many with no return value.

---

## `AppContext` — the composition root

**Owns**: construction and wiring. It is the only place that knows the full object graph.

**Startup sequence**

```
1. Load preferences (defaults on first run)
2. Resolve the master file path from preferences
3. MasterFileRepository.ensure_workbook()
     -> create with both sheets + seeded General if absent   (FR-8.1)
     -> validate and auto-repair headers, capturing a report (FR-8.4)
4. Construct the data, integration, and domain-facing components
5. Construct the lookup clients; Merriam-Webster reports itself unavailable
   when no key is configured
6. Construct the services, injecting their dependencies
7. Apply preferences to WidgetStateService and TextToSpeechService
8. Start the master-file watcher                              (FR-8.8)
9. Construct the tray icon, then the floating widget window
   -> if the tray icon cannot be created, the widget is not permitted to hide,
      so the app can never become unreachable                 (E1-S4 branch 4a)
10. Surface any header-repair report to the user
```

**Shutdown**: stop the watcher, stop background tasks, persist any pending preference writes.

**Reload signal**: `on_data_reloaded` fires after an external file change has been absorbed. Views
subscribe so that open screens refresh their collection lists and counts — while explicitly
preserving unsaved input in an open Collect card, and explicitly not disturbing an in-flight
practice session (E8-S5 branches).

---

## Service interaction map

| Caller | Calls | For |
|---|---|---|
| Widget / Collect popups | `CollectService` | capture, duplicate resolution, inline collection creation |
| Widget / menu / tray | `WidgetStateService` | idle-active state, position, visibility, character |
| Practice window | `PracticeService` | collection list, pool, drill, summary |
| Settings window | `SettingsService` | preferences, master file, collections CRUD |
| `CollectService` | `LookupService`, `MasterFileRepository` | enrichment, persistence |
| `PracticeService` | `MasterFileRepository`, `HistoryStore`, TTS, Audio | pool, history, feedback |
| `SettingsService` | `MasterFileRepository`, `PreferencesStore`, `WidgetStateService`, TTS | all of the above |
| `LookupService` | three `LookupClient`s, `domain.lookup_priority` | concurrent fetch, selection |

No cycles: `SettingsService` calls `WidgetStateService`, and `WidgetStateService` never calls back.
