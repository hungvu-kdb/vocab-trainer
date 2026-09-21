# Change log

Newest first. One entry per change, timestamped when the change was made.

> Entries before 2026-09-17 17:00 were reconstructed from file modification times,
> since this folder is not under version control and the log was created after the
> fact. Times are accurate to the minute; the grouping into entries is by feature.

---

# Date 2026-09-21 21:56

**Release build v2.1.0, shipped to `send_out/` via the "wrap up" workflow.**

First wrap-up run against the checklist process. Baseline was v2.0.0 (the original
`.cmd` installer). User confirmed via `send_out/wrap-up-checklist.md`, then deleted
per the wrap-up steering's cleanup step.

Included:
- Configurable widget size (50–300% slider)
- Shortened/unclipped type-chip labels on the Collect card
- Reworked penalty scoring (fixed this session, see the 21:28 entry above) — a wrong
  answer now adds one extra required repetition, capped so a session cannot fail to
  terminate
- The `.exe` installer format itself (non-optional, ships regardless of selection)

Excluded from this release (left in the source tree, not reverted, available for a
future wrap-up):
- Optional local AI meanings via Ollama, and its companion timeout fix
- Multi-word ("Several") capture
- Speech-bubble lookup confirmation ("I found it!" / "I couldn't find it")

**One item shipped despite being listed as excludable, and that is worth stating
plainly:** the checklist described "Looking up… instead of a blank dash" (the
pending-lookup preview indicator) as separable from the Ollama feature. It is not,
in the current code — `previewCell()` in both `settings.js` and `practice.js` renders
that state for *any* pending lookup via `PendingEnrichmentRegistry`, which every
save creates regardless of source, not only Ollama ones. Splitting it out would have
meant writing a real revert (restoring the old two-state blank/dash rendering) rather
than a no-op checkbox. Since dictionary-only lookups are typically sub-second, the
"Looking up…" text is rarely seen in practice with Ollama excluded, so it shipped
as-is rather than doing throwaway revert work for a state that's nearly invisible
without the feature it was built alongside. Flagged here rather than silently
included.

- `pyproject.toml` — version `2.0.0` → `2.1.0`. Minor bump: one new user-visible
  feature (widget size) plus a behavior change (scoring), not just a fix.
- `install_tool/build_exe.py` rebuilt the wheel from `src/` fresh, generated the
  icon, froze with PyInstaller, self-checked the binary. `20,420,754` bytes, valid
  64-bit PE.
- Confirmed before building: the installer never writes to
  `%AppData%\VocabularyTrainer` (the workbook/collections) anywhere in
  `installer_main.py` — only `%LocalAppData%\VocabularyTrainer` (the runtime venv)
  is ever modified, so a reinstall over an existing copy preserves user data. Read
  the full installer source to confirm this rather than assuming it still held.
- `send_out/` replaced entirely: old `wrap-up-checklist.md` deleted,
  `Install-VocabularyTrainer.exe` and a new plain-language `release-notes.md` copied
  in.

Verified: full suite green (784 tests) before building. Did not update
`current_published_installation_package/` — per the wrap-up steering, that only
happens once the user confirms they are actually distributing this build.

---

# Date 2026-09-21 21:28

**Fixed the NOR (penalty/repetition) scoring rework so a session can no longer fail
to terminate.**

This closes the open question left from the previous NOR change: whether a word's
required-repetition count could grow without bound from repeated mistakes. It could,
and it did — `remaining_repetitions` had no ceiling, so a wrong answer added one to a
word's target and a correct answer removed one, meaning strict wrong/right
alternation held the target on a permanent plateau and never reached zero. A learner
who was persistently 50/50 on one word could never finish the session.
`test_a_session_with_misses_still_terminates` caught exactly this and was red on the
tree before this fix.

