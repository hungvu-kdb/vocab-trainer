# Vocabulary Trainer v3 — Consolidated Project Reference

> **Purpose of this file**: everything needed to understand and continue work on this
> product from inside `VocabularyTrainer.V3/` alone — business context, feature
> behavior, and technical design.
>
> **This folder is now self-contained.** The reference materials it was built from
> (mockups, character artwork, numbered requirements, user stories, personas, the
> original spec) were copied into `materials/` — see `materials/README.md` for what
> each one is and how far to trust it. The superseded v1 and v2 implementations were
> archived to `../archive/` and frozen; do not use them as a reference, since both are
> now behind this codebase.
>
> **Source of truth going forward**: this file, for this folder. It was consolidated
> from the living spec (now at `materials/specs/output_specs.md`), requirements
> (`materials/aidlc-docs/inception/requirements/requirements.md`), personas
> (`materials/aidlc-docs/inception/user-stories/personas.md`), and the actual v3
> source code, as of the date below. If code and this file ever disagree, trust the
> code and fix this file — but nothing was outstanding at the time of writing
> (757 tests passing).
>
> **Last consolidated**: 2026-09-13, against `VocabularyTrainer.V3/src` as it stands
> after: v2→v3 copy, package rename to `vocab-v2`, manual-meaning toggle (FR-2.11/12),
> widget menu width fix, offline dictionary source (FR-3.1/3/5/6/8 revision), widget
> Quit action (FR-1.10), the Collections preview table (FR-7.14), and the separate
> practice-log workbook (FR-6.17/18/19), background-lookup hand-off on save (FR-2.9 fix), and the Practice-mode collection preview (FR-5.10).

---

## Part 1 — Business Context

### 1.1 What this product is

A Windows desktop application that helps a user build and practice an English
vocabulary list. Two pillars:

- **Learn** — a lightweight, always-on-top floating widget ("mini-ani") for capturing
  new words the moment the user encounters them, with automatic dictionary lookup or
  a manually typed meaning.
- **Practice** — a native writing-drill window that tests recall of previously
  collected words, organized by collection, with scoring and audio feedback.

All vocabulary data lives in a single, human-editable **Excel master file** — the
user can open and hand-edit it at any time without breaking the app.

### 1.2 Who it's for — two personas, one person

The personas are the same individual in two different mental states. Their needs
actively conflict, which is why several design decisions exist (the widget
show/hide toggle plus a permanent tray-icon fallback is the sharpest example).

**Persona 1 — "The Collector"**
- Mode: mid-task (reading, watching, working), wants to bank a new word before
  forgetting it.
- Attention divided; session length 10–30 seconds; several times a day.
- Goals: capture instantly, get a definition without leaving the task, file it
  somewhere sensible, return to work with no residue (no open windows, no lost
  place).
- What frustrates them: a browser tab that outlives the lookup; being forced to stop
  and create a collection in a separate settings screen; a slow network lookup that
  blocks saving; being told "duplicate" with no context to decide quickly.
- Success = one click to the input, immediate save regardless of lookup state,
  inline collection creation, duplicate popup that shows enough to decide in seconds.
- Drives: Collect flow, lookup pipeline, duplicate resolution, widget presence,
  master-file safety behaviors that protect a single capture.

**Persona 2 — "The Driller"**
- Mode: deliberately sits down to study, app is the primary task.
- Attention focused; session length 10–30 minutes; a few times a week.
- Goals: choose exactly which collections to drill; be tested by production (typing
  the word from its meaning, not picking from choices); know how the session is going
  moment to moment; repeat weak words until they stick; get a clear read on what the
  session achieved.
- What frustrates them: an unsearchable collection list; a drill that shows each word
  once (recognition, not recall); a miss that silently moves on without revealing the
  spelling; a miss that wipes out progress already made on a word; losing all
  results to an accidental window close.
- Success = searchable/sortable collections with counts up front, a
  user-set mastery threshold, live score/penalties, revealed spelling with time to
  read it after a miss, mistakes cost score but never reset progress, both "end
  early" and "finish naturally" produce the same recorded summary.
- Drives: Practice setup, drill loop, scoring/mastery rules, session summary.

**Shared tension**: the Collector wants the widget always present; the Driller wants
it out of the way during a session. Resolved by making the widget toggleable with a
tray icon as a permanent fallback — the app can never be running yet unreachable.

### 1.3 Platform and scope boundaries

- **Platform**: Windows only. Windows 10 (1809+) or Windows 11, x64.
- **Out of scope** (deliberate, not gaps to fill without asking):
  - Cloud sync or multi-device support.
  - Languages beyond English (word) and Vietnamese (translation fallback).
  - macOS, Linux, or mobile.
  - Spaced-repetition scheduling — Practice is manual collection selection.
  - A web-based or browser-hosted Practice mode (was tried, explicitly reverted).
  - Accessibility work beyond toolkit defaults (recorded scope reduction, not an
    oversight — see NFR-12 in Part 3).
  - Editing existing word rows from within the app — the workbook is edited in Excel
    for that; the Collections preview table (§2.6) is read-only by design.
  - Clipboard or hotkey capture of words — entry is always manual.

### 1.4 Decision history worth knowing before changing behavior

Each of these was tried, reconsidered, and reversed at least once. Re-proposing the
earlier approach without this context wastes a cycle:

| Area | Was | Now | Why it changed |
|---|---|---|---|
| Dictionary source | Cambridge Dictionary via HTML scraping | Structured-API pipeline, 4 sources | Scraping is fragile; APIs give structured parts of speech |
| Lookup strategy | Sequential fallback chain, stop at first hit | Concurrent — query all sources every time | A slow first source no longer delays a result a faster one already has |
| Lookup source ranking | Free Dictionary > Merriam-Webster > Translate | **Local dictionary** > Free Dictionary > Merriam-Webster > Translate | A machine with blocked/unreliable outbound HTTP made both web dictionaries fail identically, every time, with no recovery — see §2.3 |
| Excel access | pandas (read) + openpyxl (write) | **openpyxl only** | Repository needs cell-level access on two sheets (header repair in place, preserve user columns, delete individual rows) — a DataFrame round-trip can't express that without rewriting whole sheets |
| Practice/Settings UI | Local HTTP server serving a website | Native `QWebEngineView` loading local files, **no server, no browser, no localhost** | Reverted for both a security/architecture reason (no server surface) and a product reason (native window, not a website) |
| Practice/Settings transport | WebView2 via `pywebview` | `QWebEngineView` under one Qt event loop | `pywebview` and Qt each own a blocking main loop; they can't coexist in one process without fragile interleaving that would hurt widget responsiveness |
| Collect meaning source | Auto-lookup only | Auto-lookup **or** manually typed meaning, user's choice per word | User-requested; see §2.2 |
| Lookup source ranking (again) | Local dictionary first | **Local LLM (Ollama)** > local dictionary > Free Dictionary > Merriam-Webster > Translate | An optional generated meaning is preferred *when the user opted in*; it is absent from ranking otherwise, so the previous order still holds for everyone else — see §2.3.1 |
| Package identity (v3 only) | Distribution name `vocabulary-trainer` (same as v2) | `vocab-v2` | v2 and v3 shared a package name; installing one silently replaced the other's editable install. Renamed so both can coexist and the launch command is unambiguous. The **importable module** is still `vocabulary_trainer` — only the pip distribution name and console script changed. |

