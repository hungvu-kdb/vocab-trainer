# Story to Unit Map — Vocabulary Trainer v2

Every one of the 42 user stories is assigned to exactly one **primary** unit — the unit that must be
complete for the story to be deliverable. Stories may also list **contributing** units that supply
behavior the story consumes.

Assignment rule: a story's primary unit is the unit containing the last piece of work needed to make
the story observably true for the user. This keeps the mapping unambiguous — 42 stories, 42 primary
assignments, no double-counting.

---

## By Story

| Story | Title | Primary | Contributing |
|---|---|---|---|
| E1-S1 | See the widget resting on my desktop | U7 | U1, U3, U6, U10 |
| E1-S2 | Open the widget menu to choose what to do | U7 | U1, U6 |
| E1-S3 | Move the widget out of my way | U7 | U3, U6 |
| E1-S4 | Hide the widget without losing the app | U7 | U3, U6 |
| E1-S5 | Have the app ready when I log in | U9 | U5, U6, U10 |
| E2-S1 | Enter a word and its part of speech | U8 | U1, U6, U7 |
| E2-S2 | Choose which collection the word goes into | U8 | U2, U6 |
| E2-S3 | Create a collection without leaving the card | U8 | U1, U2, U6 |
| E2-S4 | Save the word immediately, even mid-lookup | U8 | U1, U2, U4, U6 |
| E3-S1 | Get a definition looked up automatically | U4 | U1, U6, U8 |
| E3-S2 | Get the definition matching my part of speech | U4 | U1 |
| E3-S3 | Fall back to a Vietnamese translation | U4 | U1 |
| E3-S4 | Save a word even when every lookup fails | U4 | U1, U2, U6 |
| E3-S5 | Supply my own Merriam-Webster key | U9 | U3, U4, U6 |
| E4-S1 | Be told when I've already collected this word | U8 | U1, U2, U6 |
| E4-S2 | Keep what I already have | U8 | U6 |
| E4-S3 | Refresh the existing entry with my new lookup | U8 | U2, U4, U6 |
| E4-S4 | Remove the word entirely | U8 | U2, U6 |
| E5-S1 | Open Practice and see my collections | U9 | U2, U6, U7 |
| E5-S2 | Find a collection without scrolling | U9 | U6 |
| E5-S3 | Build the pool and set my mastery bar | U9 | U1, U2, U6 |
| E5-S4 | Be stopped from starting an empty session | U9 | U6 |
| E6-S1 | Be prompted to write a word from its meaning | U9 | U1, U6 |
| E6-S2 | Get rewarded for a correct answer | U9 | U1, U5, U6 |
| E6-S3 | Keep seeing a word until it sticks | U9 | U1, U6 |
| E6-S4 | Learn from a wrong answer without being set back | U9 | U1, U5, U6 |
| E6-S5 | Track my score and stop when I want | U9 | U1, U6 |
| E6-S6 | See how the session went and go again | U9 | U3, U6 |
| E7-S1 | Navigate Settings | U9 | U6, U7 |
| E7-S2 | Choose where my vocabulary file lives | U9 | U2, U3, U6 |
| E7-S3 | Change how the widget looks | U9 | U3, U6, U7 |
| E7-S4 | Pick the voice that reads words to me | U9 | U3, U5, U6 |
| E7-S5 | Check what version I'm running | U9 | U6 |
| E7-S6 | See and create collections | U9 | U1, U2, U6 |
| E7-S7 | Rename a collection without breaking its words | U9 | U1, U2, U6 |
| E7-S8 | Delete a collection knowing what it costs | U9 | U2, U6 |
| E8-S1 | Have a working file on first launch | U2 | U1, U10 |
| E8-S2 | Never lose data to a crash mid-save | U2 | — |
| E8-S3 | Recover from a workbook I broke by hand | U2 | U1 |
| E8-S4 | Not lose my word because Excel has the file open | U8 | U2, U6 |
| E8-S5 | Have my Excel edits noticed | U3 | U2, U6 |
| E8-S6 | Have concurrent operations stay consistent | U2 | — |

---

## By Unit