- `domain/scoring.py` — added `MAX_PENALTY_REPETITIONS_MULTIPLIER = 3` and a private
  `_target` helper. A word's effective target can now be inflated by wrong answers
  only up to `required_correct * 3`, never further. 3x was chosen so the cap is
  never felt in ordinary play — a default `required_correct = 3` word would need 6+
  wrong answers before the ceiling engages at all — while still being a small, fixed
  bound that makes termination provable rather than merely likely.
- `domain/models.py` — `PracticeWordState.remaining_for` docstring updated to note
  the cap; behavior unchanged, it already delegated to `remaining_repetitions`.
- `tests/domain/test_scoring.py` — added `TestRepetitionCap`: confirms the two
  originally requested examples (NODR=3, one wrong → 4; one correct + two wrong → 4)
  are untouched by the cap since they're far below it; confirms the target stops
  growing past the ceiling even at 1000 wrong answers; pins a concrete strict
  wrong/right alternation trace reaching mastery within a proven bound.
- `tests/services/test_practice_service.py` — the previously-failing test now passes
  and asserts it stayed under its guard rather than merely not hanging forever, so a
  future regression that quietly raises the attempt count is still caught.

**What did not change**: the core NOR rule itself — mistakes still cost one extra
repetition on top of the score penalty, running totals not a consecutive streak,
mastery still a one-way gate floored at zero. Only the missing ceiling was added.

Verified: proved termination analytically for `required_correct` 1 through 10 under
the exact adversarial alternation pattern before trusting the test suite, then
confirmed the full suite — 784 passed, no regressions, no diagnostics on either
changed file.

---

# Date 2026-09-17 20:59

**The character now says "I found it!" or "I couldn't find it" in a small speech
bubble beside the widget when a lookup resolves (FR-3.11).**

Previously a lookup that finished after the Collect card closed had nowhere to report
itself: the meaning appeared in the workbook with no acknowledgement on screen. Since
the card closes the instant a word is saved, that was the normal case, not the edge
case.

- `ui/widget/speech_bubble_popup.py` — **new.** A transient message anchored beside
  the character. `ToolTip` window flag rather than `Popup`, because a Popup grabs
  input and would swallow the user's next click somewhere else entirely. Never takes
  focus, dismisses itself after 4s, and closes on click for anyone who would rather
  not wait. Reuses `place_beside` so it flips away from a screen edge like every other
  popup, but top-aligned — bottom-aligning would tuck it behind the taskbar when the
  widget sits in its default corner.
- `ui/widget/lookup_announcer.py` — **new.** A `QObject` that turns a worker-thread
  lookup completion into a UI-thread signal. This exists for a hard reason: Qt widgets
  may only be touched from the thread that owns them, so building the bubble directly
  in the lookup callback would be undefined behaviour.
- `app.py` — owns the announcer and the bubble, **not** the Collect card. Anything
  owned by the card would be destroyed before the result it was waiting for arrived.
  Only one bubble at a time: a batch of ten words resolving over a few seconds would
  otherwise stack ten overlapping popups.
- `ui/widget/collect_card_popup.py` — hands each saved word's in-flight lookup to the
  announcer. Manual-meaning saves are not announced: the user supplied the meaning, so
  there is nothing to find.
- `ui/theme/qt_stylesheet.py` — `SpeechBubble` styles. The not-found variant is
  grey-accented, not red: failing to find a rare word is an ordinary outcome and an
  error colour would overstate it.

Verified with the real `gemma:2b` model end to end: three words produced three
bubbles — "I found it!" for *serene* and *mountain*, "I couldn't find it" for a
nonsense word. Also confirmed the bubble never becomes the active window, self-
dismisses, and closes on click. 759 tests pass.

A note on method, because it nearly produced a wrong conclusion: my first live run
showed only 2 bubbles for 3 saved words, which looked like a real defect. It was the
test — its wait loop stopped as soon as the pending count hit zero, but an
announcement crosses threads as a queued signal and is delivered on a *later*
event-loop turn. The app's event loop never stops, so it was never affected.

---

# Date 2026-09-17 20:58

