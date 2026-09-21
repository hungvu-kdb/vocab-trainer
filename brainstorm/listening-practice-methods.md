# English Listening Practice — Method Options for Vocabulary Trainer

> Brainstorm document. Nothing here is committed; it's a menu to choose from and
> refine before any spec/design/implementation work starts.

## Why listening, and why these methods

The product today is vocabulary-only: Collect captures words, Practice drills
spelling recall from a typed meaning. There is no listening skill in the loop at
all — TTS exists, but only to *reward* a correct answer by speaking the word after
the fact (`integrations/tts.py`), not to *test* comprehension.

Before proposing methods I looked at what the L2-listening research actually
supports, because "listening practice" covers a wide range of activities with very
different evidence behind them:

- **Dictation / partial dictation / dictogloss** — writing down what you hear, in
  part or in full. Consistently shows medium-to-large effects on listening
  comprehension across studies, and it's the one listening activity that produces a
  *checkable* artifact (text), which matters a lot for a desktop app with no human
  teacher grading anything.
- **Shadowing** — listening and speaking along with audio in real time (or with a
  short lag). Repeatedly shown to improve both comprehension and pronunciation,
  because it forces continuous real-time processing rather than passive listening.
  Harder to score automatically (needs speech recognition), so it's a lower-fit
  candidate for this app unless paired with self-assessment rather than automated
  checking.
- **Extensive listening** (lots of comprehensible input, minimal interruption) vs.
  **intensive listening** (short clips, close attention, explicit noticing of sounds
  and structures) — these aren't competing methods, they're complementary and
  address different things: intensive listening trains the ear to *recognize* known
  words at speed; extensive listening trains fluency and automatization through
  volume of exposure. A small vocabulary app is naturally suited to intensive
  listening on its own word list — that's the material it already has.
- **Minimal-pair / phoneme discrimination drills** — training the ear on sounds
  that don't exist or don't contrast in the learner's L1 (a classic problem for
  Vietnamese speakers: consonant clusters, final consonants, some vowel length
  distinctions). This is narrow but well-supported and cheap to build because it
  reuses single-word audio.

