# Personas — Vocabulary Trainer v2

Two personas are defined, split by **mode of use** rather than by person. They are the same
individual in two different mental states, and separating them is useful because their needs
actively conflict: the Collector wants zero friction and no context switch, while the Driller
wants a focused, immersive window that owns the screen. Design decisions that serve one can harm
the other, so each story below names which persona it serves.

---

## Persona 1 — "The Collector"

**Mode**: Encountering a new word during other work, and wanting to bank it before it's forgotten.

### Profile
| Attribute | Detail |
|---|---|
| Context | Mid-task — reading an article, watching a video, working through documentation, in a meeting |
| Attention | Divided. The vocabulary app is not the task at hand; it is an interruption they chose to accept |
| Session length | 10–30 seconds per word |
| Frequency | Several times a day, unpredictably |
| Device | Windows desktop, other applications occupying the screen |

### Goals
- Capture a word the instant it's encountered, before the moment passes.
- Get a definition without going to look one up manually.
- File the word somewhere sensible so it can be found again later.
- Return to what they were doing with no residue — no window left open, no lost place.

### Frustrations that drive the design
- Opening a browser tab to look a word up derails the original task, and the tab is still open an
  hour later.
- Having to decide *where* to file a word before a suitable collection exists means either
  abandoning the capture or breaking off to go create one in a settings screen.
- Waiting for a network lookup before being allowed to save means a slow connection costs the word.
- Being told "that word already exists" without being shown what already exists forces a guess.

### Success looks like
- The widget is visible but ignorable, and one click reaches the input.
- The word saves immediately, whether or not the lookup has finished.
- A new collection can be created without leaving the card.
- A duplicate is surfaced with enough context (which collection, collected when) to decide in a
  couple of seconds.

### Stories driven by this persona
E1 (all), E2 (all), E3 (all), E4 (all), E8-S1, E8-S4, E8-S5

---

## Persona 2 — "The Driller"

**Mode**: Deliberately sitting down to practice, having set other work aside.

### Profile
| Attribute | Detail |
|---|---|
| Context | Dedicated study time; the app is the primary task |
| Attention | Focused, and willing to stay in one window |
| Session length | 10–30 minutes |
| Frequency | A few times a week |
| Device | Windows desktop, app window in the foreground |

### Goals
- Choose exactly which words to work on, by collection, without hunting through a long list.
- Be tested on recall by production — typing the word from its meaning, not recognizing it from
  choices.
- Know, moment to moment, whether the session is going well.
- Repeat weak words until they stick, rather than seeing each word once.
- Finish with a clear read on what the session achieved.

### Frustrations that drive the design
- A collection list with dozens of entries and no search or sort makes selection a chore.
- A drill that shows each word once teaches recognition, not recall.
- A wrong answer that silently moves on leaves the correct spelling unknown — the exact moment
  learning should happen is skipped.
- A wrong answer that wipes out accumulated progress on a word is punishing enough to discourage
  continuing.
- Closing the window by accident and losing all session results.

### Success looks like
- Collections are searchable and sortable, with word counts visible before committing.
- The number of correct writes required for mastery is theirs to set.
- Score and penalties update live, and the correct spelling is shown after a miss with time to
  read it.
- Mistakes cost score but never reset mastery progress.
- Both ending early and finishing naturally lead to the same summary, and results are recorded.

### Stories driven by this persona
E5 (all), E6 (all), E1-S2 (as the entry point into Practice)

---

## Shared Concerns

Both personas depend on these, from opposite directions:

| Concern | Collector's stake | Driller's stake |
|---|---|---|
| **Collection management (E7)** | Needs collections to exist and be sensibly named at capture time | Needs them to be meaningful groupings worth practicing as a set |
| **Master file integrity (E8)** | Every capture must survive; a lost write means a lost word | The practice pool is only as trustworthy as the file it reads |
| **Excel as the store** | Occasionally opens the workbook directly to tidy entries by hand | Expects the app to notice those hand edits rather than overwrite them |
| **Widget presence (E1)** | Wants it there, always, one click away | Wants it out of the way during a focused session |

That last row is the sharpest tension in the product, and it is why the widget is toggleable and
why a tray icon exists as a permanent fallback (FR-1.6, FR-1.7). The Driller can dismiss the
widget without losing access to the app; the Collector can bring it back the same way.