**Collect can now take several words at once, comma-separated, looking them all up in
parallel (FR-2.12).**

A "One word / Several" toggle sits above the input. In Several mode the text is split
on commas, and each fragment is trimmed, whitespace-collapsed and lowercased before
saving.

- `domain/word_list.py` — **new.** `parse_word_list`, reusing `normalize_word` rather
  than hand-rolling trim/collapse/lowercase, so batch de-duplication matches the
  workbook's own definition of word identity. Forgiving by design: a trailing or
  doubled comma is dropped and an in-batch repeat collapses, rather than rejecting the
  whole entry — refusing everything over a stray comma would cost the user all of what
  they just typed. Order typed is preserved, first occurrence winning, so the
  confirmation reads in the order written.
- `services/collect_service.py` — `save_words` plus a `BatchOutcome` dataclass. Every
  lookup is started **before** any row is written, so ten words cost roughly one
  lookup's wait rather than ten; writing inside the loop would have serialised them
  behind each workbook write. Reuses `save_word` per word rather than reimplementing
  save-then-patch. `BatchOutcome` carries three lists because a batch genuinely has a
  mixed result, and owns its own `summary` string so the counts and the sentence cannot
  drift apart.
- `ui/widget/collect_card_popup.py` — the mode toggle, plus a live hint echoing what
  the commas parsed into. The hint matters because the parsing is lossy in ways the
  user cannot otherwise see: words are lowercased and repeats vanish, and this makes a
  stray comma visible *before* saving. Multi-word mode disables Manual meaning — one
  typed definition cannot be right for several different words — and does not start a
  lookup per keystroke, which would fire dozens of requests for words still being
  typed.
- `ui/theme/qt_stylesheet.py` — `FieldHint` style for that echo.

**Duplicates are skipped, not offered for resolution.** The single-word flow shows a
Keep/Replace/Delete popup, which is right when the user is looking at one word;
asking that five times for a batch would be worse than reporting "Saved 1, skipped 1
already there (hello)" and letting them handle those individually.

**Two deliberate limits.** Lowercasing means proper nouns entered in a batch lose
their capitals — that is what was asked for, but it is worth knowing. And a locked
workbook stops the batch at the word that hit the lock, rather than writing some rows
and not others with no clear boundary.

Verified: 14 parsing cases including `,,,`, `"hello,,world"` and `"a, b, A"`; six
words with 0.3s lookups completed in 0.36s (sequential would have been ≥1.8s); a
batch of three saved in 0.13s with all three rows written immediately and enriched
afterwards; and end to end with the real `gemma:2b` model, where *serene* and
*mountain* got meanings and a nonsense word stayed blank but still saved. 759 tests
pass.

---

# Date 2026-09-17 17:39

**Collection previews now show "Looking up…" for a row whose meaning is still being
fetched, instead of the same em dash used for a lookup that found nothing.**

The workbook cannot distinguish the two states — both are an empty cell — so a word
saved two seconds ago looked identical to one whose lookup failed last week. The user
had no way to know whether waiting would help. This matters more now that the local
LLM can take 15s or more.

The Collect card already knew, through its `LookupHandle`, but that knowledge was
private to one popup. Making it visible needed a shared place to publish it:

- `services/pending_enrichment.py` — **new.** `PendingEnrichmentRegistry`: a
  thread-safe set of natural keys with an enrichment patch outstanding, plus an
  observer channel. Keyed by natural key rather than row position, matching every
  other identity decision in the app, so a row that moves when the workbook is sorted
  in Excel is still recognised. **Deliberately not persisted** — a pending lookup
  cannot outlive the process running it, so a registry restored from disk would claim
  rows are being worked on by a thread that no longer exists.
- `services/collect_service.py` — `_schedule_enrichment` marks the row pending and
  clears it in a `finally`, so an unexpected failure cannot leave a row stuck showing
  "Looking up…" forever. Cleared on success, empty result and failure alike: the claim
  is only that the row is *waiting*.
