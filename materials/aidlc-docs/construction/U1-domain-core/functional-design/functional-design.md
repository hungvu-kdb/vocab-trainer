# Functional Design — U1 Domain Core

**Unit**: U1 — Domain Core
**Requirements**: FR-3.2, FR-3.3, FR-5.9, FR-6.3, FR-6.4, FR-6.7, FR-6.10, FR-8.9
**Constraint**: pure Python. No file I/O, no network, no Qt imports. Every function here is
deterministic given its inputs (randomness is injected, never sourced internally).

This unit holds the rules that must not vary between the two UI surfaces. Each algorithm below is
specified precisely because the whole point of isolating them is that they can be exhaustively tested
without mocks.

---

## 1. Natural Key Normalization (FR-8.9)

**Purpose**: one definition of when two entries are the same word.

```
normalize(value):
    1. strip leading and trailing whitespace
    2. collapse any internal whitespace run to a single space
    3. casefold          (not lower() — see below)
    return result

natural_key(word, collection_name):
    return (normalize(word), normalize(collection_name))
```

**Why `casefold()` rather than `lower()`**: `casefold` is the Unicode-correct operation for
caseless matching. `lower()` would treat the German "ß" and "ss" as different, and mishandles a few
other scripts. For an English-vocabulary app this rarely bites, but choosing the correct primitive
costs nothing.

**Why internal whitespace collapses**: the app stores phrases, not just single words (FR-2.2 includes
"phrase"). `"give up"` and `"give  up"` are the same phrase, and a user who types two spaces has not
created a new entry.

**Trailing-punctuation is deliberately NOT normalized.** `"well"` and `"well,"` remain distinct.
Stripping punctuation would be a guess about intent, and the requirements only specify case and
whitespace.

**Collection name conflict** (FR-2.5, FR-7.8): `names_conflict(a, b)` is `normalize(a) == normalize(b)`.
This is what makes recasing your own collection permissible (E7-S7 branch 4c) — the caller compares
the normalized form against *other* collections, not against itself.

---

## 2. Definition Selection Within One Source (FR-3.2)

**Purpose**: pick the definition whose part of speech matches what the user chose.

```
select_definition(candidates, preferred_pos):
    if candidates is empty:
        return None
    for c in candidates:                          # first match wins, order preserved
        if c.part_of_speech == preferred_pos:
            return c
    return candidates[0]                          # fall back to first available
```

**Order matters and is preserved.** Dictionary APIs return definitions roughly by commonness, so
"first available" is a meaningful fallback rather than an arbitrary one.

**Candidates with `part_of_speech is None`** (a source that reports no part of speech) can never match
the preferred value, so they only surface through the fallback. That is correct: a known match should
always beat an unknown.

---

## 3. Cross-Source Priority Selection (FR-3.3, FR-3.5)

**Purpose**: with all three sources queried concurrently, decide which answer to keep.

```
PRIORITY = (FREE_DICTIONARY, MERRIAM_WEBSTER, GOOGLE_TRANSLATE)

select_result(results):                           # results: source -> LookupResult
    for source in PRIORITY:
        r = results.get(source)
        if r is not None and not r.is_empty:
            return r
    return LookupResult(meaning=None, example=None, source=NONE)
```

`is_empty` is `meaning` being None or blank after stripping. A source that technically responded but
returned nothing usable is treated as not having answered — otherwise an empty
Free Dictionary response would beat a good Merriam-Webster one purely on priority.

**Note on the concurrent model (CQ2 = B)**: this function is why concurrency does not change the
stored outcome. All three are asked; priority still decides. A source that times out simply is not in
the mapping.

---

## 4. Shuffle (FR-5.9)

```
shuffled(pool, rng):
    result = list(pool)                           # never mutate the caller's sequence
    rng.shuffle(result)
    return result
```

**Property that must hold**: the output is a permutation of the input — same elements, same
multiplicity. Empty and single-element inputs are valid and return equivalent lists.

**`rng` is injected** so tests are deterministic with a seeded `Random`. A module-level default is used
in production.

---

## 5. Reinsertion Avoiding the Next Draw (FR-6.7)

**Purpose**: a word that was answered correctly but is not yet mastered goes back into the pool —
but must not be the very next word shown, or the user just retypes what they saw a second ago.

Draw convention: **index 0 is the next word drawn** (the pool is consumed from the front).

```
reinsert_avoiding_next(pool, item, rng):
    if len(pool) == 0:
        pool.append(item)                         # only word left; index 0 unavoidable
        return
    # valid insertion indices are 1 .. len(pool) inclusive
    index = rng.randint(1, len(pool))
    pool.insert(index, item)
```

