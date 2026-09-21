"""Locating the widget's character artwork.

Naming convention: ``mini_ani_{state}.png`` for the cat and
``mini_ani_{state}_{character}.png`` for anything else. The cat is unsuffixed because
that is how the existing assets in ``asset/floating_widget/`` are already named, and
renaming shipped artwork to satisfy a convention would be gratuitous.

``resolve`` returns ``None`` rather than raising when artwork is absent, which is what
lets Settings keep the previous character in place and tell the user instead of
rendering a blank widget (E7-S3 branch 4a).
"""

from __future__ import annotations

from pathlib import Path

from vocabulary_trainer.domain.models import CharacterKind, WidgetState

__all__ = ["assets_root", "available_characters", "resolve"]


def assets_root() -> Path:
    """The bundled asset directory."""
    return Path(__file__).resolve().parent.parent.parent / "assets" / "floating_widget"


def _candidates(character: CharacterKind, state: WidgetState) -> list[str]:
    """Filenames to try for a character and pose, most specific first.

    Only the cat may use the unsuffixed names. Letting another character fall back to
    them would make it report as available when its own artwork is absent, so Settings
    would offer "Crocodile" and then render a cat -- worse than not offering it at all.
    Each non-cat character therefore resolves strictly against its own suffixed files.
    """
    suffix = "idle" if state is WidgetState.IDLE else "active"

    if character is CharacterKind.CAT:
        # The "_web" variants are the transparent cutouts used by the HTML mockups --
        # the same artwork under a different name, so they serve as a fallback.
        return [f"mini_ani_{suffix}.png", f"mini_ani_{suffix}_web.png"]

    return [
        f"mini_ani_{suffix}_{character.value}.png",
        f"mini_ani_{suffix}_web_{character.value}.png",
    ]


def resolve(
    character: CharacterKind,
    state: WidgetState,
    root: Path | None = None,
) -> Path | None:
    """Path to the artwork for a character and state, or ``None`` if unavailable."""
    directory = root or assets_root()
    for name in _candidates(character, state):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def available_characters(root: Path | None = None) -> list[CharacterKind]:
    """Characters that have artwork for both states.

    A character missing one pose would render inconsistently as the widget switched
    between idle and active, so both are required before it is offered.
    """
    directory = root or assets_root()
    return [
        character
        for character in CharacterKind
        if resolve(character, WidgetState.IDLE, directory) is not None
        and resolve(character, WidgetState.ACTIVE, directory) is not None
    ]