- `services/settings_service.py`, `services/practice_service.py` —
  `is_lookup_pending`, so both previews report through the same source and cannot
  disagree.
- `services/app_context.py` — constructs the registry and shares one instance.
- `ui/web/settings_bridge.py`, `ui/web/practice_bridge.py` — each preview row carries
  `lookupPending`, plus an `anyPending` summary so the page does not have to scan rows
  to decide whether to keep polling.
- `ui/web/assets/settings.js`, `practice.js` — three cell states where there were
  two: a value, "Looking up…" with a spinner, or the em dash. Polls once a second
  **only while a row is actually pending**, and stops as soon as none is; a permanent
  timer would keep re-reading the workbook for a modal left open on a finished
  collection. `previewCollection` doubles as the open/closed flag, so a reply arriving
  after the modal closes is discarded rather than rendered into a hidden table.
- `ui/web/assets/app.css` — `.preview-pending` and a spinner, brand-coloured because
  this state is temporary and worth noticing, where the em dash is meant to recede.
  The animation is disabled under `prefers-reduced-motion`; the text alone still
  carries the meaning.

Every new parameter is optional, so existing construction sites are untouched — a
caller with no registry simply gets the old blank-cell behaviour.

Verified in the live Settings modal with a deliberately slow source: both states
render simultaneously (one row "Looking up…" with a spinner, another showing the em
dash), the meaning replaces the indicator when it lands, polling starts and stops on
its own, and closing the modal clears both the timer and the collection. Also checked
that a lookup finding *nothing* still stops being pending, and that manual-meaning
entries are never pending. 759 tests pass.

One note on method: my first UI check failed on four assertions, and the cause was
the test, not the code — a 6s stub lookup expired *during* the assertions, so the
first read found it already finished. Widened to 25s and all states appeared.

---

# Date 2026-09-17 17:24

**Widened the overall lookup deadline to 60s whenever the local AI model is
available, fixing a bug that stopped it ever being used.**

The whole-lookup ceiling was 8s, sized for dictionary requests. A local model takes
5–15s, so it was being cancelled before it could answer and the dictionaries won by
default — switching the feature on appeared to do nothing.

This was missed when the feature was added because the live check called
`OllamaClient.generate` directly, bypassing `LookupService` and its deadline. The
lesson is worth keeping: verifying a component in isolation says nothing about the
path the app actually takes.

- `services/lookup_service.py` — added `_GENERATIVE_TIMEOUT = 60.0` and
  `_deadline_for`, which picks the ceiling from the sources **available on this
  lookup**. So a user who never enables the model keeps the tight 8s deadline, and
  one who switches it off gets it back immediately. The `timeout` parameter became
  `float | None`: `None` means "decide for me", while an explicit value is always
  honoured, which keeps the existing timeout tests meaningful rather than silently
  overridden.
- `integrations/ollama_client.py` — raised `_GENERATE_TIMEOUT` from 45s to 60s. It
  was the shorter of the two and would have been the real ceiling regardless of what
  the service allowed, making the wider limit a fiction. The two now agree, and the
  docstring says why they must.

**This is a ceiling, not a delay.** `asyncio.wait` returns as soon as every source
finishes, so nothing slows down: measured 0.32s for a fast lookup and 0.11s with the
model switched off. The full 60s is only spent while the model is genuinely still
working — and it costs the user nothing either way, since the word is saved
immediately and the row patched when the result lands.

Verified end to end through the real service with `gemma:2b`: "serene" resolved in
12.9s with `source: ollama` — the exact case the old ceiling would have killed at 8s.
A 12s model under a forced 8s ceiling still falls back to the dictionary rather than
returning nothing. 759 tests pass, no regressions.

---

# Date 2026-09-17 15:02

**Optional local-AI meanings via Ollama (FR-3.10).** A fifth lookup source that
*generates* an English meaning and example with a model running on the user's own
machine, instead of looking one up.

Off by default and skipped entirely unless switched on **and** given a model, so a
machine without Ollama behaves exactly as it did before.