**The boundary case is the interesting part.** When the pool is empty, index 0 is the only possible
position, so the word does repeat immediately. The requirement says "provided at least one other word
remains" — so this is compliant, and it matches E6-S3 branch 3a: a single-word pool must keep drawing
that word rather than stalling.

**Upper bound is `len(pool)` inclusive**, meaning append is allowed. With a pool of one other word,
valid indices are exactly `{1}` — the word goes behind the other one.

---

## 6. Answer Matching (FR-6.4)

```
answer_matches(submitted, target):
    return normalize(submitted) == normalize(target)
```

Reuses the natural-key normalizer, so answer matching and duplicate detection cannot drift apart.
Consequences, all intended:
- Case differences pass: `"Ubiquitous"` matches `"ubiquitous"`.
- Padding passes: `"  ubiquitous  "` matches.
- Internal whitespace collapse passes: `"give  up"` matches `"give up"`.
- Spelling errors fail — which is the entire point of the drill.

An empty submission normalizes to `""` and cannot match any non-empty target. The UI additionally
ignores empty submissions entirely (E6-S1 branch 7a) so they never reach here as attempts.

---

## 7. Score and Progress (FR-6.3, FR-6.10)

```
compute_score(correct_attempts, penalties):
    return correct_attempts - penalties           # may be negative

total_required_attempts(pool_size, required_correct):
    return pool_size * required_correct
```

**Negative scores are returned, not clamped.** The formula is defined as correct minus penalties, and
E6-S4 branch 2a explicitly requires displaying a negative value rather than hiding it at zero.

**`total_required_attempts` is the progress denominator, computed once at session start.** It is the
minimum number of correct attempts needed to master the whole pool. Actual attempts will exceed it
whenever the user makes mistakes, so the caller must clamp the *displayed* fraction to 100% — that
clamping belongs in the presentation layer, not here, because the raw numbers are what the summary
reports.

---

## 8. Mastery Check (FR-6.6)

```
PracticeWordState.is_mastered_at(required):
    return self.consecutive_correct >= required
```

`>=` rather than `==` so an off-by-one elsewhere can never make a word unmasterable and strand the
session in an infinite loop.

**The invariant this unit guarantees**: nothing in `domain` ever decreases `consecutive_correct`.
There is no function here that can. A penalty is a separate counter. This is FR-6.8's
"mastery progress is not reset by a wrong answer", enforced by omission — the operation simply does
not exist.

---

## 9. Data Model Notes

**Frozen dataclasses** for `WordEntry`, `Collection`, `CollectionSummary`, `DefinitionCandidate`,
`LookupResult`, `SessionSummary`, `AttemptOutcome`. Immutability means a repository result cannot be
mutated by a caller and silently diverge from what is on disk.

**`PracticeWordState` is mutable** — `consecutive_correct` changes during a session by design.

**`AppPreferences` is mutable** — it is loaded, edited field by field from Settings, and saved back.

**`WordEntry.natural_key`** is a property delegating to `natural_key()`, so no caller recomputes it.

**Enums are `StrEnum`** so their values serialize directly into the workbook and JSON without a
conversion table, and read as plain strings when a user opens the file in Excel.

---

## Test Plan

| # | Target | Cases |
|---|---|---|
| 1 | `normalize` | leading/trailing space, internal run collapse, case, unicode casefold, empty, already-normal |
| 2 | `natural_key` | identical inputs match; case-only difference matches; whitespace-only difference matches; different word fails; different collection fails |
| 3 | `names_conflict` | exact, case-only, whitespace-only, genuinely different |
| 4 | `select_definition` | pos match found; no pos match falls back to first; empty returns None; None-pos candidates only match via fallback; first of several matches wins |
| 5 | `select_result` | each source alone; all three; higher-priority empty defers to lower; all empty returns NONE; missing keys |
| 6 | `shuffled` | permutation preserved (multiset equality); empty; single; input not mutated; seeded determinism |
| 7 | `reinsert_avoiding_next` | never index 0 when pool non-empty (exhaustive over many seeds); index 0 when pool empty; single-other-word puts it at index 1; length grows by exactly 1 |
| 8 | `answer_matches` | exact; case; padding; internal whitespace; wrong spelling; empty submitted |
| 9 | `compute_score` | positive, zero, negative |
| 10 | `total_required_attempts` | typical; pool of 1; required of 1 |
| 11 | `is_mastered_at` | below, exactly at, above threshold |
| 12 | Frozen dataclasses | mutation attempt raises |

Coverage target: 100% of U1 — it is pure, so there is no excuse for less.