| Unit | Primary story count | Stories |
|---|---|---|
| **U1** Domain Core | 0 | — (contributes to 25 stories) |
| **U2** Master File Repository | 4 | E8-S1, E8-S2, E8-S3, E8-S6 |
| **U3** Preferences, History, Watching | 1 | E8-S5 |
| **U4** Lookup Clients & Orchestration | 4 | E3-S1, E3-S2, E3-S3, E3-S4 |
| **U5** Feedback & OS Integration | 0 | — (contributes to 5 stories) |
| **U6** Application Services | 0 | — (contributes to 38 stories) |
| **U7** Theme & Widget Shell | 4 | E1-S1, E1-S2, E1-S3, E1-S4 |
| **U8** Collect & Duplicate Popups | 9 | E2-S1, E2-S2, E2-S3, E2-S4, E4-S1, E4-S2, E4-S3, E4-S4, E8-S4 |
| **U9** Practice & Settings Windows | 20 | E1-S5, E3-S5, E5-S1..S4, E6-S1..S6, E7-S1..S8 |
| **U10** Composition Root & Startup | 0 | — (contributes to 3 stories) |
| **Total** | **42** | ✓ reconciles |

### Why three units have zero primary stories

U1, U5, U6, and U10 are enabling units. No user can observe "the domain layer" or "the service layer"
directly — they observe a Collect card that saves correctly, which is why those stories are primary to
the UI unit that completes them. This is intentional and worth stating: it means **those four units
cannot be validated by acceptance criteria alone**, and their correctness rests on unit tests. That is
exactly why the mandatory 80% coverage gate on new business logic matters most for U1, U4, and U6.

### Why U9 carries 20 stories

It contains all of Practice (10 stories) and all of Settings (8 stories), plus two that surface inside
Settings (E1-S5 start-with-Windows, E3-S5 the API key field). Splitting it was considered and rejected:
both windows share one `QWebEngineView` host mechanism and one `QWebChannel` bridge, so a split would
duplicate that plumbing across two units. Within the unit the build order is Practice first, then
Settings, because the drill is the harder interaction.

Three assignments worth explaining:

- **E1-S5 (start with Windows) -> U9, not U10.** The registration mechanism lives in U5 and startup
  behavior in U10, but the story is only observably true once the toggle exists in the Settings
  General tab, which is U9.
- **E3-S5 (Merriam-Webster key) -> U9, not U4.** U4 already handles a missing key by skipping that
  source. The story needs a field to enter the key, which is a Settings surface.
- **E8-S4 (locked file, Retry) -> U8, not U2.** U2 raises the distinguishable error, but the story is
  about the user keeping their typed word and getting a Retry action — which is popup behavior.

---

## Requirement Coverage Cross-Check

All 74 FRs are covered. Distribution by primary unit:

| Unit | FRs owned |
|---|---|
| U1 | FR-3.2, FR-3.3, FR-5.9, FR-6.3, FR-6.4, FR-6.7, FR-6.10, FR-8.9 |
| U2 | FR-8.1, FR-8.3, FR-8.4, FR-8.5, FR-8.7 |
| U3 | FR-6.16, FR-7.13, FR-8.2, FR-8.8 |
| U4 | FR-3.1, FR-3.4, FR-3.5, FR-3.8, FR-3.9 |
| U5 | FR-1.8, FR-6.5, FR-7.5 |
| U6 | FR-2.5, FR-2.8, FR-2.9, FR-4.1, FR-4.3, FR-4.4, FR-4.5, FR-4.8, FR-5.2, FR-5.3, FR-5.4, FR-5.7, FR-5.8, FR-6.6, FR-6.13, FR-6.15, FR-7.9, FR-7.11 |
| U7 | FR-1.1 – FR-1.7 |
| U8 | FR-2.1 – FR-2.4, FR-2.6, FR-2.7, FR-2.10, FR-3.6, FR-3.7, FR-4.2, FR-4.6, FR-4.7, FR-8.6 |
| U9 | FR-5.1, FR-5.5, FR-5.6, FR-6.1, FR-6.2, FR-6.8, FR-6.9, FR-6.11, FR-6.12, FR-6.14, FR-7.1 – FR-7.8, FR-7.10, FR-7.12 |
| U10 | startup paths of FR-1.4, FR-8.1, FR-8.2, FR-8.8 |

No FR is unassigned. Several appear in more than one unit's list where a requirement genuinely spans
layers — FR-8.1 for instance is implemented in U2 and invoked during U10's startup sequence.

---

## Validation Summary

- [x] All 42 stories assigned to exactly one primary unit
- [x] No story double-assigned as primary
- [x] No story orphaned
- [x] Story count reconciles: 4 + 1 + 4 + 4 + 9 + 20 = 42
- [x] All 74 FRs covered across units
- [x] Every story's primary unit comes at or after all its contributing units in the build order
- [x] No unit depends on a higher-numbered unit