---

## Part 2 — Feature Behavior

This section describes exactly what the app does, screen by screen. Treat every
rule here as intentional; if something looks like a bug, check §1.4 and the source
file cited before "fixing" it.

### 2.1 Collect a word (the floating widget)

Entry points: click the widget → **Collect new word**, or the tray icon's menu.

The Collect card (`ui/widget/collect_card_popup.py`, mirrors
`ui/web/assets` styling but is itself a native Qt popup, not web-rendered):

- Fields: Word/phrase text input, Type as single-select chips (**noun, verb,
  adjective, adverb, phrase**), a Collection dropdown.
- **The type chips are labelled short** — `N`, `V`, `adj`, `adv`, `ph`
  (`CHIP_LABELS` in `collect_card_popup.py`), each carrying the full word as its
  tooltip. Display only: what is saved is still `PartOfSpeech.value`, so the
  workbook stays readable in Excel and the lookup pipeline keeps matching
  definitions on the real part-of-speech name. Five full words do not fit the
  270px card, so Qt was compressing the chips and clipping text mid-word
  ("noun" → "1our"). Widening the card was rejected: it has to stay narrow enough
  to sit beside the widget without covering what the user is reading. Each chip
  also sets a minimum width from its own `sizeHint`, so the layout can never
  squeeze a label below the room its text needs.
- **Inline collection creation**: the dropdown's last entry is "+ New collection…",
  which swaps the dropdown for a name field with Create/Cancel. Names are validated
  for emptiness and case-insensitive uniqueness; the new collection is immediately
  selected.
- **No clipboard or hotkey capture** — entry is always manual, by design.
- **Save is enabled the instant a word and a type exist** — never gated on lookup
  finishing. The whole design of §2.3 exists to make that safe.
- **One word or several** (FR-2.12): a "One word / Several" toggle above the input.
  In Several mode the text is split on commas and each fragment is trimmed,
  whitespace-collapsed and lowercased (`domain/word_list.parse_word_list`, which
  reuses `normalize_word` so batch de-duplication matches the workbook's own identity
  rule). Parsing is forgiving — a trailing or doubled comma is dropped, an in-batch
  repeat collapses — because rejecting the whole entry over a stray comma would cost
  the user everything they typed. A live hint echoes the parsed result, since the
  lowercasing and collapsing are otherwise invisible until after saving.
  All lookups start before any row is written, so ten words cost roughly one lookup's
  wait; `CollectService.save_words` reuses `save_word` per word rather than
  reimplementing save-then-patch. **Duplicates are skipped, not offered for
  resolution** — the Keep/Replace/Delete popup is right for one word, but asking it
  five times would be worse than reporting "Saved 3, skipped 2 already there".
  Multi-word mode disables Manual meaning (one typed definition cannot be right for
  several words) and starts no lookup per keystroke. A locked workbook stops the batch
  at the word that hit the lock rather than writing an arbitrary subset. Two accepted
  limits: proper nouns lose their capitals, and the card stays open after a batch so
  the mixed result can be read.

#### 2.2 Auto-meaning vs Manual-meaning (the toggle)

The Collect card carries an **Auto-lookup / Type it myself** toggle
(`MeaningMode` in `collect_card_popup.py`), defaulting to Auto-lookup.

- **Switching to Manual**: cancels any lookup in flight for the current word, hides
  the read-only lookup-result panel, and shows two editable fields — **Your
  meaning** and **Your example** (optional).
- **Switching back to Auto**: starts a fresh lookup for the word/type currently
  entered.
- **Saving in Manual mode**: stores exactly what the user typed, trimmed. A blank
  meaning is permitted and behaves like an unresolved Auto-lookup (word saves with
  Type only, no error).
- **The lookup pipeline is never queried while Manual is selected**, and a lookup
  that was already running when the user switched is abandoned rather than allowed
  to patch the row later. This is the one race the feature specifically closes: a
  slow dictionary response landing after save must never silently overwrite a
  meaning the user explicitly chose to write themselves.
- Duplicate detection/resolution (§2.4) is identical either way — the natural key and
  the three outcomes don't care which mode produced the incoming word.
- Code: `services/collect_service.py` (`save_word`/`build_entry` accept
  `manual_meaning`/`manual_example` kwargs; passing either bypasses the lookup
  handle entirely), `ui/widget/collect_card_popup.py` (the toggle UI).

#### 2.3 Lookup pipeline

WHEN a Word + Type is entered, the app queries **all four sources concurrently**,
under one bounded deadline (`services/lookup_service.py`):

0. **Local LLM via Ollama** (`integrations/ollama_client.py`) — see §2.3.1. Absent
   from selection entirely unless switched on with a model chosen, so this list is
   unchanged for anyone who never touches the setting.
1. **Bundled offline dictionary** (`integrations/local_dictionary_client.py`) — a
   WordNet-derived JSON file shipped at
   `assets/dictionary/wordnet-2025-dictionary.json` (~127k entries, ~45MB). Parsed
   once into memory on first use and cached for the process. **No network call at
   all.**
2. **Free Dictionary API** (`api.dictionaryapi.dev`) — keyless, always available.
3. **Merriam-Webster Dictionary API** — needs a free API key, configurable in
   Settings → General; skipped entirely (not called) without one.
4. **Google Translate** (EN→VI) — the fallback; becomes the meaning with no example
   when it's the one that answers.

Selection rules (`domain/lookup_priority.py`):
- Within a source, the definition whose part of speech matches the selected Type
  wins; otherwise the first available definition is used (sources order roughly by
  commonness).
- Across sources, the **highest-priority non-empty** result is stored:
  **local dictionary > Free Dictionary > Merriam-Webster > Google Translate**. A
  source that answered but returned nothing usable counts as not having answered —
  an empty high-priority response can never beat a usable lower-priority one.