- `domain/models.py` — added `LookupSource.OLLAMA`, plus `ollama_enabled` and
  `ollama_model` to `AppPreferences`.
- `domain/lookup_priority.py` — `PRIORITY` now leads with `OLLAMA`. It ranks first
  *when available*, which it is not unless the user opted in, so the order is
  unchanged for everyone else.
- `integrations/ollama_client.py` — **new.** Talks to Ollama's HTTP API on
  `127.0.0.1:11434`. Loopback only and deliberately not configurable: a remote host
  would send every collected word to a third party. Asks for a JSON response with
  `format: "json"`, and tolerates a markdown fence, surrounding prose, or the literal
  string `"null"`, all of which smaller models emit. 2s timeout for the model list,
  45s for generation.
- `integrations/lookup_client.py` — added the `GenerativeLookupClient` protocol. A
  separate protocol rather than widening `fetch`, so adding a generative source did
  not force a parameter onto the four dictionary clients that have no use for it.
- `services/lookup_service.py` — `_request` dispatches to `generate` or `fetch`
  depending on what a client offers. The chosen part of speech reaches the model as a
  constraint, not a post-hoc filter.
- `services/settings_service.py` — `set_ollama`, `ollama_models`,
  `ollama_is_running`. Refuses to enable without a model and returns the *achieved*
  state, so the toggle reverts rather than showing "on" over a source that cannot
  answer.
- `services/app_context.py` — constructs and wires `OllamaClient`.
- `data/preferences_store.py` — persists both new fields, with the store's usual
  per-field corruption tolerance.
- `ui/web/settings_bridge.py` — `ollama_state` and `set_ollama` slots. Added
  `_await`, which drives an async service call on a worker thread; `asyncio.run` on
  the calling thread would freeze the Settings window while Ollama was probed.
- `ui/web/assets/settings.{html,js}` — Local AI model section in General: on/off
  switch, model dropdown, Refresh button. Only installed models are listed, so the
  dropdown can never offer one that would fail on first use. An empty list is
  explained by cause (Ollama absent vs. no models pulled), and a model chosen then
  deleted is reported in a banner rather than silently ignored.
- `ui/widget/collect_card_popup.py` — status line reads "Generated by local AI
  model".
- `tests/domain/test_lookup_priority.py` — updated the pinned `PRIORITY` tuple, an
  intended change.

**Deliberately not packaged.** Ollama is a separate program the user installs
themselves; nothing was added to `pyproject.toml` or the installer.

Verified against a real local model (`gemma:2b`): "serene" → *"calm and peaceful,
with a sense of tranquility"* in 11.3s. Also checked that an unreachable Ollama
returns empty and never raises, and that an empty LLM answer cannot outrank a usable
dictionary one. 759 tests pass — up from 757 because two existing tests parametrize
over every `LookupSource`, so the new member generated two more cases.

---

# Date 2026-09-17 14:59

**Shortened the type chips on the Collect card.** The chips were being compressed
below the width their own text needed, so labels were clipping mid-word — "noun"
rendered as "1our", "adjective" as "jecti".

- `ui/widget/collect_card_popup.py` — added `CHIP_LABELS`: `N`, `V`, `adj`, `adv`,
  `ph`. Display only; the stored value is still the full `PartOfSpeech` word, so the
  workbook stays readable in Excel and the lookup pipeline keeps matching on the real
  part-of-speech name. Each chip carries the full word as its tooltip, and takes a
  minimum width from its own `sizeHint` so the layout can never squeeze a label
  again.

Abbreviating rather than widening the card: it has to stay narrow enough to sit
beside the widget without covering what the user is reading. Measured on a live card
— all five chips render at full width, using 192px of the available 294px.

---

# Date 2026-09-16 23:44

**Replaced the `.cmd` installer with a real single-file `.exe`.**

- `install_tool/installer_main.py` — **new.** The installer program, rewritten from
  PowerShell into Python.
