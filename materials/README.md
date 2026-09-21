# Materials — Reference Inputs, Copied Into This Folder

These are the **source materials and historical design documents** the product was
built from, copied here on 2026-09-13 so `VocabularyTrainer.V3/` is self-contained
and you never need to look outside it. V1 and V2 have been archived to
`../../archive/` and are no longer part of the working tree.

**Nothing in here is loaded at runtime.** These are reference inputs for humans, not
application assets. The files the app actually reads live under
`../src/vocabulary_trainer/assets/`. See the note on the dictionary below for the one
place that distinction matters most.

For the consolidated, current-state reference — business context, features, and
technical design in one place — read `../PROJECT.md` instead. That file is the source
of truth. Everything here is historical input that fed into it, and where the two
disagree, `PROJECT.md` (and ultimately the code) wins.

## What each folder is

| Folder | What it holds | Still authoritative? |
|---|---|---|
| `mockup/` | 16 HTML/CSS mockup files, the **visual source of truth** for layout and styling. `styles.css` is where `../src/vocabulary_trainer/ui/theme/tokens.py` was transcribed from. | Yes, for *visuals*. See the stale-copy warning below. |
| `asset/floating_widget/` | Original character artwork (4 PNGs) plus 2 reference JPGs (`animation_1/2.jpg`) that are design references only, never shipped. | Source artwork; the shipped copies live in `../src/vocabulary_trainer/assets/floating_widget/`. |
| `aidlc-docs/` | 23 files: the full AI-DLC trail — numbered requirements (`FR-x.y`), 42 user stories, 2 personas, application design, and an audit log of decisions. | Requirement/story IDs cited throughout the code point here. |
| `specs/output_specs.md` | The living product specification as maintained during development. | Superseded in practice by `../PROJECT.md`, which consolidates it. |
| `draft/brainstorming.md` | Rough idea notes. Explicitly **not** a specification — it says so at the top. | No. Ideas only, several already implemented or rejected. |

## The dictionary is deliberately not duplicated here

The workspace root has a `dictionary/wordnet-2025-dictionary.json` (42.7 MB). It was
**not** copied into this folder, because the app already ships its own copy at:

```
../src/vocabulary_trainer/assets/dictionary/wordnet-2025-dictionary.json
```

That bundled file is what `integrations/local_dictionary_client.py` actually loads,
it is declared in `pyproject.toml`'s `package-data`, and it was verified
**byte-identical** (SHA-256) to the root copy at the time of this move. Copying it
again would add 42.7 MB of redundancy with no benefit and two files to keep in sync
instead of one.

If you ever need to replace the dictionary, replace the bundled one under `src/` —
that is the only copy the application reads.

## Known stale copy in the mockups

The mockups remain the visual reference, but three pieces of their **text** are
out of date and are deliberately not reproduced in the app. There are tests
asserting the first one never appears:

1. **"Cambridge Dictionary"** — a lookup source dropped before v2. The app now uses
   a bundled offline dictionary, Free Dictionary, Merriam-Webster, and Google
   Translate.
2. **"delegated entirely to the local website"** — from an early draft where Practice
   was served over `localhost`. That was reverted; Practice is a native window with
   no server, no browser, and no `localhost`.
3. **Settings tab count** — some mockups draw two panes where **five** ship
   (General, Collections, Widget, Audio, About).

Requirements and `../PROJECT.md` win over mockup copy in all three cases.