- The local dictionary ranks first specifically because it cannot fail for network
  reasons the way the two web dictionaries can — this was added after observing that
  a machine with blocked/timed-out outbound HTTP made auto-meaning silently return
  nothing on every attempt, with no way to recover short of a network change.
- If all four fail (offline dictionary has no entry and both web dictionaries fail
  or find nothing), the word is still saved with its Type; Meaning/Example stay
  blank.
- The status line names the actual source on success (e.g. "✓ Found in offline
  dictionary", "✓ Found in Free Dictionary"). Lookup never blocks saving, and the
  widget stays responsive throughout — lookup runs on a background thread with its
  own asyncio loop (`CollectService.begin_lookup`).
- **Save-then-patch**: a word is written immediately with whatever the lookup has
  produced so far (possibly nothing); if the lookup is still outstanding, the same
  row is patched when it completes rather than a second row being inserted. A patch
  targeting a row deleted meanwhile is abandoned, not recreated.
- **The lookup survives the card closing.** The Collect card closes immediately on
  every successful save, so the pending lookup is deliberately *handed off* rather
  than cancelled — it finishes in the background and patches the row when the result
  lands. Only a **discarded** entry (closed via X or Escape without saving) cancels
  its lookup, so a late result can never write a row the user abandoned. Manual mode
  always cancels (§2.2). Tracked by `CollectCardPopup._handed_off_lookup`; see §4.4
  for the bug this fixed.

#### 2.3.1 Local LLM meanings via Ollama (FR-3.10, optional, off by default)

An optional fifth source that **generates** an English meaning and example rather
than looking one up, using a model running on the user's own machine through
Ollama's HTTP API at `127.0.0.1:11434`.

- **Not installed by this app, and deliberately excluded from the installer.** The
  user brings their own Ollama. Every path treats "not installed" and "not running"
  as ordinary silent outcomes, so a machine without it behaves exactly as it did
  before the feature existed.
- **Loopback only, not configurable.** Pointing the host at a remote machine would
  send every collected word to a third party — a materially different privacy
  proposition than a local model, so the UI offers no way to do it.
- **Off by default, and unavailable until switched on *and* given a model.**
  `set_ollama` refuses to enable without a model and returns the *achieved* state,
  so the toggle reverts rather than showing "on" over a source that cannot answer —
  the same contract as the start-with-Windows switch.
- **Only installed models are ever offered.** Settings lists `GET /api/tags`, so the
  dropdown cannot name a model that would fail on first use. An empty list is
  explained by cause — Ollama absent vs. running with nothing pulled — rather than
  shown as a failure. A model chosen and later deleted is reported in a banner, not
  silently dropped.
- **It ranks first in `PRIORITY`** (see §1.4). Enabling it is an explicit statement
  that its phrasing is preferred; it also runs locally, so like the bundled
  dictionary it cannot fail for network reasons. When it is off it contributes
  nothing to the ordering, so the ranking is unchanged for everyone else.
- **The part of speech is a constraint, not a filter.** Unlike a dictionary, which
  returns many senses for `select_definition` to choose between, the model is asked
  directly for the sense matching the chosen type and returns at most one candidate.
  The prompt tells it to return null when the word is not used that way, and an
  empty meaning is treated as "did not answer" — so a wrong-part-of-speech
  generation can never outrank a correct dictionary entry.
- **The response is requested as JSON**, with Ollama's own `format: "json"` applied.
  Free-form prose would need parsing out of whatever preamble a model chose to add,
  which varies per model and per run. The parser still tolerates a markdown fence or
  surrounding prose, because smaller models ignore the instruction; it also maps the
  *string* `"null"` to empty, which models emit routinely.
- **Timeouts differ by call.** 2s for the model list (it runs when Settings opens,
  and a refused connection returns instantly), 60s for generation (a cold model on
  CPU genuinely takes that long). The long one is safe because lookup never blocks
  saving — measured 5–15s on `gemma:2b` for a real word.
- **`LookupService` widens its whole-lookup ceiling to 60s when a generative source
  is available**, via `_deadline_for`, and keeps the 8s dictionary ceiling otherwise.
  This is not optional politeness: at 8s the model was cancelled before it could ever
  answer, so enabling the feature appeared to do nothing. The two limits must stay
  aligned — `OllamaClient._GENERATE_TIMEOUT` being shorter would make the service's
  wider budget a fiction. The ceiling is chosen from the sources available *on that
  lookup*, so a user who has the model off is never slowed by it, and it is a ceiling
  rather than a delay: `asyncio.wait` returns as soon as every source finishes.
- Because `QWebChannel` slots are synchronous and Qt runs no asyncio loop, the
  bridge drives these coroutines on a worker thread (`_await` in
  `settings_bridge.py`) rather than `asyncio.run` on the calling thread, which would
  freeze the Settings window while Ollama was probed.
- Code: `integrations/ollama_client.py`, `GenerativeLookupClient` in
  `integrations/lookup_client.py` (a separate protocol so adding a generative source
  did not force a parameter onto the four dictionary clients that have no use for
  it), `LookupService._request`, `SettingsService.set_ollama` / `ollama_models`,
  bridge slots `ollama_state` / `set_ollama`.

#### 2.3.2 The character reports the outcome (FR-3.11)

When a lookup resolves, a small speech bubble appears beside the widget: **"I found
it!"** or **"I couldn't find it"**, with the word beneath it so a bubble seen a few
seconds later is still attributable.

This exists because the Collect card closes the instant a word is saved, so a lookup
finishing afterwards previously had nowhere to report itself — the meaning simply
appeared in the workbook with no acknowledgement. That is the *normal* case, not an
edge case.

- **Owned by `Application`, not the Collect card.** Anything owned by the card would
  be destroyed before the result arrived.
- **`LookupAnnouncer` (`ui/widget/lookup_announcer.py`) crosses the thread boundary.**
  Lookups complete on a worker thread and Qt widgets may only be touched from their
  owning thread, so the result is emitted as a signal and the bubble is built on the UI
  thread. Building it in the callback directly would be undefined behaviour.
- **`ToolTip` window flag, not `Popup`.** A Popup grabs input and would swallow the
  user's next click elsewhere. The bubble never takes focus, self-dismisses after 4s,
  and closes on click.
- **One bubble at a time.** A batch of ten words resolving over a few seconds would
  otherwise stack ten overlapping popups; the newest replaces the previous.
- Manual-meaning saves are never announced — the user supplied the meaning, so there
  was nothing to find. The not-found variant is grey, not red: failing to find a rare
  word is ordinary, and an error colour would overstate it.

#### 2.4 Duplicate detection & resolution

WHEN the submitted word already exists under the same natural key (word +
collection, case/whitespace-normalized — see §3.2):

1. A popup appears showing the existing entry's **Collection** and **Date**.
2. Three actions: **Keep old** (nothing changes), **Replace** (overwrites
   Meaning/Example/Date on the existing row, preserving Word and Collection),
   **Delete both** (removes the existing row **and** discards the new submission —
   neither survives; the label is written exactly this way so the effect is
   unambiguous).
3. Dismissing the popup with no choice behaves exactly as **Keep old**.
4. Exactly one of {no change, row updated, row removed} ever happens — no action
   inserts the incoming word as a separate row.
5. Code: `services/collect_service.py` (`resolve_duplicate`),
   `ui/widget/duplicate_conflict_popup.py`.

### 2.5 Practice (native writing drill)

A native window (`ui/web/windows.py` hosts a `QWebEngineView` loading
`ui/web/assets/practice.html`, bridged by `ui/web/practice_bridge.py` to
`services/practice_service.py`). **No local server, no browser process, no
localhost** — the page is loaded from a local file inside the app's own window.

**Setup screen**:
- Collection multi-select: checkbox list, each row showing word count and creation
  date.
- Search: case-insensitive substring on name, live; "No collections match your
  search." on zero results.
- Sort: Newest first (default), Oldest first, Name (A–Z). Independent of the search
  filter and of which collections are checked — a checked collection filtered out of
  view stays checked and still counts toward the pool. Resets to Newest first every
  time the window opens.
- Required correct writes: stepper, default **3**, range **1–10**, disabled at the
  bounds.
- Combined pool size shown before starting; Start is disabled with an explanation if
  the checked collections total zero words.
- **Preview** (added in this v3 session): each row carries an eye-icon action opening
  the same read-only table Settings offers (§2.6) — Word, Type, Meaning, Example,
  Date, with blanks as "—". Lets the user check a collection's contents before
  committing it to a pool instead of leaving Practice to look. Clicking it never
  toggles the checkbox. Both this and the Settings preview read through
  `MasterFileRepository.words_for()` — one definition of collection membership, so
  they cannot disagree. Code: `PracticeService.words_for_collection`, bridge slot
  `PracticeBridge.collection_words`, `practice.html`'s `#preview-backdrop`.

**Drill loop**:
1. Words presented in random shuffle order (`domain/shuffle.py`).
2. Each prompt shows Type and Meaning; the user types the Word. The spelling is
   never shown before submission. A word with no recorded meaning gets an explicit
   note rather than a blank prompt.
3. Progress = attempts made against `pool size × required writes`, **computed once
   at session start** so the bar only ever advances (a shrinking pool as words are
   mastered must not make the denominator jump backwards).
4. **Correct answer** (case-insensitive, trimmed, whitespace-collapsed match —
   `domain/scoring.py`): plays a success sound, speaks the word via TTS, increments
   the word's consecutive-correct counter (shown as mastery dots). At the required
   count the word is **mastered** and leaves the pool; otherwise it's reinserted at
   a position other than the immediate next draw (`domain/shuffle.reinsert_avoiding_next`)
   so the user never retypes what they just saw.
5. **Incorrect answer**: applies exactly 1 penalty; live score = `total correct
   attempts − total penalties`, shown throughout, **not clamped at zero**. The
   word's mastery progress is **never reset** — this is guaranteed structurally: no
   operation in the domain layer decreases `consecutive_correct`, so the invariant
   can't be broken by a later edit that forgets to check for it. The correct
   spelling is revealed and the drill **waits for an explicit Next** before
   advancing. An empty submission is ignored, not penalized.

**Summary**: shown when every word is mastered, the user clicks End session, or the
window is closed mid-session — all three routes produce the same summary. Shows
final score, words practiced, total penalties, time taken. Actions: **Back to
setup** (restores previous selections) and **Practice again** (same collections and
threshold, freshly shuffled). Results append to `practice-history.json`; **nothing
is written into the master workbook** — it stays a clean word list.

**Separate practice log workbook** (added in this v3 session, user-requested): every
session ending also appends one row to a *second*, dedicated Excel file —
`%AppData%\VocabularyTrainer\practice-log.xlsx` — meant to be opened directly in
Excel, distinct from both the master workbook and `practice-history.json`:

| Column | Value |
|---|---|
| Date | Session's start date |
| Start Time / End Time | `hh:mm:ss` Excel time cells (real time type, not text — sortable, supports duration math) |
| Collection | Chosen collections, comma-joined (e.g. `"IELTS, Daily Reading"`) |
| Penalty | Total penalties that session |
| Finish | `True` **only** if the pool emptied naturally (every word mastered) before the session ended; ending early via End session or closing the window mid-session logs `False` even if some words were mastered |
| Word with penalty | `'|'.join(f"{word}_{count}")` for every word missed at least once, e.g. `hello_2|goodbye_3`; blank for a perfect session |

Code: `domain/models.PracticeLogEntry` (the two string-rendering properties
`collection_display`/`word_with_penalty` are the only formatting logic, kept in the
domain layer per §3.2's testability invariant), `data/practice_log_repository.py`
(`PracticeLogRepository`, same temp-file-then-swap discipline as the master
workbook but degrades to `False` on failure rather than raising a typed lock
error — losing one log row is not worth the master file's retry machinery),
`services/practice_service.PracticeSession._wrong_counts` (tallied per normalized
word during `submit_attempt`, exposed as `session.wrong_counts`),
`PracticeService.end_session()` (builds the entry and calls
`practice_log.append_entry`, wired optionally via `AppContext`). This file is
**write-only from the app's perspective** — nothing else in the app reads it back.

### 2.6 Settings (native window, five tabs)

Two-pane layout — left nav, right content — `ui/web/assets/settings.html` +
`.js`, bridged by `ui/web/settings_bridge.py` to `services/settings_service.py`.

- **General**: master file path (Browse dialog; an unreadable file is rejected and
  the previous path stays in effect; a non-existent path creates a correctly
  structured workbook there), Start with Windows toggle (off by default, reports its
  *achieved* state so a failed registration reverts the switch rather than
  displaying a lie), Merriam-Webster API key (stored locally, never logged or read
  back across the bridge), and the **Local AI model** section (§2.3.1).
- **Collections (CRUD)**: list with word counts; create, rename (cascades to every
  word row in one atomic write; case-only recasing like `ielts`→`IELTS` is
  permitted), delete (modal confirmation states the exact word count, repeated on
  the confirm button; deleting the last collection re-seeds `General`).
  - **Preview** (this row action): opens a read-only modal table — columns **Word,
    Type, Meaning, Example, Date** — for every word in that collection. Read-only:
    editing still means opening the workbook in Excel.
    A blank Meaning/Example has **two distinct causes, shown differently**: a lookup
    still running renders "Looking up…" with a spinner, while one that finished
    without a result renders "—". The workbook cannot tell them apart (both are an
    empty cell), so the distinction comes from
    `PendingEnrichmentRegistry` — a non-persisted, thread-safe set of natural keys
    with an enrichment patch outstanding, published by `CollectService` and read by
    both previews. Not persisted on purpose: a pending lookup cannot outlive its
    process, so a restored registry would show rows as being worked on by a thread
    that no longer exists. While any row is pending the modal polls once a second and
    stops as soon as none is.
    Code: `services/pending_enrichment.py`,
    `SettingsService.words_for_collection` / `is_lookup_pending`, bridge slot
    `collection_words` (returns `lookupPending` per row plus an `anyPending`
    summary), `settings.html`'s `#preview-backdrop` modal, `.preview-table` and
    `.preview-pending` CSS.
- **Widget**: Show widget toggle (kept in sync with the widget's own menu toggle via
  `WidgetStateService`'s observer pattern), Character dropdown (applied live), and
  **Widget size** — a 50%–300% slider with a Reset button, default 100%, applied
  live as it is dragged (FR-7.15). The range travels from `domain/models.py`
  through the bridge into the slider's `min`/`max` rather than being written into
  the markup, so the control cannot offer a size the service would refuse. The
  service rejects out-of-range values outright; the *preferences store* clamps
  instead, because a hand-edited file has no caller to correct. Code:
  `WidgetStateService.set_scale_percent`, `SettingsService.set_widget_scale_percent`,
  bridge slot `set_widget_scale_percent`, `FloatingWidgetWindow._target_width`.
- **Audio**: Voice dropdown listing installed Windows speech voices with a Preview
  button; a machine with no voices is explained, not shown as broken (Practice still
  plays its success sound without speech).
- **About**: application name, version, master file location in use.

### 2.7 Floating widget ("mini-ani")

- Frameless, per-pixel-translucent, always-on-top window; no taskbar entry; never
  steals focus (`ui/widget/floating_widget_window.py`).
- Character is **cat or crocodile**, selectable at runtime from Settings, applied
  live. Only cat artwork ships; crocodile is listed as unavailable rather than
  silently rendering a cat (see §4.6 for how to add it).
- Draggable anywhere; position persists across restarts and is clamped back
  on-screen if a monitor is removed or resolution changes.
- **Click opens a popup menu** (`ui/widget/widget_menu_popup.py`):
  **Collect new word**, **Practice**, a divider, **Settings**, a **Widget on**
  toggle (a custom-painted `ToggleSwitch`, not a plain `QCheckBox` — QSS cannot draw
  a sliding thumb on a checkbox indicator), a divider, and **Quit**. The menu flips
  to the widget's other side near a screen edge if there's not enough room.
- **Quit** (added in this v3 session): ends the app directly from the widget menu —
  the same shutdown path (`Application.quit()`) the tray icon's own Quit already
  used, so there's no new shutdown logic, just a second way to reach it. Added so
  quitting never requires finding the tray icon.
- Character switches idle/active pose depending on whether a popup it owns is open.
- **System tray icon**: always present while the app runs, carrying the same menu.
  The widget is only permitted to hide itself if a tray icon exists — the app can
  never end up running yet unreachable (`ui/widget/tray_icon.py`).

---

## Part 3 — Technical Reference

### 3.1 Stack

- **Language**: Python 3.12+ (developed/verified on 3.14).
- **Widget UI**: PySide6 Qt widgets — needs frameless, per-pixel-translucent,
  always-on-top windows, which an embedded web view can't do cleanly.
- **Practice + Settings UI**: `QWebEngineView` (Qt's embedded Chromium) rendering
  local HTML/CSS/JS under `ui/web/assets/`, bridged to Python via `QWebChannel`.
  **No HTTP server, no browser process, no `localhost`** — content loads from local
  files inside the app's own window.
- **Excel**: `openpyxl` only. No pandas (see §1.4 for why).
- **HTTP**: `httpx`, for the two web lookup sources and translation.
- **Other**: `watchdog` (external file-change detection, optional — falls back to
  polling if absent), `pywin32` (SAPI text-to-speech, Windows-only).
- **Package identity**: distribution name `vocab-v2`, console script `vocab-v2`,
  importable module `vocabulary_trainer` (unchanged from v2's module name — only the
  pip-level identity differs, specifically to avoid collision with v2's own
  `vocabulary-trainer` distribution if both are ever installed on the same machine).

### 3.2 Layering (strict, one-way dependencies)

```
ui            Qt widgets (floating overlay) + QWebEngineView (Practice, Settings)
services      orchestration; the ONLY layer the UI may call
data          Excel workbook, preferences, practice history, file watching
integrations  dictionary/translation clients, TTS, audio, OS startup registration
domain        pure logic, NO I/O: identity, lookup priority, shuffle, scoring
```

**Nothing below `ui` ever imports from it.** This is what makes the entire service
layer testable with no display and no Qt application object in the process, and
what stops the two UI technologies (Qt widgets vs. web-rendered windows) from
growing divergent copies of the same behavior. If a service ever seems to need to
import a widget, the logic belongs somewhere else — restructure instead of breaking
the rule.

Other invariants to preserve when changing code:
- **No business logic in `ui/`.** The `QWebChannel` bridges (`practice_bridge.py`,
  `settings_bridge.py`) carry data and calls, never decisions — every judgement
  (which lookup source wins, whether an answer is correct, how many words a
  deletion destroys) is a service/domain call. `ui/` is excluded from coverage on
  this basis (see `pyproject.toml`'s `[tool.coverage.run]` omit list).
- **All workbook writes go through `MasterFileRepository`'s atomic swap** — never
  write the `.xlsx` directly. Temp file must be a sibling of the target (`os.replace`
  is atomic only within one filesystem volume).
- **Word identity is defined once**, in `domain/natural_key.py` (`normalize_word`,
  `normalize_collection`, `natural_key`). Duplicate detection, repository lookups,
  and practice answer matching all route through it — never reimplement
  normalization elsewhere, or duplicates get detected inconsistently by code path.
- **Design tokens live once**, in `ui/theme/tokens.py`. The Qt stylesheet
  (`ui/theme/qt_stylesheet.py`) and the web layer's CSS variables
  (`ui/web/assets/app.css` via injected `:root`) are both **generated** from it —
  never hardcode a color or radius in either surface.
- **A wrong practice answer never reduces mastery progress.** Guaranteed by
  omission: no operation anywhere in `domain/` decreases
  `PracticeWordState.consecutive_correct`. Keep it that way — do not add one.

### 3.3 Source map

```
src/vocabulary_trainer/
├── app.py                          Qt app shell; wires UI to services; owns quit()
├── __main__.py                     entry point (python -m vocabulary_trainer)
│
├── domain/                         PURE. No I/O, no Qt.
│   ├── models.py                   every dataclass + enum (WordEntry, LookupSource,
│   │                               PartOfSpeech, AppPreferences, etc.)
│   ├── natural_key.py               word/collection identity — the ONE definition
│   ├── lookup_priority.py          PRIORITY tuple + select_definition/select_result
│   ├── shuffle.py                  pool order + no-immediate-repeat reinsertion
│   └── scoring.py                  answer matching, score, required attempts
│
├── data/
│   ├── master_file_repository.py   THE ONLY writer of the .xlsx workbook
│   ├── preferences_store.py        JSON prefs, per-field corruption tolerance
│   ├── history_store.py            practice session log (JSON), capped at 500
│   ├── practice_log_repository.py  separate Excel practice log, one row/session
│   ├── file_watcher.py             debounced external-change detection
│   └── errors.py                   MasterFileLocked / Unreadable / etc.
│
├── integrations/
│   ├── lookup_client.py            the LookupClient protocol; fetch() never raises
│   ├── local_dictionary_client.py  bundled offline dictionary — priority 1, no network
│   ├── free_dictionary_client.py   priority 2, keyless
│   ├── merriam_webster_client.py   priority 3, needs an API key
│   ├── translate_client.py         priority 4, EN→VI
│   ├── tts.py                      SAPI, speaks on a worker thread
│   ├── audio.py                    feedback sounds, system-sound fallback
│   └── startup_registration.py     start-with-Windows registry entry
│
├── services/                       the ONLY layer the UI may call
│   ├── app_context.py              composition root — the one place construction
│   │                               order matters; wires all 4 lookup clients
│   ├── collect_service.py          save-then-patch, duplicate resolution,
│   │                               manual-meaning bypass
│   ├── practice_service.py         collections, pool, drill loop, summary,
│   │                               per-word wrong-count tally for the practice log
│   ├── settings_service.py         prefs, master file path, collection CRUD,
│   │                               words_for_collection (preview)
│   ├── widget_state_service.py     widget state + observer channel
│   ├── lookup_service.py           concurrent fetch, then priority selection
│   ├── clock.py                    injected time (SystemClock / FixedClock)
│   └── errors.py                   ValidationError, EmptyPoolError
│
└── ui/
    ├── theme/
    │   ├── tokens.py                design tokens — the ONE source
    │   └── qt_stylesheet.py         generated Qt stylesheet
    ├── widget/                     Qt native windows/popups
    │   ├── floating_widget_window.py
    │   ├── collect_card_popup.py    incl. Auto/Manual meaning toggle
    │   ├── duplicate_conflict_popup.py
    │   ├── widget_menu_popup.py     incl. Quit action, dynamic width sizing
    │   ├── toggle_switch.py         custom-painted on/off switch (no QCheckBox)
    │   ├── tray_icon.py
    │   ├── anchoring.py             popup placement math (pure, unit-testable)
    │   └── assets.py                character artwork resolution
    └── web/                        QWebEngineView hosts + bridges
        ├── web_window.py           asset staging (qwebchannel.js, fonts, etc.)
        ├── windows.py               PracticeWindow, SettingsWindow
        ├── bridge.py                BridgeBase, ok()/fail() envelope helpers
        ├── practice_bridge.py       Practice window's @Slot methods
        ├── settings_bridge.py       Settings window's @Slot methods
        └── assets/                 practice.html/.js, settings.html/.js,
                                     app.css, bridge-client.js
assets/
├── floating_widget/                 mini_ani_{idle,active}[_web].png (cat only)
├── fonts/                           Google Sans TTFs (bundled, no CDN)
├── sounds/                          (currently empty — system sounds used instead)
└── dictionary/
    └── wordnet-2025-dictionary.json  ~127k entries, ~45MB, bundled for offline lookup

tests/                                mirrors src/, shared fakes in tests/conftest.py

materials/                          ★ reference inputs, NOT loaded at runtime
├── README.md                         what each item is, and how far to trust it
├── mockup/                           16 HTML/CSS files — visual source of truth
├── asset/floating_widget/            original character artwork + design refs
├── aidlc-docs/                       requirements (FR-x.y), 42 stories, personas
├── specs/output_specs.md             the living spec this file consolidates
└── draft/brainstorming.md            rough notes, explicitly not a spec

PROJECT.md                          ★ this file — the consolidated reference
README.md                             install / run / test quickstart
pyproject.toml                        deps, package-data, pytest + coverage config
```

Note the deliberate split: `src/vocabulary_trainer/assets/` holds what the
**application loads at runtime**; `materials/` holds what **humans read**. The
character artwork appears in both because the shipped copies live under `src/` while
the originals (plus two unshipped reference JPGs) are kept in `materials/`.

### 3.4 Data model

**Master workbook** (`.xlsx`, two sheets, safe to hand-edit in Excel):

`Words` sheet:

| Column | Type | Required | Notes |
|---|---|---|---|
| Words | Text | Yes | The word/phrase. Part of the natural key with Collection. |
| Type | Enum text | Yes | noun / verb / adjective / adverb / phrase |
| Meaning | Text | No | Blank if lookup found nothing, or manual mode left it blank |
| Example | Text | No | Blank when meaning came from translation, or manual with no example |
| Name of collection | Text | Yes | Must match a `Collections` row's Name |
| Date | Date | Yes | Collected date, or last-replaced date per duplicate resolution |

`Collections` sheet:

| Column | Type | Required | Notes |
|---|---|---|---|
| Name | Text, unique | Yes | Case-insensitive uniqueness |
| Created date | Date | Yes, system-set | Drives Practice setup's sort modes |

- Matching is case-insensitive, whitespace-trimmed, and collapses internal
  whitespace runs (`"give  up"` == `"give up"`). Punctuation is **not** normalized
  (`"well"` != `"well,"`). See `domain/natural_key.py`.
- `(Words, Name of collection)` is the natural key.
- A default collection **General** always exists (seeded on first run and re-seeded
  if the last collection is ever deleted).

**App data**, under `%AppData%\VocabularyTrainer\` (unchanged folder name from v2 —
this is the app's data directory identity, separate from the pip package name):

- `master.xlsx` — the default master file location (user-configurable in Settings).
- `preferences.json` — widget position/visibility, character, TTS voice, master file
  path, Merriam-Webster API key, start-with-Windows, last-used practice settings
  (last practiced collections, required-writes value).
- `practice-history.json` — session results, capped at 500 entries, read back by
  the app.
- `practice-log.xlsx` — separate, write-only Excel practice log (§2.5); one row per
  session, never read back by the app, meant purely for the user to inspect.

### 3.5 Non-functional requirements (as implemented)

1. **Offline resilience**: only the two web dictionaries and translation need
   network; the bundled offline dictionary and everything else work fully offline.
   Auto-meaning only degrades to blank if the offline dictionary *also* has no
   entry for the word.
2. **Data safety**: every master-file write is atomic — temp file beside the
   target, then swap, so a crash mid-write leaves either the complete old or
   complete new content. Orphaned temp files from an interrupted run are cleaned up
   at next launch.
3. **Write serialization**: no two mutating operations write concurrently.
4. **Locked file** (Excel has it open): pending change held in memory, user told to
   close Excel, Retry offered. Nothing partially applied.
5. **Header repair**: header rows validated on open; an altered/missing header is
   auto-repaired positionally (data beneath preserved), user told exactly what
   changed. Extra user-added columns are preserved. A file that isn't a readable
   workbook at all is reported as such with no repair attempted.
6. **External edits**: the app watches the master file and reloads once writes
   settle. An in-flight practice session keeps its original pool; unsaved Collect
   input is preserved.
7. **Responsiveness**: no network or file I/O on the UI thread; widget stays
   draggable/clickable during lookups.
8. **Preference persistence**: widget state/position/character, TTS voice, master
   file path, API key all persist across restarts.
9. **Destructive-action safety**: collection deletion and duplicate "Delete both"
   both require explicit confirmation.
10. **Security**: the Merriam-Webster API key lives only in local preferences,
    never logged or surfaced in errors. Outbound requests go only to the three
    network lookup endpoints and carry only the word being looked up. The bundled
    offline dictionary makes no outbound request at all.
11. **Testability**: business logic stays independent of the UI layer. That
    structural property still holds and still matters — it is what keeps `domain/`
    and `services/` directly exercisable and reviewable — but it is now about how
    the code is *shaped*, not a testing quota. The existing suite runs with **no Qt
    application object in the process** for most tests (a few `ui/` tests do
    construct a `QApplication` — see §4.4).
    > ⛔ **Never write new unit tests unless the user explicitly asks.** Standing
    > user decision; it replaces the former "minimum 80% line coverage on new
    > business logic" rule that used to sit here. The existing tests stay and must
    > keep passing. See §4.2.
12. **Accessibility**: **not a focus for this product.** Toolkit keyboard behavior
    is retained; no additional keyboard navigation, screen-reader annotation, or
    contrast verification was done. Recorded scope reduction, not an oversight — do
    not silently add partial accessibility work without flagging the change in
    scope.

### 3.6 Visual design

- **Typeface**: Google Sans (Regular/Medium/Bold), bundled as local TTF files under
  `assets/fonts/` — never loaded from a CDN, so the UI renders correctly offline.
  Segoe UI is the fallback.
- **Style**: light theme, rounded cards (10/14/20px radii), soft shadows, blue
  primary accent, soft-tinted success/danger/warning colors.
- **Single token source**: `ui/theme/tokens.py` — both the Qt stylesheet and the web
  layer's CSS variables are generated from it (see §3.2's invariant). The values were
  transcribed from `materials/mockup/styles.css`.
- **Visual reference**: `materials/mockup/` (16 HTML/CSS files) is the visual source
  of truth for layout and styling. Its *copy* is stale in three places — see
  `materials/README.md` before quoting any text from it.

---

## Part 4 — Working in This Folder

### 4.1 Install and run

```cmd
cd VocabularyTrainer.V3
python -m pip install -e ".[dev]"
```

Then, from any directory once installed:

```cmd
vocab-v2
```

Equivalently: `python -m vocabulary_trainer` (module name unchanged; only the
console script/distribution name is `vocab-v2`).

**Without installing**, from `VocabularyTrainer.V3/`:
```cmd
set PYTHONPATH=src
python -m vocabulary_trainer
```

**Nothing appears?** The app has no main window by design — it starts as a
floating character plus a tray icon. Look bottom-right of the primary screen, above
the taskbar, and in the notification area. If the widget was previously switched
off, only the tray icon shows; click it for the menu (or see §4.5 to reset
`preferences.json` directly).

### 4.2 Test

```cmd
python -m pytest
```
With coverage:
```cmd
python -m pytest --cov=vocabulary_trainer --cov-report=term-missing
```

As of this consolidation: **757 tests passing, 89% line coverage** (2058
statements). `ui/` is excluded from coverage (needs live Windows compositing and
installed speech voices — verified manually, and business logic is deliberately
kept out of it).

#### ⛔ Do not write new tests unless asked

**Standing user decision: never author new unit tests unless the user explicitly
requests them.** This overrides the old "tests are mandatory / 80% coverage" rule
that used to appear in §3.5 item 11, in `materials/specs/output_specs.md`, and as
`NFR-TEST-02` in `materials/aidlc-docs/.../requirements.md`. Those documents are
historical inputs; this rule wins.

What that does and does not mean:

- **Do not** create new test files, add cases to existing ones, or write a
  regression test after fixing a bug — however large or risky the change. Not even
  "just one to be safe".
- **Do** keep running `python -m pytest` after changes. The existing 757 tests stay,
  and an existing test catching a regression is exactly what it is for. Never delete
  or weaken a test to make a change pass.
- **Do** still verify, just without authoring tests: run the affected code path
  directly, launch the app with `vocab-v2` and exercise the feature, and report
  plainly what was checked and what was not. Tests passing was never sufficient
  proof here anyway — see the launch-command trap in §4.4.
- If a change genuinely seems to warrant a test (data-integrity or destructive
  paths are the usual candidates), say so in one sentence and let the user decide.
  Do not write it pre-emptively.

Test layout mirrors `src/`:
- `tests/domain/` — pure logic, no fixtures needed beyond simple factories.
- `tests/data/` — repository/store tests, use `tmp_path`.
- `tests/integrations/` — lookup clients; no live network calls, transport is
  substituted or (for `local_dictionary_client`) a temp JSON file is used.
- `tests/services/` — the bulk of business-logic coverage; shared fixtures
  (`repository`, `preferences_store`, `clock`, `fake_tts`, `fake_audio`,
  `make_entry(...)`) live in `tests/conftest.py`.
- `tests/ui/` — presentation-logic-only tests (status wording, popup width/fit,
  bridge JSON shape). A few need a `QApplication` (module-scoped fixture pattern in
  `test_web_asset_staging.py` and `test_widget_menu_popup.py`); most do not.

### 4.3 Package/distribution identity — read before installing alongside v2

This project's `pyproject.toml` declares `name = "vocab-v2"` and console script
`vocab-v2 = "vocabulary_trainer.__main__:main"`. The **importable package** on
`PYTHONPATH`/`sys.path` is still `vocabulary_trainer` — that part didn't change.

Why this matters: the archived v2 (now at `../archive/VocabularyTrainer.V2/`)
declares distribution name `vocabulary-trainer`. Before this rename, installing v2
and this v3 folder as editable installs in the same Python environment meant
whichever was `pip install -e`'d most recently silently became the one
`python -m vocabulary_trainer` actually ran — no error, no warning. The rename to
`vocab-v2` fixes the *distribution* collision, so `pip list` now shows them
distinctly.

Note that both still expose the same **importable module** name,
`vocabulary_trainer`, so `python -m vocabulary_trainer` remains ambiguous if both
are ever installed in one environment. v2 is archived and does not need to be
installed; if you ever must run it, use a separate virtual environment. If you
create a v4, keep distribution names distinct the same way.

A related bit of housekeeping: a stale `src/vocabulary_trainer.egg-info/` left over
from before the rename made `pip list` report a phantom `vocabulary-trainer`
distribution rooted in this folder. It has been removed; only `vocab_v2.egg-info/`
should exist under `src/`.

### 4.4 Known real bugs already fixed in this codebase (context for similar-looking issues)

If you hit something that looks like one of these, it is very likely NOT the same
bug recurring — these are already fixed and covered by regression tests. Useful
context for diagnosing genuinely new issues without retreading the same ground:

- **`PracticeBridge.start_session`/`practice_again` duplicate-keyword crash**:
  `ok(**self._prompt_payload(), poolSize=...)` where `_prompt_payload()` already
  contained a `poolSize` key raised `TypeError`, caught by the generic exception
  handler and shown as "Something went wrong." Fixed by dropping the redundant
  kwarg. Regression test: `tests/ui/test_practice_bridge.py`.
- **Widget menu label clipping**: `WidgetMenuPopup._resolve_width()` omitted the
  popup's own outer margin and the card body's margin from its width calculation,
  so "Collect new word" clipped by ~20px even after an earlier partial fix. Now
  accounts for every layer of chrome between the popup edge and the label.
  Regression test: `tests/ui/test_widget_menu_popup.py`.
- **No sliding "roller" on the widget-on toggle**: `QCheckBox::indicator` in QSS can
  only ever paint one flat glyph — there is no QSS equivalent of CSS's `::after`
  pseudo-element, so a plain styled checkbox can never grow a separate sliding
  thumb. Replaced with `ui/widget/toggle_switch.py`, a small `QAbstractButton`
  subclass that paints its own track + thumb directly.
- **Auto-meaning silently returning nothing**: both web dictionary APIs were timing
  out identically on a machine with restricted outbound HTTP (confirmed directly
  with `httpx.ReadTimeout`), and the pipeline had no source that didn't need a
  network call. Fixed by adding the local dictionary source (§2.3). If auto-meaning
  ever again returns nothing for every word, check network reachability to
  `api.dictionaryapi.dev` / Merriam-Webster / Google Translate first — the local
  source should still answer for any word actually in
  `assets/dictionary/wordnet-2025-dictionary.json`.
- **Words saved with a permanently blank meaning in Auto mode**: `CollectCardPopup`
  closes immediately on every successful save, and its `closeEvent` cancelled the
  in-flight lookup unconditionally — which cancelled the enrichment patch
  `save_word` had just scheduled against the new row. Any word saved before its
  lookup resolved therefore kept blank Meaning/Example forever, silently violating
  FR-2.9. Fixed by handing the lookup off on save (`_handed_off_lookup`) and only
  cancelling for genuinely discarded entries. Regression tests:
  `tests/ui/test_collect_card_lookup_handoff.py` (verified to fail if the fix is
  reverted).
- **"Launching does nothing" that isn't actually a launch failure**: `AppContext.
  shutdown()` unconditionally writes its **in-memory** preferences snapshot back to
  `preferences.json` on exit. If multiple instances of the app end up running at
  once (easy to do accidentally while testing — launching again without closing the
  previous one first), whichever instance closes *last* silently overwrites any
  preference change made in between, including `widget_visible`. Symptom: you set
  `widget_visible: true` directly in the file, relaunch, and it's back to `false`
  with no error anywhere. Before editing `preferences.json` or debugging "nothing
  appears," check Task Manager / `Get-Process` for more than one `vocab-v2`-derived
  process and close all of them first.

### 4.5 Editing runtime state directly (outside the repo)

`%AppData%\VocabularyTrainer\preferences.json` is **outside this workspace** and
outside any file-editing tool's sandbox — edit it via shell command
(`Get-Content`/`Set-Content` or equivalent), and always stop the running app first
so it doesn't overwrite your edit on its own next save. Useful fields:
`widget_visible` (bool), `widget_position` ([x, y]), `character` ("cat" |
"crocodile"), `merriam_webster_api_key`, `start_with_windows`,
`required_correct_writes` (1–10), `master_file_path`.

### 4.6 Adding the crocodile character

The code path is complete and tested; only the artwork is missing. Drop
`mini_ani_idle_crocodile.png` and `mini_ani_active_crocodile.png` into
`src/vocabulary_trainer/assets/floating_widget/` and it becomes selectable in
Settings → Widget → Character. Until both files exist, `assets.available_characters()`
deliberately excludes it (a character missing either pose would flicker
inconsistently between idle/active) and Settings reports it as artwork-not-installed
rather than silently falling back to the cat.

### 4.7 Dependency policy

Versions are declared as compatible ranges, never exact pins — `pyproject.toml`
`[project.dependencies]`. `pywin32` in particular publishes per-interpreter builds,
so an exact pin fails to resolve on any Python version it doesn't target. When
adding a dependency, follow the same pattern and avoid introducing pandas (see
§1.4's rationale) unless the reason for needing it is fundamentally different from
what was already rejected.