Sources consulted (search snippets, not full papers — cite before using any claim
verbatim in product copy): shadowing effectiveness studies collected across EFL
contexts ([ResearchGate meta-collection](https://www.researchgate.net/publication/389112117_SHADOWING_TECHNIQUE_SHADOW_REPEAT_ECHO_REPEAT_WHEN_TEACHING_LISTENING_IN_A_FOREIGN_LANGUAGE),
[EJ1479870](https://files.eric.ed.gov/fulltext/EJ1479870.pdf)), dictation effect studies
([Kindai repository](https://kindai.repo.nii.ac.jp/record/14254/files/AA12508620-20151130-0043.pdf),
[dictation exercises on language skills](https://elibrary.edu.pl/pdf/2024/10.54691-525rm471.pdf)),
extensive/intensive listening comparison
([ERIC EJ1206536](http://files.eric.ed.gov/fulltext/EJ1206536.pdf),
[ResearchGate 372607255](https://www.researchgate.net/publication/372607255_Developing_L2_listening_comprehension_through_extensive_and_intensive_listening)),
and a 2022 meta-analysis on listening-strategy instruction reporting a medium
aggregate effect (d = 0.69) across 45 studies
([SAGE](https://journals.sagepub.com/doi/abs/10.1177/13621688211072981)).

**The constraint that shapes everything below**: this app has no audio *content*
pipeline today. It has SAPI TTS (speaks short strings, one voice at a time, on a
worker thread) and WAV/system-sound playback for two fixed cues. Every method here
either (a) works from TTS-spoken single words/phrases pulled from the existing
Excel word list — buildable now, no new asset pipeline — or (b) needs bundled/
imported audio clips, which is a materially bigger feature and is marked as such.

---

## Group A — buildable from what already exists (word list + TTS)

These reuse the collection/word model and `TextToSpeechService` almost as-is. No
new content pipeline, no licensing question, no network dependency.

### A1. Listening Dictation Drill ("hear it, spell it")

**What it is**: a new Practice mode, sibling to the existing writing drill. Instead
of showing Type + Meaning and asking for the Word, it **speaks** the word (TTS) and
asks the user to type what they heard. Everything else — mastery counting, penalty
scoring, mastery dots, the "reveal on miss" behavior, the session summary, the
separate practice-log workbook — is the *exact same machinery* already in
`domain/scoring.py` and `services/practice_service.py`; only the prompt changes
from "show meaning" to "speak word."

**Why this fits the evidence**: this is straightforward dictation, the
best-evidenced listening activity for measurable comprehension gains, and it's the
one that produces an automatically gradeable artifact — text, matched against the
known word via the same normalization (`domain/natural_key.py`) already used for
duplicate detection. No new scoring logic needed.

**What's genuinely new**:
- A "Listening" mode selector on the Practice setup screen (Writing / Listening),
  reusing the same collection multi-select, search, sort, and pool-size UI.
- The drill screen speaks instead of showing Meaning; an optional "replay" button
  (SAPI can be asked to speak the same string again — cheap).
- Decide: does Meaning show as a hint underneath, or is it *only* audio? Suggest a
  toggle ("show meaning as hint") defaulting off for challenge, on for beginners —
  this maps cleanly onto the existing required-writes stepper pattern (a per-session
  setting, not a permanent preference).

**Risk / honesty check**: SAPI voices vary a lot in naturalness and some Vietnamese
users may find certain Windows voices' pronunciation of tricky words (e.g. weak
forms, contractions, unusual stress) actually *wrong* rather than merely accented.
This should be flagged as a known limitation rather than promised as "authentic
listening," and the Settings → Audio voice picker + preview already lets a user
switch away from a bad voice.

### A2. Minimal-Pair / Confusable-Sound Drill

**What it is**: a companion drill focused specifically on words that are easy to
mis-hear — pulls pairs or small clusters from the user's own collections (e.g.
`ship`/`sheep`, `three`/`tree`, `light`/`right` — anything where the two normalized
forms differ by one phoneme-adjacent letter pattern) and asks "which word did you
hear," then optionally "type it." Can also ship a small **curated list** of classic
EN–VI confusable pairs (final consonants, consonant clusters, vowel length) as a
seeded starter collection, independent of what the user has collected.

**Why this fits**: phoneme discrimination training is well-supported and
specifically addresses the L1-transfer listening errors that generic dictation
doesn't target on its own (a user can "hear" `light` as `light` even when their
actual perceptual boundary is fuzzy, if dictation only ever presents one option at
a time). A forced-choice format surfaces the discrimination gap directly.

**What's genuinely new**: the pair-finding logic (a small domain module, testable
in isolation like `lookup_priority.py` or `shuffle.py` are today) and a very small
new drill screen (multiple-choice, not free-text). Reuses TTS and the existing
mastery/scoring pattern.

**Honest limitation**: automatically detecting which words in a user's *own*
collection form a "confusable pair" from spelling alone is a heuristic, not a
real phonetic analysis (no IPA data available offline). It will both miss real
pairs and flag false ones (e.g. `bear`/`beer` isn't really a common EFL confusion,
`ship`/`sheep` is). A curated seed list is more reliable than the auto-detected
one; the auto-detected one is a "nice extra," not the core of this feature.

### A3. "Speak It Back" self-check (lightweight shadowing, no speech recognition)

**What it is**: on the existing Collect card or a word's preview row, add a "Hear +
repeat" button. It plays TTS, then gives the user a few seconds of silence (a
visual countdown) during which they say the word aloud themselves, matching
stress/rhythm — the app does not listen or grade this. Fully self-assessed.

**Why this fits**: shadowing's evidence base is strong, but *automated* shadowing
assessment needs real-time speech recognition, which is a materially different
project (new dependency, accuracy problems, privacy questions if it ever touched
network STT). This is the honest middle ground: give the *structure* shadowing
needs (hear → immediately produce) without pretending to grade it. It costs almost
nothing to build — a button, a TTS call, and a timer — and it's the only listening
method here that also trains speaking/pronunciation, which nothing else in the app
touches at all.

**What's genuinely new**: one small UI affordance in an existing popup. No new
service, no new data model.

### A4. Listening Review Queue ("what have I saved, said aloud")

**What it is**: not a drill — a lean-back mode. Pick a collection, and the app
speaks every word (optionally + meaning, optionally + example sentence if one was
captured) in sequence, hands-free, like flipping through flashcards by ear. Useful
right before falling asleep, during a commute with the laptop open, etc. — this
maps onto the "Driller" persona's studying context but with zero typing.

**Why this fits**: this is **extensive listening** using the user's own known
vocabulary as comprehensible input — repetition and exposure rather than testing.
It's the complementary half to A1's intensive/testing approach, and the research
is explicit that both are useful for different things (automatization vs. focused
noticing).

**What's genuinely new**: a simple sequencer UI (play/pause/next, maybe speed —
SAPI supports rate control) built on the same `words_for_collection` data path the
Settings/Practice preview tables already use. No scoring, no new domain logic.

---

## Group B — needs an audio *content* pipeline (bigger, flagged clearly)

These require the app to import, store, and play back actual audio (podcasts,
audiobook clips, YouTube-derived clips, etc.) rather than synthesizing single words.
This is a genuinely different feature category: new file formats, storage
location, possibly transcript alignment, and licensing questions for any bundled
content. Listed for completeness since "listening practice" often implies this, but
none of it is a small addition to the current app.

### B1. Passage dictation / cloze dictation from imported audio

Play a short (10–30s) clip of real audio, ask the user to transcribe it fully or
fill blanks (cloze). This is the gold-standard version of dictation in the
literature — much stronger signal than single-word dictation because it exercises
segmentation (finding word boundaries in connected speech), not just word
recognition. Needs: an audio file importer, a transcript (either the user supplies
one, or a synced caption file, since there's no offline STT in this app today),
playback UI with scrub/replay-segment controls, and a text-diff scorer more
forgiving than exact match (word-level diff, not character match).

### B2. Graded-podcast integration / extensive listening library

Point users at existing graded-listening content (there are copyright-safe learner
podcasts and public-domain audio) and track "minutes listened" the way a
reading-log app tracks pages. This is a content-curation project more than a
software feature — the app would mostly be a player + a log, with the actual
audio living elsewhere or requiring user-supplied files.

### B3. Video/subtitle-based listening (shadowing or dictation against a video)

Load a video + its subtitle file, let the user practice against real captioned
speech (pause-and-repeat, cloze from the subtitle track). This is close to what
tools like Language Reactor do. Meaningfully larger scope: video playback,
subtitle parsing/sync, and — like B1/B2 — a content-sourcing story that's outside
this app's current "single Excel file, no external content" design philosophy
(see PROJECT.md §1.3 scope boundaries, which explicitly excludes anything content-
hosting-shaped so far).

---

## Suggested next step if you want to pick one

Given the existing architecture (Excel word list, native Qt Practice drill, SAPI
TTS, no server, no bundled media), **A1 (Listening Dictation Drill)** is the
straightforward next feature: it's dictation — the best-evidenced method for
measurable gains — and it is close to a *reskin* of the writing drill that already
exists, reusing scoring, mastery, penalties, session summary, and the practice-log
workbook without new domain logic. **A3 (Speak It Back)** is worth bundling
alongside it since it's nearly free to add and is the only option here that touches
speaking/pronunciation at all.

A2 and A4 are reasonable phase-two additions once A1's drill screen exists, since
they can share most of its plumbing (pool selection, TTS playback, session
lifecycle).

Group B is a real option only if you're open to the app taking on an audio-content
feature (importing/storing/playing real clips) as a new pillar alongside Collect
and Practice — worth a separate conversation before scoping, since it changes the
product's shape rather than extending it.