- `install_tool/build_exe.py` — **new.** Builds the wheel, generates a
  multi-resolution icon from the character artwork, freezes everything with
  PyInstaller, then verifies the output is a genuine 64-bit PE binary.
- Removed `Install-VocabularyTrainer.cmd`, `build_installer.py`,
  `installer_body.ps1`.

Rewritten rather than wrapped because PyInstaller needs a real program to freeze, and
because PowerShell 5.1 had caused three separate bugs in the previous version: it
mangles double quotes when rebuilding a native command line, it turns any native
stderr output into a terminating error under `$ErrorActionPreference = 'Stop'` (so a
routine pip notice aborted a healthy install), and it interprets pipe characters
inside a quoted `-Command` argument.

Two bugs found while testing the result:

- The installer **refused to install on a clean machine**, reporting a phantom
  running app. Its process query runs through PowerShell, whose own command line
  contains `vocabulary_trainer` — so it matched itself. Fixed by also requiring
  `Name -like 'python*'`. The uninstaller had the same flaw and would have killed its
  own shell mid-run.
- `data/preferences_store.py` — a **UTF-8 BOM made the app discard every
  preference**. `json.loads` failed on the leading `\ufeff`, defeating the per-field
  tolerance the store is built around. Now reads with `utf-8-sig`. Plausible in real
  use: PowerShell's `Set-Content -Encoding utf8` and several Windows editors add a
  BOM.

Tested end to end: fresh install, shortcut launch, and uninstall — which removes the
app and both shortcuts while preserving all four user-data files.

---

# Date 2026-09-16 23:31

**Configurable widget size (FR-7.15).** A 50–300% slider in Settings → Widget,
default 100%, applied live as it is dragged.

- `domain/models.py` — `widget_scale_percent`, plus `MIN_/MAX_WIDGET_SCALE_PERCENT`
  and `clamp_widget_scale_percent` defined once so three layers share one definition
  of the range.
- `data/preferences_store.py` — persists it, clamping a hand-edited value.
- `services/widget_state_service.py` — `scale_percent`, `scale_factor`,
  `set_scale_percent`. The service *rejects* out-of-range input rather than clamping
  it, because silently storing 300 when the caller asked for 900 would hide a bug;
  the store clamps instead, because a hand-edited file has no caller to correct.
- `services/settings_service.py` — delegates, so the Settings tab and the widget
  cannot disagree.
- `ui/widget/floating_widget_window.py` — scales from the source artwork every time,
  never from the already-scaled pixmap, so repeated changes do not compound
  interpolation blur.
- `ui/web/assets/settings.{html,js}`, `app.css`, `ui/web/settings_bridge.py` —
  slider, value readout and Reset button. The range travels from the domain layer
  through the bridge into the slider's `min`/`max` rather than being hardcoded in
  markup, so the control cannot offer a size the service would refuse.

Two bugs found by measuring real geometry rather than trusting unit tests:

- The widget **grew but never shrank** — 300%→100% left a small character in a large
  window. `resize()` is floored by the minimum size Qt retains from the largest
  pixmap held; fixed by setting a fixed size on both the label and the window.
- `_default_position` and `_clamped` hardcoded the unscaled 92px width, which would
  have hung a 300% widget off the right edge on first run.

---

# Date 2026-09-16 22:00

**Single-file installer (first version).** A self-extracting `.cmd` with the
application wheel embedded as base64, so one file could be sent to a non-technical
recipient. Per-user install to `%LocalAppData%`, no admin rights, its own private
virtual environment, Start Menu and desktop shortcuts, an Apps entry and an
uninstaller that preserves user data.

Superseded by the `.exe` on 2026-09-16 23:44; kept here because the bugs it exposed
are recorded in `install_tool/README.md` and still apply.

Also verified during this work that **start-with-Windows already functioned
correctly** — it registers `pythonw.exe -m vocabulary_trainer` and that command
genuinely launches the installed app — so a planned fix was dropped rather than
changing working code.
